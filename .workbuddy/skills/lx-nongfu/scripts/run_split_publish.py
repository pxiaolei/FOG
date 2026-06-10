#!/usr/bin/env python3
"""Split a Feishu master sheet into operator daily-info sheets.

This command implements the lx-nongfu orchestration:

- read a Feishu ordinary spreadsheet master sheet;
- map rows to operators through lx_shujuku.operator_brand;
- create one same-named sheet under each operator's daily-info workbook;
- write matched rows and optionally copy the source header format;
- generate one merchant-facing notice block per operator.

It intentionally targets Feishu ordinary Sheets only. It does not use Base.
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
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - WorkBuddy runtime normally has PyYAML
    yaml = None


DEFAULT_SOP_URL = "https://shimo.im/docs/zdkydeonJzUOaOq6"
DEFAULT_NOTIFICATION_TEMPLATE = """为提升{topic_label}，需要配置资源位&触达配置，辛苦尽早完成配置。
🔍配置检查表：{link}
📚配置SOP：{sop_url}
配置完成时间：{deadline}
配置用物料：{material_note}"""


class NongfuError(RuntimeError):
    """Expected user-facing error."""


@dataclass
class SourceSheet:
    url: str
    token: str
    sheet_id: str
    sheet_name: str
    row_count: int
    column_count: int


@dataclass
class TargetWorkbook:
    operator: str
    folder_token: str
    spreadsheet_token: str
    url: str
    existing_sheets: dict[str, str] = field(default_factory=dict)


@dataclass
class OperatorPublish:
    operator: str
    data_rows: list[list[str]]
    target: TargetWorkbook | None = None
    sheet_id: str = ""
    link: str = ""
    status: str = "pending"
    reason: str = ""


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".workbuddy" / "skills").is_dir() and (candidate / "config").is_dir():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()
CONFIG_PATH = PROJECT_ROOT / "config" / "fog_config.yaml"
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


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def resolve_lark_cli(config: dict[str, Any], explicit: str = "") -> Path:
    feishu = config.get("lx_feishudocs", {})
    configured = feishu.get("cli_path", "") if isinstance(feishu, dict) else ""
    candidates = [
        explicit,
        os.environ.get("LARK_CLI", ""),
        str(configured or ""),
        shutil.which("lark-cli") or "",
        str(WORKBUDDY_LARK_CLI),
        "/opt/homebrew/bin/lark-cli",
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(str(raw)).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return path
    raise NongfuError("未找到 lark-cli；请先在 WorkBuddy 安装并授权飞书连接器。")


def extract_sheet_token(url_or_token: str) -> str:
    value = url_or_token.strip()
    match = re.search(r"/(?:sheets|spreadsheets)/([^/?#]+)", value)
    return match.group(1) if match else value


def extract_folder_token(url_or_token: str) -> str:
    value = url_or_token.strip()
    match = re.search(r"/drive/folder/([^/?#]+)", value)
    return match.group(1) if match else value


def col_to_a1(column: int) -> str:
    result = ""
    current = column
    while current > 0:
        current, rem = divmod(current - 1, 26)
        result = chr(65 + rem) + result
    return result


def a1_range(row_count: int, column_count: int) -> str:
    return f"A1:{col_to_a1(column_count)}{row_count}"


def rows_to_csv(rows: list[list[Any]], column_count: int | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        values = list(row)
        if column_count is not None:
            values = (values + [""] * column_count)[:column_count]
        writer.writerow(values)
    return buffer.getvalue()


def parse_annotated_csv(text: str) -> list[list[str]]:
    lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\[row=\d+\]\s?(.*)$", line)
        lines.append(match.group(1) if match else line)
    return [list(row) for row in csv.reader(io.StringIO("\n".join(lines)))]


def pad_row(row: list[str], column_count: int) -> list[str]:
    return (list(row) + [""] * column_count)[:column_count]


RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def normalize_color(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    match = RGB_RE.match(value.strip())
    if not match:
        return value
    r, g, b = (max(0, min(255, int(part))) for part in match.groups())
    return f"#{r:02X}{g:02X}{b:02X}"


def normalize_colors(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_colors(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_colors(item) for item in value]
    return normalize_color(value)


def sanitize_cell_for_set(cell: Any) -> dict[str, Any]:
    if not isinstance(cell, dict) or not cell:
        return {}
    allowed = {
        "value",
        "formula",
        "rich_text",
        "multiple_values",
        "cell_styles",
        "border_styles",
        "note",
        "data_validation",
    }
    result = {key: value for key, value in cell.items() if key in allowed and value not in (None, {}, [])}
    if "formula" in result:
        result.pop("value", None)
        result.pop("rich_text", None)
        result.pop("multiple_values", None)
    elif "rich_text" in result:
        result.pop("value", None)
        result.pop("multiple_values", None)
    elif "multiple_values" in result:
        result.pop("value", None)
    return normalize_colors(result)


def rectangular_cells(cells: list[list[Any]], rows: int, cols: int) -> list[list[dict[str, Any]]]:
    result: list[list[dict[str, Any]]] = []
    for row_index in range(rows):
        source_row = cells[row_index] if row_index < len(cells) else []
        result.append(
            [
                sanitize_cell_for_set(source_row[col_index] if col_index < len(source_row) else {})
                for col_index in range(cols)
            ]
        )
    return result


def parse_json_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    start = text.find("{")
    if start < 0:
        raise NongfuError(f"命令没有返回 JSON: {text[:500]}")
    return json.loads(text[start:])


class LarkCli:
    def __init__(self, cli_path: Path, identity: str = "user", timeout: int = 180) -> None:
        self.cli_path = cli_path
        self.identity = identity
        self.timeout = timeout

    def run(self, args: list[str], *, input_text: str | None = None, retries: int = 1) -> dict[str, Any]:
        argv = [str(self.cli_path), *args]
        last_detail = ""
        for attempt in range(1, retries + 2):
            proc = subprocess.run(
                argv,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            if proc.returncode == 0:
                return parse_json_output(proc.stdout)
            last_detail = proc.stderr.strip() or proc.stdout.strip()
            if attempt <= retries:
                time.sleep(3 * attempt)
        raise NongfuError(f"lark-cli 执行失败: {' '.join(args)}\n{last_detail[:2000]}")

    def sheets(self, args: list[str], *, input_text: str | None = None, retries: int = 1) -> dict[str, Any]:
        return self.run(["sheets", *args, "--as", self.identity, "--json"], input_text=input_text, retries=retries)

    def drive(self, args: list[str], *, retries: int = 1) -> dict[str, Any]:
        return self.run(["drive", *args, "--as", self.identity, "--json"], retries=retries)


def list_drive_files(cli: LarkCli, folder_token: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {"folder_token": folder_token, "page_size": 200}
        if page_token:
            params["page_token"] = page_token
        result = cli.drive(["files", "list", "--params", json.dumps(params, ensure_ascii=False)])
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        batch = data.get("files", []) if isinstance(data, dict) else []
        files.extend([item for item in batch if isinstance(item, dict)])
        if not isinstance(data, dict) or not data.get("has_more"):
            break
        page_token = str(data.get("next_page_token") or data.get("page_token") or "")
        if not page_token:
            break
    return files


def workbook_info(cli: LarkCli, *, url: str = "", token: str = "") -> dict[str, Any]:
    args = ["+workbook-info"]
    if url:
        args.extend(["--url", url])
    else:
        args.extend(["--spreadsheet-token", token])
    return cli.sheets(args)


def sheet_records(info: dict[str, Any]) -> list[dict[str, Any]]:
    data = info.get("data") if isinstance(info.get("data"), dict) else info
    sheets = data.get("sheets", []) if isinstance(data, dict) else []
    return [item for item in sheets if isinstance(item, dict)]


def choose_source_sheet(cli: LarkCli, source_url: str, source_sheet_name: str) -> SourceSheet:
    info = workbook_info(cli, url=source_url)
    sheets = sheet_records(info)
    if not sheets:
        raise NongfuError("大文档没有可读取的 sheet。")
    if source_sheet_name:
        selected = next(
            (sheet for sheet in sheets if (sheet.get("sheet_name") or sheet.get("title") or sheet.get("name")) == source_sheet_name),
            None,
        )
        if not selected:
            raise NongfuError(f"大文档中没有 sheet: {source_sheet_name}")
    elif len(sheets) == 1:
        selected = sheets[0]
    else:
        names = [str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "") for sheet in sheets]
        raise NongfuError("大文档有多个 sheet，请用 --source-sheet 指定: " + "、".join(names))
    sheet_name = str(selected.get("sheet_name") or selected.get("title") or selected.get("name") or "")
    sheet_id = str(selected.get("sheet_id") or selected.get("id") or selected.get("reference_id") or "")
    if not sheet_id or not sheet_name:
        raise NongfuError(f"大文档 sheet 元数据不完整: {selected}")
    return SourceSheet(
        url=source_url,
        token=extract_sheet_token(source_url),
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        row_count=int(selected.get("row_count") or selected.get("rowCount") or 0),
        column_count=int(selected.get("column_count") or selected.get("columnCount") or 0),
    )


def read_sheet_rows(cli: LarkCli, source: SourceSheet, source_range: str = "") -> list[list[str]]:
    row_count = source.row_count or 1000
    column_count = source.column_count or 50
    range_text = source_range or a1_range(row_count, column_count)
    result = cli.sheets(
        [
            "+csv-get",
            "--url",
            source.url,
            "--sheet-id",
            source.sheet_id,
            "--range",
            range_text,
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    annotated = data.get("annotated_csv") if isinstance(data, dict) else ""
    return parse_annotated_csv(str(annotated or ""))


def load_operator_mapping(contact_person: str, limit: int) -> tuple[dict[tuple[str, str], str], list[dict[str, Any]], int]:
    db_tools = PROJECT_ROOT / ".workbuddy" / "skills" / "lx_shujuku" / "scripts" / "db_tools.py"
    if not db_tools.exists():
        raise NongfuError(f"缺少 lx_shujuku db_tools.py: {db_tools}")
    escaped = contact_person.replace("'", "''")
    sql = (
        "SELECT contact_person, operator_entity, brand_name, city_name "
        "FROM operator_brand "
        f"WHERE contact_person = '{escaped}' "
        "ORDER BY operator_entity, brand_name, city_name "
        f"LIMIT {int(limit)}"
    )
    proc = subprocess.run(
        [sys.executable, str(db_tools), "query", sql, "--json"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise NongfuError(f"查询 operator_brand 失败:\n{(proc.stderr or proc.stdout).strip()[:2000]}")
    payload = parse_json_output(proc.stdout)
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise NongfuError("operator_brand 查询结果格式异常：rows 不是列表。")
    mapping: dict[tuple[str, str], str] = {}
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        brand = str(row.get("brand_name") or "").strip()
        city = str(row.get("city_name") or "").strip()
        operator = str(row.get("operator_entity") or "").strip()
        if not brand or not city or not operator:
            continue
        key = (brand, city)
        if key in mapping and mapping[key] != operator:
            conflicts.append({"brand": brand, "city": city, "operators": [mapping[key], operator]})
        mapping[key] = operator
    return mapping, conflicts, int(payload.get("row_count") or len(rows))


def configured_list(config: dict[str, Any], path: list[str], default: list[str]) -> list[str]:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    if isinstance(current, list) and current:
        return [str(item) for item in current]
    return default


def configured_value(config: dict[str, Any], path: list[str], default: str = "") -> str:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return str(current or default).strip()


def root_folder_from_contact_config(operator_doc: dict[str, Any], contact_person: str) -> str:
    mapping = operator_doc.get("contact_person_root_folders")
    if not isinstance(mapping, dict):
        return ""
    value = mapping.get(contact_person)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("url") or value.get("token") or "").strip()
    return ""


def resolve_operator_root_folder(args: argparse.Namespace, config: dict[str, Any], contact_person: str) -> str:
    explicit = args.operator_root_folder_url or args.operator_root_folder_token
    if explicit:
        return extract_folder_token(explicit)
    operator_doc = configured_value_map(config, ["lx_nongfu", "operator_doc"])
    configured = root_folder_from_contact_config(operator_doc, contact_person)
    if not configured:
        configured = str(
            operator_doc.get("operator_root_folder_url")
            or operator_doc.get("operator_root_folder_token")
            or ""
        ).strip()
    return extract_folder_token(configured) if configured else ""


def configured_value_map(config: dict[str, Any], path: list[str]) -> dict[str, Any]:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def auto_header_row(rows: list[list[str]], brand_fields: list[str], city_fields: list[str], max_scan_rows: int) -> int:
    brand_set = {item.strip() for item in brand_fields}
    city_set = {item.strip() for item in city_fields}
    for index, row in enumerate(rows[:max_scan_rows], start=1):
        values = {str(value).strip() for value in row}
        if values & brand_set and values & city_set:
            return index
    raise NongfuError(
        "无法自动识别品牌/城市表头行；请用 --header-row 指定。"
    )


def find_column(header: list[str], candidates: list[str], label: str) -> int:
    lookup = {str(name).strip(): index for index, name in enumerate(header)}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    raise NongfuError(f"表头中没有找到{label}列，候选：{', '.join(candidates)}")


def group_rows_by_operator(
    rows: list[list[str]],
    header_row_number: int,
    brand_col: int,
    city_col: int,
    mapping: dict[tuple[str, str], str],
) -> tuple[dict[str, list[list[str]]], list[dict[str, Any]], int]:
    groups: dict[str, list[list[str]]] = {}
    out_of_scope: list[dict[str, Any]] = []
    valid_rows = 0
    for row_number, row in enumerate(rows[header_row_number:], start=header_row_number + 1):
        brand = str(row[brand_col] if brand_col < len(row) else "").strip()
        city = str(row[city_col] if city_col < len(row) else "").strip()
        if not brand and not city:
            continue
        valid_rows += 1
        operator = mapping.get((brand, city))
        if operator:
            groups.setdefault(operator, []).append(row)
        else:
            out_of_scope.append({"source_row": row_number, "brand": brand, "city": city})
    return groups, out_of_scope, valid_rows


def file_type(item: dict[str, Any]) -> str:
    return str(item.get("type") or item.get("obj_type") or item.get("file_type") or "")


def file_url(item: dict[str, Any]) -> str:
    return str(item.get("url") or item.get("file_url") or item.get("link") or "")


def resolve_targets(
    cli: LarkCli,
    root_folder_token: str,
    operators: list[str],
    operator_folder_template: str,
    target_table_template: str,
) -> dict[str, TargetWorkbook]:
    root_files = list_drive_files(cli, root_folder_token)
    folder_by_name = {
        str(item.get("name") or ""): str(item.get("token") or item.get("file_token") or "")
        for item in root_files
        if file_type(item) == "folder"
    }
    result: dict[str, TargetWorkbook] = {}
    for operator in operators:
        folder_name = operator_folder_template.format(operator=operator)
        folder_token = folder_by_name.get(folder_name, "")
        if not folder_token:
            continue
        target_name = target_table_template.format(operator=operator)
        files = list_drive_files(cli, folder_token)
        target_file = next(
            (
                item
                for item in files
                if str(item.get("name") or "") == target_name and file_type(item) == "sheet"
            ),
            None,
        )
        if not target_file:
            continue
        url = file_url(target_file)
        token = extract_sheet_token(url) if url else str(target_file.get("token") or target_file.get("file_token") or "")
        info = workbook_info(cli, token=token)
        existing: dict[str, str] = {}
        for sheet in sheet_records(info):
            sheet_name = str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "")
            sheet_id = str(sheet.get("sheet_id") or sheet.get("id") or sheet.get("reference_id") or "")
            if sheet_name and sheet_id:
                existing[sheet_name] = sheet_id
        result[operator] = TargetWorkbook(
            operator=operator,
            folder_token=folder_token,
            spreadsheet_token=token,
            url=url,
            existing_sheets=existing,
        )
    return result


def read_header_format(cli: LarkCli, source: SourceSheet, header_rows: int, column_count: int) -> tuple[list[list[dict[str, Any]]], dict[str, Any]]:
    range_text = a1_range(header_rows, column_count)
    cells_result = cli.sheets(
        [
            "+cells-get",
            "--url",
            source.url,
            "--sheet-id",
            source.sheet_id,
            "--range",
            range_text,
            "--include",
            "value,style",
        ]
    )
    data = cells_result.get("data") if isinstance(cells_result.get("data"), dict) else {}
    ranges = data.get("ranges", []) if isinstance(data, dict) else []
    cells = ranges[0].get("cells", []) if ranges and isinstance(ranges[0], dict) else []
    layout = cli.sheets(
        [
            "+sheet-info",
            "--url",
            source.url,
            "--sheet-id",
            source.sheet_id,
            "--range",
            range_text,
            "--include",
            "merges,row_heights,col_widths",
        ]
    )
    layout_data = layout.get("data") if isinstance(layout.get("data"), dict) else {}
    return rectangular_cells(cells if isinstance(cells, list) else [], header_rows, column_count), layout_data


def apply_header_format(
    cli: LarkCli,
    target: TargetWorkbook,
    sheet_id: str,
    header_cells: list[list[dict[str, Any]]],
    layout: dict[str, Any],
    header_rows: int,
    column_count: int,
    delay_seconds: float,
) -> None:
    range_text = a1_range(header_rows, column_count)
    cli.sheets(
        [
            "+cells-set",
            "--spreadsheet-token",
            target.spreadsheet_token,
            "--sheet-id",
            sheet_id,
            "--range",
            range_text,
            "--cells",
            "-",
        ],
        input_text=json.dumps(header_cells, ensure_ascii=False),
    )
    time.sleep(delay_seconds)

    for merge in layout.get("merged_cells", []) if isinstance(layout, dict) else []:
        merge_range = str(merge.get("range") or "") if isinstance(merge, dict) else ""
        if merge_range:
            cli.sheets(
                [
                    "+cells-merge",
                    "--spreadsheet-token",
                    target.spreadsheet_token,
                    "--sheet-id",
                    sheet_id,
                    "--range",
                    merge_range,
                    "--merge-type",
                    "all",
                ]
            )
            time.sleep(delay_seconds)

    for row_height in layout.get("row_heights", []) if isinstance(layout, dict) else []:
        if not isinstance(row_height, dict):
            continue
        rows = str(row_height.get("rows") or "")
        resize_type = str(row_height.get("type") or "")
        if not rows:
            continue
        args = [
            "+rows-resize",
            "--spreadsheet-token",
            target.spreadsheet_token,
            "--sheet-id",
            sheet_id,
            "--range",
            rows,
        ]
        if resize_type in {"custom", "pixel"} and row_height.get("height"):
            args.extend(["--type", "pixel", "--size", str(row_height["height"])])
        elif resize_type == "standard":
            args.extend(["--type", "standard"])
        else:
            args.extend(["--type", "auto"])
        cli.sheets(args)
        time.sleep(delay_seconds)

    for col_width in layout.get("column_widths", []) if isinstance(layout, dict) else []:
        if not isinstance(col_width, dict):
            continue
        cols = str(col_width.get("cols") or "")
        resize_type = str(col_width.get("type") or "")
        if resize_type not in {"custom", "pixel"} or not cols or not col_width.get("width"):
            continue
        cli.sheets(
            [
                "+cols-resize",
                "--spreadsheet-token",
                target.spreadsheet_token,
                "--sheet-id",
                sheet_id,
                "--range",
                cols,
                "--type",
                "pixel",
                "--size",
                str(col_width["width"]),
            ]
        )
        time.sleep(delay_seconds)


def refresh_existing_header_format(
    cli: LarkCli,
    publish: OperatorPublish,
    header_cells: list[list[dict[str, Any]]],
    header_layout: dict[str, Any],
    header_row_count: int,
    column_count: int,
    delay_seconds: float,
) -> None:
    if publish.target is None or not publish.sheet_id:
        raise NongfuError(f"{publish.operator} 缺少既有 sheet，无法补刷表头格式。")
    apply_header_format(
        cli,
        publish.target,
        publish.sheet_id,
        header_cells,
        header_layout,
        header_row_count,
        column_count,
        delay_seconds,
    )
    publish.status = "format_refreshed"


def create_sheet(cli: LarkCli, target: TargetWorkbook, title: str, row_count: int, column_count: int) -> str:
    result = cli.sheets(
        [
            "+sheet-create",
            "--spreadsheet-token",
            target.spreadsheet_token,
            "--title",
            title,
            "--row-count",
            str(max(row_count, 200)),
            "--col-count",
            str(max(column_count, 20)),
        ]
    )

    def walk(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("sheet_id", "sheetId", "id", "reference_id"):
                if value.get(key):
                    return str(value[key])
            for item in value.values():
                found = walk(item)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = walk(item)
                if found:
                    return found
        return ""

    sheet_id = walk(result)
    if sheet_id:
        return sheet_id
    info = workbook_info(cli, token=target.spreadsheet_token)
    for sheet in sheet_records(info):
        if str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "") == title:
            return str(sheet.get("sheet_id") or sheet.get("id") or sheet.get("reference_id") or "")
    raise NongfuError(f"{target.operator} 创建 sheet 后无法获取 sheet_id。")


def target_sheet_link(target: TargetWorkbook, sheet_id: str) -> str:
    base = target.url.split("?", 1)[0] if target.url else f"https://hohscmgpby.feishu.cn/sheets/{target.spreadsheet_token}"
    return f"{base}?sheet={sheet_id}"


def write_and_verify(
    cli: LarkCli,
    publish: OperatorPublish,
    sheet_name: str,
    rows: list[list[str]],
    column_count: int,
    header_row_count: int,
    header_cells: list[list[dict[str, Any]]] | None,
    header_layout: dict[str, Any] | None,
    preserve_header_format: bool,
    delay_seconds: float,
) -> None:
    if publish.target is None:
        raise NongfuError(f"{publish.operator} 缺少目标表格。")
    sheet_id = create_sheet(cli, publish.target, sheet_name, len(rows), column_count)
    time.sleep(delay_seconds)
    cli.sheets(
        [
            "+csv-put",
            "--spreadsheet-token",
            publish.target.spreadsheet_token,
            "--sheet-id",
            sheet_id,
            "--start-cell",
            "A1",
            "--csv",
            "-",
        ],
        input_text=rows_to_csv(rows, column_count),
    )
    time.sleep(delay_seconds)
    if preserve_header_format and header_cells is not None and header_layout is not None:
        apply_header_format(
            cli,
            publish.target,
            sheet_id,
            header_cells,
            header_layout,
            header_row_count,
            column_count,
            delay_seconds,
        )
    verify = cli.sheets(
        [
            "+csv-get",
            "--spreadsheet-token",
            publish.target.spreadsheet_token,
            "--sheet-id",
            sheet_id,
            "--range",
            a1_range(len(rows), column_count),
        ]
    )
    data = verify.get("data") if isinstance(verify.get("data"), dict) else {}
    actual = parse_annotated_csv(str(data.get("annotated_csv") or ""))
    expected = [pad_row(row, column_count) for row in rows]
    actual_padded = [pad_row(row, column_count) for row in actual]
    if len(actual_padded) != len(expected):
        raise NongfuError(f"{publish.operator} 写后验证行数不一致：预期 {len(expected)}，实际 {len(actual_padded)}。")
    # The format copy may restore A1 as rich text; csv-get should still expose the same text.
    for row_index, expected_row in enumerate(expected):
        actual_row = actual_padded[row_index]
        if actual_row[: min(3, column_count)] != expected_row[: min(3, column_count)]:
            raise NongfuError(f"{publish.operator} 写后验证失败：第 {row_index + 1} 行品牌/城市/辅助列不一致。")
    publish.sheet_id = sheet_id
    publish.link = target_sheet_link(publish.target, sheet_id)
    publish.status = "created"


def load_notification_template(args: argparse.Namespace) -> str:
    if args.notification_template_file:
        return Path(args.notification_template_file).expanduser().read_text(encoding="utf-8")
    if args.notification_template:
        return args.notification_template
    return DEFAULT_NOTIFICATION_TEMPLATE


def build_notifications(publishes: list[OperatorPublish], args: argparse.Namespace) -> dict[str, str]:
    template = load_notification_template(args)
    notices: dict[str, str] = {}
    for publish in publishes:
        if publish.status != "created" and not publish.link:
            continue
        body = template.format(
            operator=publish.operator,
            link=publish.link,
            sheet_name=args.target_sheet_name or args.source_sheet,
            sop_url=args.sop_url,
            deadline=args.deadline,
            material_note=args.material_note,
            topic_label=args.topic_label,
        ).strip()
        notices[publish.operator] = f"【{publish.operator}】\n{body}"
    return notices


def check_notice_terms(text: str) -> dict[str, Any]:
    checker = PROJECT_ROOT / ".workbuddy" / "skills" / "lx-tongzhi" / "scripts" / "check_terms.py"
    if not checker.exists():
        return {"ok": False, "message": f"缺少禁词检查脚本: {checker}"}
    proc = subprocess.run(
        [sys.executable, str(checker), "--audience", "shangjia", "--text", text],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def default_output_paths(config: dict[str, Any], source_sheet_name: str) -> tuple[Path, Path]:
    nongfu = config.get("lx_nongfu", {})
    workspace = "workspace/12农夫协作"
    if isinstance(nongfu, dict) and nongfu.get("workspace_dir"):
        workspace = str(nongfu["workspace_dir"])
    output_dir = Path(workspace)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir = output_dir / "输出"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_sheet = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", source_sheet_name).strip("_") or "nongfu"
    return output_dir / f"{stamp}_{safe_sheet}_publish_summary.json", output_dir / f"{stamp}_{safe_sheet}_notifications.md"


def write_outputs(
    result: dict[str, Any],
    notifications: dict[str, str],
    args: argparse.Namespace,
    config: dict[str, Any],
    source_sheet_name: str,
) -> dict[str, str]:
    if args.no_output_files:
        return {}
    default_json, default_md = default_output_paths(config, source_sheet_name)
    json_path = Path(args.output_json).expanduser() if args.output_json else default_json
    md_path = Path(args.output_markdown).expanduser() if args.output_markdown else default_md
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path
    if not md_path.is_absolute():
        md_path = PROJECT_ROOT / md_path
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n\n".join(notifications.values()) + ("\n" if notifications else ""), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lx-nongfu 飞书大文档拆分发布命令。")
    parser.add_argument("--source-url", required=True, help="飞书普通电子表格大文档 URL")
    parser.add_argument("--source-sheet", default="", help="大文档 sheet 名；不填且仅 1 个 sheet 时自动使用")
    parser.add_argument("--source-range", default="", help="读取范围；默认按工作簿行列元数据读取全表")
    parser.add_argument("--contact-person", default="", help="对接人；不填则使用 config/fog_config.yaml 的 lx_nongfu.default_contact_persons[0]")
    parser.add_argument("--operator-root-folder-token", default="", help="运营主体文件夹所在父文件夹 token")
    parser.add_argument("--operator-root-folder-url", default="", help="运营主体文件夹所在父文件夹 URL")
    parser.add_argument("--operator-folder-template", default="", help="运营主体文件夹名模板；默认读取配置或 {operator}-运营主体")
    parser.add_argument("--target-table-template", default="", help="目标普通表格名模板；默认读取配置或 {operator}-日常信息")
    parser.add_argument("--target-sheet-name", default="", help="目标新建 sheet 名；默认等于 source sheet 名")
    parser.add_argument("--header-row", type=int, default=0, help="品牌/城市表头所在行，1-based；默认自动识别")
    parser.add_argument("--max-header-scan-rows", type=int, default=10)
    parser.add_argument("--operator-brand-limit", type=int, default=1000)
    parser.add_argument("--if-sheet-exists", choices=["fail", "skip"], default="fail")
    parser.add_argument("--include-empty-operators", action="store_true", help="也为 0 数据主体创建只有表头的 sheet")
    parser.add_argument("--preserve-header-format", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--refresh-existing-header-format",
        action="store_true",
        help="配合 --confirmed --if-sheet-exists skip 使用：同名 sheet 已存在时只补刷表头格式，不重写数据",
    )
    parser.add_argument("--write-delay-seconds", type=float, default=2.5)
    parser.add_argument("--confirmed", action="store_true", help="实际写入飞书；不加时只 dry-run")
    parser.add_argument("--lark-cli", default="")
    parser.add_argument("--identity", choices=["user", "bot"], default="user")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--notification-template", default="", help="通知模板文本，可用 {operator}/{link}/{sheet_name}/{sop_url}/{deadline}/{material_note}/{topic_label}")
    parser.add_argument("--notification-template-file", default="")
    parser.add_argument("--topic-label", default="本期（0610）飞涨卡售卡")
    parser.add_argument("--sop-url", default=DEFAULT_SOP_URL)
    parser.add_argument("--deadline", default="6月10日下午18:00")
    parser.add_argument("--material-note", default="见压缩包")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-markdown", default="")
    parser.add_argument("--no-output-files", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    nongfu = config.get("lx_nongfu", {}) if isinstance(config.get("lx_nongfu"), dict) else {}
    operator_doc = nongfu.get("operator_doc", {}) if isinstance(nongfu.get("operator_doc"), dict) else {}

    contact_person = args.contact_person
    if not contact_person:
        defaults = configured_list(config, ["lx_nongfu", "default_contact_persons"], [])
        contact_person = defaults[0] if defaults else ""
    if not contact_person:
        raise NongfuError("缺少 --contact-person，且配置里没有 lx_nongfu.default_contact_persons。")

    root_folder_token = resolve_operator_root_folder(args, config, contact_person)
    if not root_folder_token:
        raise NongfuError(
            "缺少运营主体根文件夹。请传 --operator-root-folder-url，"
            "或在 config/fog_config.yaml 的 lx_nongfu.operator_doc.contact_person_root_folders 中按对接人配置。"
        )

    target_table_template = args.target_table_template or str(
        operator_doc.get("target_table_name_template") or "{operator}-日常信息"
    )
    operator_folder_template = args.operator_folder_template or str(
        operator_doc.get("operator_folder_name_template") or "{operator}-运营主体"
    )

    cli = LarkCli(resolve_lark_cli(config, args.lark_cli), identity=args.identity, timeout=args.timeout)
    source = choose_source_sheet(cli, args.source_url, args.source_sheet)
    target_sheet_name = args.target_sheet_name or source.sheet_name
    rows = read_sheet_rows(cli, source, args.source_range)
    if not rows:
        raise NongfuError("大文档没有读到任何行。")

    brand_fields = configured_list(
        config,
        ["lx_nongfu", "large_doc", "brand_fields"],
        ["品牌", "品牌名称", "商家", "商家名称", "合作品牌", "合作商家", "运力品牌", "brand_name"],
    )
    city_fields = configured_list(
        config,
        ["lx_nongfu", "large_doc", "city_fields"],
        ["城市", "城市名称", "注册城市", "所属城市", "所属城市名称", "城市名", "city_name"],
    )
    header_row_number = args.header_row or auto_header_row(rows, brand_fields, city_fields, args.max_header_scan_rows)
    if header_row_number < 1 or header_row_number > len(rows):
        raise NongfuError(f"--header-row 超出已读取范围: {header_row_number}")
    header_rows = rows[:header_row_number]
    header = rows[header_row_number - 1]
    brand_col = find_column(header, brand_fields, "品牌")
    city_col = find_column(header, city_fields, "城市")
    column_count = max(source.column_count or 0, max(len(row) for row in rows), 1)

    mapping, conflicts, mapping_row_count = load_operator_mapping(contact_person, args.operator_brand_limit)
    if conflicts:
        raise NongfuError("operator_brand 存在品牌城市归属冲突: " + json.dumps(conflicts, ensure_ascii=False))
    groups, out_of_scope, valid_data_rows = group_rows_by_operator(rows, header_row_number, brand_col, city_col, mapping)
    operators = sorted(set(mapping.values()))
    targets = resolve_targets(
        cli,
        root_folder_token,
        operators,
        operator_folder_template,
        target_table_template,
    )

    publishes: list[OperatorPublish] = []
    for operator in operators:
        data_rows = groups.get(operator, [])
        if not data_rows and not args.include_empty_operators:
            publishes.append(OperatorPublish(operator=operator, data_rows=[], status="skipped", reason="no_matched_rows"))
            continue
        publish = OperatorPublish(operator=operator, data_rows=data_rows)
        target = targets.get(operator)
        if not target:
            publish.status = "blocked"
            publish.reason = "target_workbook_not_found"
            publishes.append(publish)
            continue
        publish.target = target
        existing_sheet_id = target.existing_sheets.get(target_sheet_name, "")
        if existing_sheet_id:
            if args.if_sheet_exists == "skip":
                publish.status = "skipped"
                publish.reason = "target_sheet_exists"
                publish.sheet_id = existing_sheet_id
                publish.link = target_sheet_link(target, existing_sheet_id)
            else:
                publish.status = "blocked"
                publish.reason = "target_sheet_exists"
            publishes.append(publish)
            continue
        publish.status = "ready"
        publishes.append(publish)

    blocked = [item for item in publishes if item.status == "blocked"]
    if blocked and args.confirmed:
        detail = [{"operator": item.operator, "reason": item.reason} for item in blocked]
        raise NongfuError("存在无法写入的主体，已停止: " + json.dumps(detail, ensure_ascii=False))

    header_cells: list[list[dict[str, Any]]] | None = None
    header_layout: dict[str, Any] | None = None
    if args.confirmed and args.preserve_header_format:
        header_cells, header_layout = read_header_format(cli, source, header_row_number, column_count)

    if args.confirmed:
        for publish in publishes:
            if publish.status != "ready":
                continue
            all_rows = header_rows + publish.data_rows
            write_and_verify(
                cli,
                publish,
                target_sheet_name,
                all_rows,
                column_count,
                header_row_number,
                header_cells,
                header_layout,
                args.preserve_header_format,
                args.write_delay_seconds,
            )
        if args.refresh_existing_header_format and args.preserve_header_format:
            if header_cells is None or header_layout is None:
                header_cells, header_layout = read_header_format(cli, source, header_row_number, column_count)
            for publish in publishes:
                if publish.reason == "target_sheet_exists" and publish.sheet_id and publish.target:
                    refresh_existing_header_format(
                        cli,
                        publish,
                        header_cells,
                        header_layout,
                        header_row_number,
                        column_count,
                        args.write_delay_seconds,
                    )

    # In dry-run, build preview links from target workbook URL only when possible.
    for publish in publishes:
        if publish.status == "ready" and publish.target and not args.confirmed:
            publish.link = publish.target.url
        if publish.status == "created" and publish.link:
            continue

    notifications = build_notifications([item for item in publishes if item.link], args)
    notice_text = "\n\n".join(notifications.values())
    term_check = check_notice_terms(notice_text) if notice_text else {"ok": True, "stdout": "无通知内容"}

    summary_items = []
    for publish in publishes:
        target_url = publish.target.url if publish.target else ""
        summary_items.append(
            {
                "operator": publish.operator,
                "status": publish.status,
                "reason": publish.reason,
                "data_rows": len(publish.data_rows),
                "write_rows_including_headers": len(publish.data_rows) + header_row_number if publish.data_rows else 0,
                "target_url": target_url,
                "sheet_id": publish.sheet_id,
                "link": publish.link,
            }
        )

    result: dict[str, Any] = {
        "ok": not blocked,
        "dry_run": not args.confirmed,
        "source": {
            "url": source.url,
            "sheet_name": source.sheet_name,
            "sheet_id": source.sheet_id,
            "read_rows": len(rows),
            "valid_data_rows": valid_data_rows,
            "header_row": header_row_number,
            "column_count": column_count,
        },
        "contact_person": contact_person,
        "db_mapping_rows": mapping_row_count,
        "matched_rows": sum(len(item.data_rows) for item in publishes),
        "out_of_scope_rows": len(out_of_scope),
        "operators_total": len(operators),
        "operators_ready_or_created": sum(1 for item in publishes if item.status in {"ready", "created", "format_refreshed"}),
        "operators_skipped": sum(1 for item in publishes if item.status == "skipped"),
        "operators_blocked": sum(1 for item in publishes if item.status == "blocked"),
        "target_sheet_name": target_sheet_name,
        "preserve_header_format": bool(args.preserve_header_format),
        "summary": summary_items,
        "sample_out_of_scope": out_of_scope[:20],
        "notifications": notifications,
        "term_check": term_check,
    }
    output_files = write_outputs(result, notifications, args, config, source.sheet_name)
    result["output_files"] = output_files

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NongfuError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
