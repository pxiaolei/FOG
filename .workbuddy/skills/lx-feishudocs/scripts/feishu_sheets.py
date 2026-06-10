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
    create.add_argument("--dry-run", action="store_true")

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
    put.add_argument("--dry-run", action="store_true")

    get = subparsers.add_parser("csv-get", help="读取普通 sheet CSV")
    get.add_argument("--spreadsheet-token", default="")
    get.add_argument("--url", default="")
    get.add_argument("--sheet-id", default="")
    get.add_argument("--sheet-name", default="")
    get.add_argument("--range", required=True)

    smoke = subparsers.add_parser("smoke", help="创建普通表格并写读验证")
    smoke.add_argument("--title", default="")
    smoke.add_argument("--folder-token", default="")
    smoke.add_argument("--dry-run", action="store_true")
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
    client = _client(args)

    if args.command == "status":
        _print(client.status())
        return

    if args.command == "create-workbook":
        headers = json.loads(args.headers_json) if args.headers_json else None
        values = json.loads(args.values_json) if args.values_json else None
        _print(
            client.workbook_create(
                args.title,
                folder_token=args.folder_token,
                headers=headers,
                values=values,
                dry_run=args.dry_run,
            )
        )
        return

    if args.command == "workbook-info":
        _print(client.workbook_info(spreadsheet_token=args.spreadsheet_token, url=args.url))
        return

    if args.command == "csv-put":
        csv_text = args.csv or (_load_csv_file(args.csv_file) if args.csv_file else "")
        if not csv_text:
            raise FeishuSheetsError("csv-put 必须提供 --csv 或 --csv-file")
        _print(
            client.csv_put(
                spreadsheet_token=args.spreadsheet_token,
                url=args.url,
                sheet_id=args.sheet_id,
                sheet_name=args.sheet_name,
                start_cell=args.start_cell,
                csv_text=csv_text,
                dry_run=args.dry_run,
            )
        )
        return

    if args.command == "csv-get":
        _print(
            client.csv_get(
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
        create_result = client.workbook_create(
            title,
            folder_token=args.folder_token,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            _print({"dry_run": True, "create": create_result})
            return
        token = client.spreadsheet_token(create_result)
        if not token:
            raise FeishuSheetsError(f"创建结果缺少 spreadsheet_token: {_json_dumps(create_result)}")
        info = client.workbook_info(spreadsheet_token=token)
        sheets = client.sheet_properties(info)
        if not sheets:
            raise FeishuSheetsError(f"工作簿信息缺少 sheet 列表: {_json_dumps(info)}")
        sheet_id = sheets[0]["sheet_id"]
        client.csv_put(
            spreadsheet_token=token,
            sheet_id=sheet_id,
            start_cell="A1",
            csv_text=_rows_to_csv(rows),
        )
        read_result = client.csv_get(
            spreadsheet_token=token,
            sheet_id=sheet_id,
            range_text="A1:B2",
        )
        _print(
            {
                "ok": True,
                "spreadsheet_token": token,
                "sheet_id": sheet_id,
                "title": title,
                "read_rows": client.csv_rows(read_result),
            }
        )


if __name__ == "__main__":
    try:
        main()
    except FeishuSheetsError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
