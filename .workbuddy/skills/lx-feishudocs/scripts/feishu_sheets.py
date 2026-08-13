#!/usr/bin/env python3
"""Feishu ordinary Sheets wrapper for FOG.

This module intentionally targets Feishu/Lark ordinary spreadsheets only. It
does not use Base/bitable/smartsheet APIs.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - project runtime normally has PyYAML
    yaml = None


class FeishuSheetsError(RuntimeError):
    """Feishu Sheets command failed."""


def _find_project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".workbuddy").exists() and (candidate / "config").exists():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = _find_project_root()
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "fog_config.yaml"
WORKBUDDY_LARK_CLI = (
    Path.home()
    / ".workbuddy"
    / "binaries"
    / "node"
    / "cli-connector-packages"
    / "lib"
    / "node_modules"
    / "@larksuite"
    / "cli"
    / "bin"
    / "lark-cli"
)


def _read_config(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _find_nested(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and item not in (None, ""):
                return item
        for item in value.values():
            found = _find_nested(item, names)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_nested(item, names)
            if found not in (None, ""):
                return found
    return None


def _find_sheet_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("sheets", "sheet", "properties"):
            item = value.get(key)
            if isinstance(item, list) and all(isinstance(row, dict) for row in item):
                return item
        for item in value.values():
            found = _find_sheet_list(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_sheet_list(item)
            if found:
                return found
    return []


def _strip_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "token" in lowered and key not in {"spreadsheet_token"}:
                result[key] = "[hidden]"
            elif "secret" in lowered:
                result[key] = "[hidden]"
            else:
                result[key] = _strip_sensitive(item)
        return result
    if isinstance(value, list):
        return [_strip_sensitive(item) for item in value]
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(_strip_sensitive(value), ensure_ascii=False, indent=2)


def _rows_to_csv(rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue()


def _csv_to_rows(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    return [list(row) for row in reader]


def _normalize_annotated_csv(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(" "):
            lines.append(line[1:])
            continue
        if line.startswith("[row="):
            _, _, rest = line.partition("]")
            lines.append(rest.lstrip())
            continue
        lines.append(line)
    return "\n".join(lines)


class FeishuSheetsClient:
    """Small subprocess wrapper around lark-cli Sheets shortcuts."""

    def __init__(
        self,
        cli_path: str | Path | None = None,
        config_path: str | Path | None = None,
        identity: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.config_path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG
        self.config = _read_config(self.config_path)
        feishu_config = self.config.get("lx_feishudocs", {})
        if not isinstance(feishu_config, dict):
            feishu_config = {}
        configured_cli = str(feishu_config.get("cli_path") or "").strip()
        self.cli_path = self._resolve_cli_path(str(cli_path or configured_cli or ""))
        self.identity = str(identity or feishu_config.get("identity") or "user")
        self.timeout = timeout

    def _resolve_cli_path(self, explicit: str) -> Path:
        candidates: list[str | Path | None] = [
            explicit or None,
            os.environ.get("LARK_CLI"),
            shutil.which("lark-cli"),
            WORKBUDDY_LARK_CLI,
            "/opt/homebrew/bin/lark-cli",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.exists() and os.access(path, os.X_OK):
                return path
        raise FeishuSheetsError(
            "未找到 lark-cli。请在 WorkBuddy 安装飞书连接器，或设置 LARK_CLI。"
        )

    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        proc = subprocess.run(
            [str(self.cli_path), *args],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout or self.timeout,
            check=False,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        parsed: Any = None
        for payload in (stdout, stderr):
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
                break
            except json.JSONDecodeError:
                continue
        if proc.returncode != 0:
            detail = _json_dumps(parsed) if parsed is not None else (stderr or stdout)
            raise FeishuSheetsError(f"lark-cli 执行失败: {' '.join(args)}\n{detail[:2000]}")
        if isinstance(parsed, dict):
            if parsed.get("ok") is False:
                raise FeishuSheetsError(f"lark-cli 返回失败: {_json_dumps(parsed)[:2000]}")
            return parsed
        if stdout:
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                return {"ok": True, "text": stdout}
            if isinstance(data, dict):
                return data
        return {"ok": True}

    def status(self) -> dict[str, Any]:
        return self.run(["auth", "status"])

    def workbook_create(
        self,
        title: str,
        *,
        folder_token: str = "",
        headers: list[str] | None = None,
        values: list[list[Any]] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        args = ["sheets", "+workbook-create", "--as", self.identity, "--title", title, "--json"]
        if folder_token:
            args.extend(["--folder-token", folder_token])
        if headers:
            args.extend(["--headers", json.dumps(headers, ensure_ascii=False)])
        if values:
            args.extend(["--values", json.dumps(values, ensure_ascii=False)])
        if dry_run:
            args.append("--dry-run")
        return self.run(args)

    def workbook_info(self, *, spreadsheet_token: str = "", url: str = "") -> dict[str, Any]:
        args = ["sheets", "+workbook-info", "--as", self.identity, "--json"]
        if url:
            args.extend(["--url", url])
        else:
            args.extend(["--spreadsheet-token", spreadsheet_token])
        return self.run(args)

    def workbook_inspect(self, *, spreadsheet_token: str) -> dict[str, Any]:
        return self.run(
            [
                "drive",
                "+inspect",
                "--as",
                self.identity,
                "--json",
                "--url",
                spreadsheet_token,
                "--type",
                "sheet",
            ]
        )

    def csv_put(
        self,
        *,
        spreadsheet_token: str = "",
        url: str = "",
        sheet_id: str = "",
        sheet_name: str = "",
        start_cell: str = "A1",
        csv_text: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        args = ["sheets", "+csv-put", "--as", self.identity, "--json"]
        if url:
            args.extend(["--url", url])
        else:
            args.extend(["--spreadsheet-token", spreadsheet_token])
        if sheet_name:
            args.extend(["--sheet-name", sheet_name])
        else:
            args.extend(["--sheet-id", sheet_id])
        args.extend(["--start-cell", start_cell, "--csv", "-"])
        if dry_run:
            args.append("--dry-run")
        return self.run(args, input_text=csv_text)

    def csv_get(
        self,
        *,
        spreadsheet_token: str = "",
        url: str = "",
        sheet_id: str = "",
        sheet_name: str = "",
        range_text: str,
    ) -> dict[str, Any]:
        args = [
            "sheets",
            "+csv-get",
            "--as",
            self.identity,
            "--json",
            "--include-row-prefix=false",
        ]
        if url:
            args.extend(["--url", url])
        else:
            args.extend(["--spreadsheet-token", spreadsheet_token])
        if sheet_name:
            args.extend(["--sheet-name", sheet_name])
        else:
            args.extend(["--sheet-id", sheet_id])
        args.extend(["--range", range_text])
        return self.run(args)

    @staticmethod
    def spreadsheet_token(result: dict[str, Any]) -> str:
        value = _find_nested(result, {"spreadsheet_token", "spreadsheetToken", "token"})
        return str(value or "")

    @staticmethod
    def sheet_properties(result: dict[str, Any]) -> list[dict[str, Any]]:
        properties: list[dict[str, Any]] = []
        for item in _find_sheet_list(result):
            sheet_id = str(
                item.get("sheet_id")
                or item.get("sheetId")
                or item.get("id")
                or item.get("reference_id")
                or ""
            )
            title = str(item.get("title") or item.get("sheet_name") or item.get("name") or sheet_id)
            grid = item.get("grid_properties") or item.get("gridProperties") or {}
            if not isinstance(grid, dict):
                grid = {}
            row_count = item.get("row_count") or item.get("rowCount") or grid.get("row_count") or grid.get("rowCount") or 200
            column_count = (
                item.get("column_count")
                or item.get("columnCount")
                or grid.get("column_count")
                or grid.get("columnCount")
                or 20
            )
            if sheet_id:
                properties.append(
                    {
                        "sheet_id": sheet_id,
                        "title": title,
                        "row_count": int(row_count or 200),
                        "column_count": int(column_count or 20),
                    }
                )
        return properties

    @staticmethod
    def workbook_identity(result: dict[str, Any]) -> dict[str, str]:
        return {
            "type": str(_find_nested(result, {"type", "file_type", "obj_type"}) or ""),
            "token": str(
                _find_nested(
                    result,
                    {"token", "file_token", "spreadsheet_token", "obj_token"},
                )
                or ""
            ),
            "title": str(_find_nested(result, {"title", "name"}) or ""),
        }

    @staticmethod
    def csv_rows(result: dict[str, Any]) -> list[list[str]]:
        annotated = _find_nested(result, {"annotated_csv"})
        if annotated is not None:
            return _csv_to_rows(_normalize_annotated_csv(str(annotated)))

        text = _find_nested(result, {"csv", "text"})
        if text is None:
            data = result.get("data")
            if isinstance(data, dict):
                annotated = data.get("annotated_csv")
                if annotated is not None:
                    return _csv_to_rows(_normalize_annotated_csv(str(annotated)))
                text = data.get("csv")
        return _csv_to_rows(str(text or ""))


def _load_csv_file(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


_A1_CELL_RE = re.compile(r"^([A-Za-z]+)([1-9][0-9]*)$")


def _column_number(column: str) -> int:
    result = 0
    for char in column.upper():
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def _column_name(number: int) -> str:
    chars: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def _csv_matrix_and_range(csv_text: str, start_cell: str) -> tuple[list[list[str]], str, int, int]:
    match = _A1_CELL_RE.fullmatch(start_cell.strip())
    if not match:
        raise FeishuSheetsError(f"start-cell 必须是单个 A1 单元格，例如 A1；实际为 {start_cell!r}")
    rows = _csv_to_rows(csv_text)
    if not rows or not any(rows):
        raise FeishuSheetsError("csv-put 的 CSV 必须至少包含一个单元格")
    width = max(len(row) for row in rows)
    matrix = [row + [""] * (width - len(row)) for row in rows]
    start_column = _column_number(match.group(1))
    start_row = int(match.group(2))
    end_column = _column_name(start_column + width - 1)
    end_row = start_row + len(matrix) - 1
    normalized_start = f"{_column_name(start_column)}{start_row}"
    return matrix, f"{normalized_start}:{end_column}{end_row}", start_column, start_row


def _readback_is_complete(result: dict[str, Any]) -> bool:
    truncated = _find_nested(result, {"truncated"})
    complete = _find_nested(result, {"complete"})
    has_more = _find_nested(result, {"has_more"})
    return truncated is not True and complete is not False and has_more is not True


def _verify_matrix(
    expected: list[list[str]],
    actual: list[list[str]],
    *,
    start_column: int,
    start_row: int,
) -> None:
    missing = object()
    row_count = max(len(expected), len(actual))
    for row_offset in range(row_count):
        expected_row: list[str] | None = expected[row_offset] if row_offset < len(expected) else None
        actual_row: list[str] | None = actual[row_offset] if row_offset < len(actual) else None
        column_count = max(len(expected_row or []), len(actual_row or []), 1)
        for column_offset in range(column_count):
            expected_value: object = (
                expected_row[column_offset]
                if expected_row is not None and column_offset < len(expected_row)
                else missing
            )
            actual_value: object = (
                actual_row[column_offset]
                if actual_row is not None and column_offset < len(actual_row)
                else missing
            )
            if expected_value == actual_value:
                continue
            cell = f"{_column_name(start_column + column_offset)}{start_row + row_offset}"
            expected_display = "<缺失>" if expected_value is missing else repr(expected_value)
            actual_display = "<缺失>" if actual_value is missing else repr(actual_value)
            raise FeishuSheetsError(
                f"写后读回不一致: {cell} 预期 {expected_display}，实际 {actual_display}"
            )


def _verify_created_workbook(
    client: FeishuSheetsClient,
    create_result: dict[str, Any],
    *,
    title: str,
    folder_token: str,
    headers: list[Any] | None = None,
    values: list[list[Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    token = client.spreadsheet_token(create_result)
    if not token:
        raise FeishuSheetsError(f"创建结果缺少 spreadsheet_token: {_json_dumps(create_result)}")
    info = client.workbook_info(spreadsheet_token=token)
    sheets = client.sheet_properties(info)
    if not sheets:
        raise FeishuSheetsError(f"创建后读回缺少 sheet 列表: {_json_dumps(info)}")
    identity = FeishuSheetsClient.workbook_identity(
        client.workbook_inspect(spreadsheet_token=token)
    )
    if identity["type"] != "sheet":
        raise FeishuSheetsError(
            f"创建后读回类型不一致: 预期 'sheet'，实际 {identity['type']!r}"
        )
    if identity["token"] != token:
        raise FeishuSheetsError(
            f"创建后读回 token 不一致: 预期 {token!r}，实际 {identity['token']!r}"
        )
    if identity["title"] != title:
        raise FeishuSheetsError(
            f"创建后读回标题不一致: 预期 {title!r}，实际 {identity['title']!r}"
        )
    readback = {
        "type": identity["type"],
        "spreadsheet_token": identity["token"],
        "title": identity["title"],
        "sheet_count": len(sheets),
        "requested_folder_token": folder_token,
        "folder_readback": "API不提供创建后folder读回",
    }
    expected_rows = ([headers] if headers else []) + (values or [])
    if expected_rows:
        column_count = max(len(row) for row in expected_rows)
        if column_count < 1:
            raise FeishuSheetsError("创建初始矩阵至少需要一列")
        sheet_id = str(sheets[0].get("sheet_id") or "")
        if not sheet_id:
            raise FeishuSheetsError("创建后读回缺少首个 sheet_id")
        range_text = f"A1:{_column_name(column_count)}{len(expected_rows)}"
        matrix_result = client.csv_get(
            spreadsheet_token=token,
            url="",
            sheet_id=sheet_id,
            sheet_name="",
            range_text=range_text,
        )
        if not _readback_is_complete(matrix_result):
            raise FeishuSheetsError(f"创建初始矩阵读回不完整: {range_text}")
        expected = [[str(value) for value in row] for row in expected_rows]
        actual = client.csv_rows(matrix_result)
        _verify_matrix(expected, actual, start_column=1, start_row=1)
        readback["initial_matrix"] = {
            "range": range_text,
            "row_count": len(expected),
            "column_count": column_count,
            "rows": actual,
        }
    return token, sheets, readback


def _verified_csv_put(
    client: FeishuSheetsClient,
    *,
    spreadsheet_token: str,
    url: str,
    sheet_id: str,
    sheet_name: str,
    start_cell: str,
    csv_text: str,
) -> dict[str, Any]:
    if bool(spreadsheet_token) == bool(url):
        raise FeishuSheetsError("csv-put 必须且只能提供 --spreadsheet-token 或 --url")
    if bool(sheet_id) == bool(sheet_name):
        raise FeishuSheetsError("csv-put 必须且只能提供 --sheet-id 或 --sheet-name")
    expected, range_text, start_column, start_row = _csv_matrix_and_range(csv_text, start_cell)
    write_result = client.csv_put(
        spreadsheet_token=spreadsheet_token,
        url=url,
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        start_cell=start_cell,
        csv_text=csv_text,
    )
    read_result = client.csv_get(
        spreadsheet_token=spreadsheet_token,
        url=url,
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        range_text=range_text,
    )
    if not _readback_is_complete(read_result):
        raise FeishuSheetsError(f"写后读回不完整: {range_text}")
    actual = client.csv_rows(read_result)
    _verify_matrix(
        expected,
        actual,
        start_column=start_column,
        start_row=start_row,
    )
    return {
        "ok": True,
        "write": write_result,
        "readback": {
            "range": range_text,
            "row_count": len(expected),
            "column_count": len(expected[0]),
            "rows": actual,
        },
    }


def _write_preview(command: str, **target: Any) -> dict[str, Any]:
    return {"ok": True, "dry_run": True, "command": command, **target}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FOG 飞书普通电子表格工具")
    parser.add_argument("--config-path", help="配置文件路径，默认 config/fog_config.yaml")
    parser.add_argument("--cli-path", help="lark-cli 路径；默认自动查找 WorkBuddy 内置 CLI")
    parser.add_argument("--identity", choices=["user", "bot"], help="飞书身份，默认 user")
    parser.add_argument("--timeout", type=int, default=120, help="命令超时秒数")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="查看飞书账号状态")

    create = subparsers.add_parser("create-workbook", help="创建普通电子表格")
    create.add_argument("--title", required=True)
    create.add_argument("--folder-token", default="")
    create.add_argument("--headers-json", help="表头 JSON 数组")
    create.add_argument("--values-json", help="初始值 JSON 二维数组")
    create_mode = create.add_mutually_exclusive_group()
    create_mode.add_argument("--dry-run", action="store_true")
    create_mode.add_argument("--confirmed", action="store_true", help="确认创建飞书工作簿")

    info = subparsers.add_parser("workbook-info", help="查看普通电子表格信息")
    info.add_argument("--spreadsheet-token", default="")
    info.add_argument("--url", default="")

    put = subparsers.add_parser("csv-put", help="写 CSV 到普通 sheet")
    put.add_argument("--spreadsheet-token", default="")
    put.add_argument("--url", default="")
    put.add_argument("--sheet-id", default="")
    put.add_argument("--sheet-name", default="")
    put.add_argument("--start-cell", default="A1")
    put.add_argument("--csv", default="")
    put.add_argument("--csv-file", default="")
    put_mode = put.add_mutually_exclusive_group()
    put_mode.add_argument("--dry-run", action="store_true")
    put_mode.add_argument("--confirmed", action="store_true", help="确认写入飞书工作簿")

    get = subparsers.add_parser("csv-get", help="读取普通 sheet CSV")
    get.add_argument("--spreadsheet-token", default="")
    get.add_argument("--url", default="")
    get.add_argument("--sheet-id", default="")
    get.add_argument("--sheet-name", default="")
    get.add_argument("--range", required=True)

    smoke = subparsers.add_parser("smoke", help="创建普通表格并写读验证")
    smoke.add_argument("--title", default="")
    smoke.add_argument("--folder-token", default="")
    smoke_mode = smoke.add_mutually_exclusive_group()
    smoke_mode.add_argument("--dry-run", action="store_true")
    smoke_mode.add_argument("--confirmed", action="store_true", help="确认创建、写入并读回 smoke 工作簿")
    return parser


def _client(args: argparse.Namespace) -> FeishuSheetsClient:
    return FeishuSheetsClient(
        cli_path=args.cli_path,
        config_path=args.config_path,
        identity=args.identity,
        timeout=args.timeout,
    )


def _print(value: Any) -> None:
    print(_json_dumps(value))


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "status":
        _print(_client(args).status())
        return

    if args.command == "create-workbook":
        headers = json.loads(args.headers_json) if args.headers_json else None
        values = json.loads(args.values_json) if args.values_json else None
        if not args.confirmed:
            _print(
                _write_preview(
                    "create-workbook",
                    title=args.title,
                    folder_token=args.folder_token,
                    headers=headers,
                    values=values,
                )
            )
            return
        client = _client(args)
        create_result = client.workbook_create(
            args.title,
            folder_token=args.folder_token,
            headers=headers,
            values=values,
        )
        _, _, readback = _verify_created_workbook(
            client,
            create_result,
            title=args.title,
            folder_token=args.folder_token,
            headers=headers,
            values=values,
        )
        _print({"ok": True, "create": create_result, "readback": readback})
        return

    if args.command == "workbook-info":
        _print(_client(args).workbook_info(spreadsheet_token=args.spreadsheet_token, url=args.url))
        return

    if args.command == "csv-put":
        csv_text = args.csv or (_load_csv_file(args.csv_file) if args.csv_file else "")
        if not csv_text:
            raise FeishuSheetsError("csv-put 必须提供 --csv 或 --csv-file")
        if not args.confirmed:
            _print(
                _write_preview(
                    "csv-put",
                    spreadsheet_token=args.spreadsheet_token,
                    url=args.url,
                    sheet_id=args.sheet_id,
                    sheet_name=args.sheet_name,
                    start_cell=args.start_cell,
                    row_count=len(_csv_to_rows(csv_text)),
                )
            )
            return
        _print(
            _verified_csv_put(
                _client(args),
                spreadsheet_token=args.spreadsheet_token,
                url=args.url,
                sheet_id=args.sheet_id,
                sheet_name=args.sheet_name,
                start_cell=args.start_cell,
                csv_text=csv_text,
            )
        )
        return

    if args.command == "csv-get":
        _print(
            _client(args).csv_get(
                spreadsheet_token=args.spreadsheet_token,
                url=args.url,
                sheet_id=args.sheet_id,
                sheet_name=args.sheet_name,
                range_text=args.range,
            )
        )
        return

    if args.command == "smoke":
        from datetime import datetime

        title = args.title or f"FOG飞书普通表格Smoke-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        rows = [["检查项", "结果"], ["普通表格写入", "ok"]]
        if not args.confirmed:
            _print(
                _write_preview(
                    "smoke",
                    title=title,
                    folder_token=args.folder_token,
                    start_cell="A1",
                    rows=rows,
                )
            )
            return
        client = _client(args)
        create_result = client.workbook_create(
            title,
            folder_token=args.folder_token,
        )
        token, sheets, create_readback = _verify_created_workbook(
            client,
            create_result,
            title=title,
            folder_token=args.folder_token,
        )
        sheet_id = sheets[0]["sheet_id"]
        write_result = _verified_csv_put(
            client,
            spreadsheet_token=token,
            url="",
            sheet_id=sheet_id,
            sheet_name="",
            start_cell="A1",
            csv_text=_rows_to_csv(rows),
        )
        _print(
            {
                "ok": True,
                "spreadsheet_token": token,
                "sheet_id": sheet_id,
                "title": title,
                "create_readback": create_readback,
                "write_readback": write_result["readback"],
                "read_rows": write_result["readback"]["rows"],
            }
        )


if __name__ == "__main__":
    try:
        main()
    except FeishuSheetsError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
