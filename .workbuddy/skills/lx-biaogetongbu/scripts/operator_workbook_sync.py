#!/usr/bin/env python3
"""Sync operator-owned Feishu workbooks back to recurring master sheets.

Default behavior is dry-run. Use --confirmed to write Feishu ordinary Sheets.
The command is intentionally value-first and refuses image-risk writes unless
the caller explicitly accepts that risk.
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


class OperatorSyncError(RuntimeError):
    """Expected user-facing sync failure."""


@dataclass
class SheetRef:
    token: str
    url: str
    sheet_id: str
    sheet_name: str
    row_count: int
    column_count: int
    float_image_count: int = 0


@dataclass
class TableRow:
    row_number: int
    values: dict[str, str]


@dataclass
class SheetTable:
    label: str
    ref: SheetRef
    headers: dict[str, int]
    rows: list[TableRow]
    last_nonblank_row: int


@dataclass
class OperatorWorkbook:
    operator: str
    folder_token: str
    token: str
    url: str
    name: str


@dataclass
class CellUpdate:
    operator: str
    token: str
    sheet_id: str
    sheet_name: str
    row_number: int
    column_number: int
    column_name: str
    old_value: str
    new_value: str
    reason: str

    @property
    def cell(self) -> str:
        return f"{col_to_a1(self.column_number)}{self.row_number}"


@dataclass
class AppendRow:
    operator: str
    source_row_number: int
    target_row_number: int
    key_text: str
    values_by_column: dict[int, str]


@dataclass
class BuildContext:
    profile: dict[str, Any]
    master: SheetTable
    sources: list[tuple[OperatorWorkbook, SheetTable]]
    operators_requested: list[str]
    missing_targets: list[dict[str, str]] = field(default_factory=list)
    missing_headers: list[dict[str, Any]] = field(default_factory=list)
    image_risks: list[dict[str, Any]] = field(default_factory=list)
    skipped_sources: list[dict[str, str]] = field(default_factory=list)


PROJECT_ROOT = Path.cwd().resolve()
for candidate in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
    if (candidate / ".workbuddy" / "skills").is_dir() and (candidate / "config").is_dir():
        PROJECT_ROOT = candidate
        break

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = SKILL_ROOT / "assets" / "profiles"
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
ROW_PREFIX_RE = re.compile(r"^\[row=(\d+)]\s?(.*)$")


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
    raise OperatorSyncError("未找到 lark-cli；请先在 WorkBuddy 安装并授权飞书连接器。")


def parse_json_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    start = text.find("{")
    if start < 0:
        raise OperatorSyncError(f"命令没有返回 JSON: {text[:500]}")
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
        raise OperatorSyncError(f"lark-cli 执行失败: {' '.join(args)}\n{last_detail[:2000]}")

    def sheets(self, args: list[str], *, input_text: str | None = None, retries: int = 1) -> dict[str, Any]:
        return self.run(["sheets", *args, "--as", self.identity, "--json"], input_text=input_text, retries=retries)

    def drive(self, args: list[str], *, retries: int = 1) -> dict[str, Any]:
        return self.run(["drive", *args, "--as", self.identity, "--json"], retries=retries)


def configured_map(config: dict[str, Any], path: list[str]) -> dict[str, Any]:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def configured_list(config: dict[str, Any], path: list[str]) -> list[str]:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    if not isinstance(current, list):
        return []
    return [str(item) for item in current if str(item).strip()]


def configured_str(config: dict[str, Any], path: list[str]) -> str:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "").strip()


def extract_sheet_token(url_or_token: str) -> str:
    value = url_or_token.strip()
    match = re.search(r"/(?:sheets|spreadsheets)/([^/?#]+)", value)
    return match.group(1) if match else value


def extract_folder_token(url_or_token: str) -> str:
    value = url_or_token.strip()
    match = re.search(r"/drive/folder/([^/?#]+)", value)
    return match.group(1) if match else value


def col_to_a1(column: int) -> str:
    if column < 1:
        raise OperatorSyncError(f"列号必须从 1 开始: {column}")
    result = ""
    current = column
    while current:
        current, rem = divmod(current - 1, 26)
        result = chr(65 + rem) + result
    return result


def a1_range(row_count: int, column_count: int) -> str:
    return f"A1:{col_to_a1(max(column_count, 1))}{max(row_count, 1)}"


def rows_to_csv(rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def spreadsheet_locator(value: str) -> list[str]:
    if value.startswith(("http://", "https://")):
        return ["--url", value]
    return ["--spreadsheet-token", value]


def file_type(item: dict[str, Any]) -> str:
    return str(item.get("type") or item.get("obj_type") or item.get("file_type") or "")


def file_url(item: dict[str, Any]) -> str:
    return str(item.get("url") or item.get("file_url") or item.get("link") or "")


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


def workbook_info(cli: LarkCli, url_or_token: str) -> list[dict[str, Any]]:
    result = cli.sheets(["+workbook-info", *spreadsheet_locator(url_or_token)])
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    sheets = data.get("sheets", []) if isinstance(data, dict) else []
    return [item for item in sheets if isinstance(item, dict)]


def select_sheet(sheets: list[dict[str, Any]], expected_name: str, label: str) -> SheetRef:
    if not sheets:
        raise OperatorSyncError(f"{label} 没有可读取的 sheet。")
    selected: dict[str, Any] | None = None
    if expected_name:
        for sheet in sheets:
            title = str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "")
            if title == expected_name:
                selected = sheet
                break
        if selected is None:
            names = [str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "") for sheet in sheets]
            raise OperatorSyncError(f"{label} 没有 sheet: {expected_name}；可用 sheet: {', '.join(names)}")
    elif len(sheets) == 1:
        selected = sheets[0]
    else:
        names = [str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "") for sheet in sheets]
        raise OperatorSyncError(f"{label} 有多个 sheet，请在 profile 或参数指定 sheet 名: {', '.join(names)}")

    title = str(selected.get("sheet_name") or selected.get("title") or selected.get("name") or "")
    sheet_id = str(selected.get("sheet_id") or selected.get("id") or selected.get("reference_id") or "")
    if not title or not sheet_id:
        raise OperatorSyncError(f"{label} sheet 元数据不完整: {selected}")
    return SheetRef(
        token="",
        url="",
        sheet_id=sheet_id,
        sheet_name=title,
        row_count=int(selected.get("row_count") or selected.get("rowCount") or 1),
        column_count=int(selected.get("column_count") or selected.get("columnCount") or 1),
        float_image_count=int(selected.get("float_image_count") or selected.get("floatImageCount") or 0),
    )


def parse_annotated_csv(text: str) -> list[list[str]]:
    lines: list[str] = []
    for line in text.splitlines():
        match = ROW_PREFIX_RE.match(line)
        lines.append(match.group(2) if match else line)
    if not lines:
        return []
    return [list(row) for row in csv.reader(io.StringIO("\n".join(lines)))]


def read_csv_rows(cli: LarkCli, ref: SheetRef) -> tuple[list[int], list[list[str]]]:
    result = cli.sheets(
        [
            "+csv-get",
            *spreadsheet_locator(ref.url or ref.token),
            "--sheet-id",
            ref.sheet_id,
            "--range",
            a1_range(ref.row_count, ref.column_count),
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    rows = parse_annotated_csv(str(data.get("annotated_csv") or ""))
    row_indices = data.get("row_indices") if isinstance(data, dict) else []
    if not isinstance(row_indices, list) or len(row_indices) != len(rows):
        row_indices = list(range(1, len(rows) + 1))
    return [int(item) for item in row_indices], rows


def normalize_header(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalize_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def row_cell(row: list[str], column_number: int) -> str:
    index = column_number - 1
    return normalize_value(row[index]) if index < len(row) else ""


def row_is_blank(row_values: dict[str, str]) -> bool:
    return all(value == "" for value in row_values.values())


def read_table(
    cli: LarkCli,
    url_or_token: str,
    *,
    expected_sheet_name: str = "",
    header_row: int = 1,
    label: str,
) -> SheetTable:
    token = extract_sheet_token(url_or_token)
    sheets = workbook_info(cli, url_or_token)
    ref = select_sheet(sheets, expected_sheet_name, label)
    ref.token = token
    ref.url = url_or_token if url_or_token.startswith(("http://", "https://")) else ""
    row_indices, rows = read_csv_rows(cli, ref)
    header_index = None
    for index, row_number in enumerate(row_indices):
        if row_number == header_row:
            header_index = index
            break
    if header_index is None or header_index >= len(rows):
        raise OperatorSyncError(f"{label} 没有读到第 {header_row} 行表头。")

    headers: dict[str, int] = {}
    duplicates: list[str] = []
    for offset, value in enumerate(rows[header_index], start=1):
        name = normalize_header(value)
        if not name:
            continue
        if name in headers:
            duplicates.append(name)
            continue
        headers[name] = offset
    if duplicates:
        raise OperatorSyncError(f"{label} 表头存在重复列: {', '.join(sorted(set(duplicates)))}")
    if not headers:
        raise OperatorSyncError(f"{label} 第 {header_row} 行没有可用表头。")

    records: list[TableRow] = []
    last_nonblank = header_row
    for row_number, row in zip(row_indices, rows):
        if row_number <= header_row:
            continue
        values = {header: row_cell(row, col) for header, col in headers.items()}
        if row_is_blank(values):
            continue
        records.append(TableRow(row_number=row_number, values=values))
        last_nonblank = max(last_nonblank, row_number)
    return SheetTable(label=label, ref=ref, headers=headers, rows=records, last_nonblank_row=last_nonblank)


def parse_csv_arg(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for item in str(raw).split(","):
            value = item.strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
    return result


def load_profile(value: str) -> dict[str, Any]:
    raw = value.strip()
    if not raw:
        raise OperatorSyncError("缺少 --scenario 或 --profile。")
    path = Path(raw).expanduser()
    if not path.suffix:
        path = PROFILE_DIR / f"{raw}.json"
    elif not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        raise OperatorSyncError(f"profile 不存在: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise OperatorSyncError(f"profile 必须是 JSON object: {path}")
    data.setdefault("_profile_path", str(path))
    return data


def profile_list(profile: dict[str, Any], key: str) -> list[str]:
    value = profile.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def resolve_master_url(args: argparse.Namespace, config: dict[str, Any], profile: dict[str, Any]) -> str:
    if args.master_url:
        return args.master_url.strip()
    scenario_id = str(profile.get("scenario_id") or args.scenario or "").strip()
    for path in (
        ["lx_biaogetongbu", "operator_sync", "scenarios", scenario_id, "master_url"],
        ["lx_biaogetongbu", "operator_sync", scenario_id, "master_url"],
    ):
        value = configured_str(config, path)
        if value:
            return value
    value = str(profile.get("master_url") or "").strip()
    if value:
        return value
    raise OperatorSyncError("缺少大表格链接。请传 --master-url，或在本机 config/fog_config.yaml 中配置。")


def resolve_contact_person(args: argparse.Namespace, config: dict[str, Any]) -> str:
    if args.contact_person:
        return args.contact_person.strip()
    defaults = configured_list(config, ["lx_biaogetongbu", "default_contact_persons"])
    if not defaults:
        defaults = configured_list(config, ["lx_nongfu", "default_contact_persons"])
    return defaults[0] if defaults else ""


def root_from_mapping(mapping: dict[str, Any], contact_person: str) -> str:
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

    operator_sync = configured_map(config, ["lx_biaogetongbu", "operator_sync"])
    mapping = operator_sync.get("contact_person_root_folders")
    if isinstance(mapping, dict):
        configured = root_from_mapping(mapping, contact_person)
        if configured:
            return extract_folder_token(configured)
    configured = str(operator_sync.get("operator_root_folder_url") or operator_sync.get("operator_root_folder_token") or "")
    if configured:
        return extract_folder_token(configured)

    nongfu_operator_doc = configured_map(config, ["lx_nongfu", "operator_doc"])
    mapping = nongfu_operator_doc.get("contact_person_root_folders")
    if isinstance(mapping, dict):
        configured = root_from_mapping(mapping, contact_person)
        if configured:
            return extract_folder_token(configured)
    configured = str(
        nongfu_operator_doc.get("operator_root_folder_url") or nongfu_operator_doc.get("operator_root_folder_token") or ""
    )
    return extract_folder_token(configured) if configured else ""


def fill_template(template: str, operator: str) -> str:
    return template.format(operator=operator)


def operator_from_folder_name(folder_name: str, template: str) -> str:
    if "{operator}" not in template:
        return ""
    prefix, suffix = template.split("{operator}", 1)
    if not folder_name.startswith(prefix) or not folder_name.endswith(suffix):
        return ""
    end = len(folder_name) - len(suffix) if suffix else len(folder_name)
    return folder_name[len(prefix) : end]


def resolve_operator_workbooks(
    cli: LarkCli,
    root_folder_token: str,
    operators: list[str],
    *,
    operator_folder_template: str,
    target_table_template: str,
) -> tuple[list[OperatorWorkbook], list[dict[str, str]], list[str]]:
    root_files = list_drive_files(cli, root_folder_token)
    folder_by_operator: dict[str, str] = {}
    for item in root_files:
        if file_type(item) != "folder":
            continue
        name = str(item.get("name") or "")
        operator = operator_from_folder_name(name, operator_folder_template)
        token = str(item.get("token") or item.get("file_token") or "")
        if operator and token:
            folder_by_operator[operator] = token

    if not operators:
        operators = sorted(folder_by_operator)
    missing: list[dict[str, str]] = []
    workbooks: list[OperatorWorkbook] = []
    for operator in operators:
        folder_token = folder_by_operator.get(operator, "")
        if not folder_token:
            missing.append({"operator": operator, "reason": "operator_folder_not_found"})
            continue
        target_name = fill_template(target_table_template, operator)
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
            missing.append({"operator": operator, "reason": "operator_workbook_not_found", "target_name": target_name})
            continue
        url = file_url(target_file)
        token = extract_sheet_token(url) if url else str(target_file.get("token") or target_file.get("file_token") or "")
        workbooks.append(
            OperatorWorkbook(
                operator=operator,
                folder_token=folder_token,
                token=token,
                url=url,
                name=target_name,
            )
        )
    return workbooks, missing, operators


def key_for(row: TableRow, columns: list[str]) -> tuple[str, ...]:
    return tuple(normalize_value(row.values.get(column)) for column in columns)


def key_text(key: tuple[str, ...]) -> str:
    return " | ".join(key)


def ensure_columns(table: SheetTable, columns: list[str], label: str) -> list[str]:
    return [column for column in columns if column not in table.headers]


def build_key_index(table: SheetTable, key_columns: list[str]) -> tuple[dict[tuple[str, ...], TableRow], list[dict[str, Any]]]:
    index: dict[tuple[str, ...], TableRow] = {}
    duplicates: list[dict[str, Any]] = []
    for row in table.rows:
        key = key_for(row, key_columns)
        if not any(key):
            continue
        if key in index:
            duplicates.append({"key": key_text(key), "row_number": row.row_number, "first_row_number": index[key].row_number})
            continue
        index[key] = row
    return index, duplicates


def next_status_column(table: SheetTable, status_column: str) -> int:
    if status_column in table.headers:
        return table.headers[status_column]
    return max(table.headers.values(), default=0) + 1


def plain_cell_risk(cell: Any) -> bool:
    if not cell:
        return False
    if not isinstance(cell, dict):
        return True
    extra_keys = set(cell) - {"value"}
    if extra_keys:
        return True
    value = cell.get("value")
    return isinstance(value, (dict, list))


def inspect_image_cells(
    cli: LarkCli,
    table: SheetTable,
    image_columns: list[str],
    *,
    row_numbers: set[int] | None = None,
    max_examples: int = 20,
) -> list[dict[str, Any]]:
    available = [column for column in image_columns if column in table.headers]
    if not available or not table.rows:
        return []
    min_col = min(table.headers[column] for column in available)
    max_col = max(table.headers[column] for column in available)
    start_row = min(row.row_number for row in table.rows)
    end_row = max(row.row_number for row in table.rows)
    result = cli.sheets(
        [
            "+cells-get",
            *spreadsheet_locator(table.ref.url or table.ref.token),
            "--sheet-id",
            table.ref.sheet_id,
            "--range",
            f"{col_to_a1(min_col)}{start_row}:{col_to_a1(max_col)}{end_row}",
            "--include",
            "value",
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    ranges = data.get("ranges", []) if isinstance(data, dict) else []
    if not ranges or not isinstance(ranges[0], dict):
        return []
    cells = ranges[0].get("cells", [])
    row_indices = ranges[0].get("row_indices", [])
    col_indices = ranges[0].get("col_indices", [])
    if not isinstance(cells, list):
        return []
    risks: list[dict[str, Any]] = []
    for row_offset, row_cells in enumerate(cells):
        if not isinstance(row_cells, list):
            continue
        row_number = row_indices[row_offset] if row_offset < len(row_indices) else start_row + row_offset
        if row_numbers is not None and int(row_number) not in row_numbers:
            continue
        for col_offset, cell in enumerate(row_cells):
            col_letter = col_indices[col_offset] if col_offset < len(col_indices) else col_to_a1(min_col + col_offset)
            if not plain_cell_risk(cell):
                continue
            risks.append({"row_number": row_number, "column": col_letter, "cell": f"{col_letter}{row_number}", "cell_keys": sorted(cell) if isinstance(cell, dict) else []})
            if len(risks) >= max_examples:
                return risks
    return risks


def common_append_columns(source: SheetTable, master: SheetTable, profile: dict[str, Any]) -> list[str]:
    configured = profile_list(profile, "append_columns")
    if configured:
        return configured
    return [
        header
        for header, _ in sorted(master.headers.items(), key=lambda item: item[1])
        if header in source.headers
    ]


def make_update(
    *,
    operator: str,
    table: SheetTable,
    row_number: int,
    column_number: int,
    column_name: str,
    old_value: str,
    new_value: str,
    reason: str,
) -> CellUpdate:
    return CellUpdate(
        operator=operator,
        token=table.ref.token,
        sheet_id=table.ref.sheet_id,
        sheet_name=table.ref.sheet_name,
        row_number=row_number,
        column_number=column_number,
        column_name=column_name,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
    )


def build_plan(ctx: BuildContext) -> dict[str, Any]:
    profile = ctx.profile
    status_column = str(profile.get("status_column") or "是否提交")
    submitted_value = str(profile.get("submitted_value") or "填写已提交")
    key_columns = profile_list(profile, "key_columns")
    required_columns = profile_list(profile, "required_columns")
    image_columns = profile_list(profile, "image_columns")

    if not key_columns:
        raise OperatorSyncError("profile.key_columns 不能为空。")
    missing_master_key = ensure_columns(ctx.master, key_columns, "大表格")
    if missing_master_key:
        ctx.missing_headers.append({"table": "master", "missing": missing_master_key})

    master_index, _ = build_key_index(ctx.master, key_columns) if not missing_master_key else ({}, [])
    master_duplicate_blockers: list[dict[str, Any]] = []
    append_rows: list[AppendRow] = []
    status_updates: list[CellUpdate] = []
    status_header_updates: list[CellUpdate] = []
    result_updates: list[CellUpdate] = []
    skipped: list[dict[str, Any]] = []
    already_in_master: list[dict[str, Any]] = []
    source_duplicates: list[dict[str, Any]] = []
    seen_source_keys: dict[tuple[str, ...], tuple[str, int]] = {}
    next_master_row = ctx.master.last_nonblank_row + 1

    for workbook, source in ctx.sources:
        needed = sorted(set(required_columns + key_columns))
        missing_source = ensure_columns(source, needed, workbook.operator)
        append_cols = common_append_columns(source, ctx.master, profile)
        missing_append = [column for column in append_cols if column not in source.headers or column not in ctx.master.headers]
        if missing_source or missing_append:
            ctx.missing_headers.append(
                {
                    "operator": workbook.operator,
                    "missing_required": missing_source,
                    "missing_append": missing_append,
                }
            )
            continue

        status_col_num = next_status_column(source, status_column)
        if status_column not in source.headers:
            status_header_updates.append(
                make_update(
                    operator=workbook.operator,
                    table=source,
                    row_number=1,
                    column_number=status_col_num,
                    column_name=status_column,
                    old_value="",
                    new_value=status_column,
                    reason="add_status_header",
                )
            )

        append_source_row_numbers: set[int] = set()
        for row in source.rows:
            current_status = normalize_value(row.values.get(status_column))
            if current_status == submitted_value:
                skipped.append(
                    {
                        "operator": workbook.operator,
                        "row_number": row.row_number,
                        "reason": "source_already_submitted",
                    }
                )
                continue
            key = key_for(row, key_columns)
            if not any(key):
                skipped.append(
                    {
                        "operator": workbook.operator,
                        "row_number": row.row_number,
                        "reason": "empty_key",
                    }
                )
                continue
            if key in seen_source_keys:
                first_operator, first_row = seen_source_keys[key]
                source_duplicates.append(
                    {
                        "key": key_text(key),
                        "operator": workbook.operator,
                        "row_number": row.row_number,
                        "first_operator": first_operator,
                        "first_row_number": first_row,
                    }
                )
                continue
            seen_source_keys[key] = (workbook.operator, row.row_number)

            existing = master_index.get(key)
            if existing:
                already_in_master.append(
                    {
                        "operator": workbook.operator,
                        "source_row_number": row.row_number,
                        "master_row_number": existing.row_number,
                        "key": key_text(key),
                    }
                )
                status_updates.append(
                    make_update(
                        operator=workbook.operator,
                        table=source,
                        row_number=row.row_number,
                        column_number=status_col_num,
                        column_name=status_column,
                        old_value=current_status,
                        new_value=submitted_value,
                        reason="already_in_master",
                    )
                )
                continue

            values_by_column = {
                ctx.master.headers[column]: row.values.get(column, "")
                for column in append_cols
            }
            append_rows.append(
                AppendRow(
                    operator=workbook.operator,
                    source_row_number=row.row_number,
                    target_row_number=next_master_row,
                    key_text=key_text(key),
                    values_by_column=values_by_column,
                )
            )
            append_source_row_numbers.add(row.row_number)
            next_master_row += 1
            status_updates.append(
                make_update(
                    operator=workbook.operator,
                    table=source,
                    row_number=row.row_number,
                    column_number=status_col_num,
                    column_name=status_column,
                    old_value=current_status,
                    new_value=submitted_value,
                    reason="appended_to_master",
                )
            )
        if append_source_row_numbers:
            if source.ref.float_image_count:
                ctx.image_risks.append(
                    {
                        "operator": workbook.operator,
                        "type": "float_image_count",
                        "count": source.ref.float_image_count,
                        "message": "该普通表格存在浮动图片；当前脚本无法确认图片是否属于本次追加行，不会复制图片到大表。",
                    }
                )
            cell_risks = (
                inspect_image_cells(ctx.profile["_cli"], source, image_columns, row_numbers=append_source_row_numbers)
                if image_columns
                else []
            )
            if cell_risks:
                ctx.image_risks.append(
                    {
                        "operator": workbook.operator,
                        "type": "non_scalar_cells",
                        "examples": cell_risks,
                        "message": "本次追加行存在图片/富文本单元格；当前脚本不会复制这些对象。",
                    }
                )

    result_config = profile.get("result_writeback") if isinstance(profile.get("result_writeback"), dict) else {}
    if result_config.get("enabled"):
        result_column = str(result_config.get("column") or "").strip()
        source_result_column = str(result_config.get("source_column") or result_column).strip()
        result_keys = [str(item).strip() for item in result_config.get("key_columns", key_columns) if str(item).strip()]
        missing_master_result = ensure_columns(ctx.master, result_keys + [result_column], "大表格")
        if missing_master_result:
            ctx.missing_headers.append({"table": "master", "missing_result_writeback": missing_master_result})
        else:
            result_master_index, result_master_duplicates = build_key_index(ctx.master, result_keys)
            master_duplicate_blockers.extend(
                {"reason": "result_writeback_duplicate", **item} for item in result_master_duplicates
            )
            for workbook, source in ctx.sources:
                missing_source_result = ensure_columns(source, result_keys + [source_result_column], workbook.operator)
                if missing_source_result:
                    ctx.missing_headers.append(
                        {
                            "operator": workbook.operator,
                            "missing_result_writeback": missing_source_result,
                        }
                    )
                    continue
                source_col = source.headers[source_result_column]
                for row in source.rows:
                    key = key_for(row, result_keys)
                    if not any(key):
                        continue
                    master_row = result_master_index.get(key)
                    if not master_row:
                        continue
                    new_value = normalize_value(master_row.values.get(result_column))
                    old_value = normalize_value(row.values.get(source_result_column))
                    if not new_value or old_value == new_value:
                        continue
                    result_updates.append(
                        make_update(
                            operator=workbook.operator,
                            table=source,
                            row_number=row.row_number,
                            column_number=source_col,
                            column_name=source_result_column,
                            old_value=old_value,
                            new_value=new_value,
                            reason="master_result_writeback",
                        )
                    )

    blocking = {
        "missing_targets": ctx.missing_targets,
        "missing_headers": ctx.missing_headers,
        "master_duplicates": master_duplicate_blockers,
        "source_duplicates": source_duplicates,
        "image_risks": ctx.image_risks,
    }
    return {
        "append_rows": append_rows,
        "status_header_updates": status_header_updates,
        "status_updates": status_updates,
        "result_updates": result_updates,
        "already_in_master": already_in_master,
        "skipped": skipped,
        "blocking": blocking,
        "next_master_row": next_master_row,
    }


def group_contiguous_columns(values_by_column: dict[int, str]) -> list[tuple[int, list[str]]]:
    groups: list[tuple[int, list[str]]] = []
    current_start = 0
    current_values: list[str] = []
    previous = 0
    for column in sorted(values_by_column):
        value = values_by_column[column]
        if not current_values:
            current_start = column
            current_values = [value]
        elif column == previous + 1:
            current_values.append(value)
        else:
            groups.append((current_start, current_values))
            current_start = column
            current_values = [value]
        previous = column
    if current_values:
        groups.append((current_start, current_values))
    return groups


def write_append_rows(cli: LarkCli, master: SheetTable, rows: list[AppendRow], delay_seconds: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in rows:
        for start_col, values in group_contiguous_columns(row.values_by_column):
            start_cell = f"{col_to_a1(start_col)}{row.target_row_number}"
            result = cli.sheets(
                [
                    "+csv-put",
                    "--spreadsheet-token",
                    master.ref.token,
                    "--sheet-id",
                    master.ref.sheet_id,
                    "--start-cell",
                    start_cell,
                    "--csv",
                    "-",
                ],
                input_text=rows_to_csv([values]),
            )
            results.append(
                {
                    "operator": row.operator,
                    "source_row_number": row.source_row_number,
                    "target_row_number": row.target_row_number,
                    "start_cell": start_cell,
                    "cell_count": len(values),
                    "result": result.get("ok", result.get("code", "")),
                }
            )
            time.sleep(delay_seconds)
    return results


def group_updates(updates: list[CellUpdate]) -> list[list[CellUpdate]]:
    groups: list[list[CellUpdate]] = []
    for update in sorted(updates, key=lambda item: (item.token, item.sheet_id, item.row_number, item.column_number)):
        if (
            groups
            and groups[-1][-1].token == update.token
            and groups[-1][-1].sheet_id == update.sheet_id
            and groups[-1][-1].row_number == update.row_number
            and groups[-1][-1].column_number + 1 == update.column_number
        ):
            groups[-1].append(update)
        else:
            groups.append([update])
    return groups


def write_updates(cli: LarkCli, updates: list[CellUpdate], delay_seconds: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for group in group_updates(updates):
        first = group[0]
        values = [[update.new_value for update in group]]
        result = cli.sheets(
            [
                "+csv-put",
                "--spreadsheet-token",
                first.token,
                "--sheet-id",
                first.sheet_id,
                "--start-cell",
                first.cell,
                "--csv",
                "-",
            ],
            input_text=rows_to_csv(values),
        )
        results.append(
            {
                "operator": first.operator,
                "sheet_name": first.sheet_name,
                "start_cell": first.cell,
                "cell_count": len(group),
                "reason": first.reason,
                "result": result.get("ok", result.get("code", "")),
            }
        )
        time.sleep(delay_seconds)
    return results


def read_single_cell(cli: LarkCli, token: str, sheet_id: str, cell: str) -> str:
    result = cli.sheets(
        [
            "+csv-get",
            "--spreadsheet-token",
            token,
            "--sheet-id",
            sheet_id,
            "--range",
            cell,
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    rows = parse_annotated_csv(str(data.get("annotated_csv") or ""))
    return normalize_value(rows[0][0]) if rows and rows[0] else ""


def verify_updates(cli: LarkCli, updates: list[CellUpdate], limit: int = 30) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for update in updates[:limit]:
        actual = read_single_cell(cli, update.token, update.sheet_id, update.cell)
        checks.append(
            {
                "operator": update.operator,
                "cell": update.cell,
                "expected": update.new_value,
                "actual": actual,
                "ok": actual == update.new_value,
                "reason": update.reason,
            }
        )
    return checks


def verify_append_keys(cli: LarkCli, master: SheetTable, rows: list[AppendRow], key_columns: list[str], limit: int = 30) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    key_col_numbers = [master.headers[column] for column in key_columns if column in master.headers]
    for row in rows[:limit]:
        actual_key = tuple(
            read_single_cell(cli, master.ref.token, master.ref.sheet_id, f"{col_to_a1(column)}{row.target_row_number}")
            for column in key_col_numbers
        )
        checks.append(
            {
                "operator": row.operator,
                "target_row_number": row.target_row_number,
                "expected_key": row.key_text,
                "actual_key": key_text(actual_key),
                "ok": key_text(actual_key) == row.key_text,
            }
        )
    return checks


def cell_update_to_dict(update: CellUpdate) -> dict[str, Any]:
    return {
        "operator": update.operator,
        "sheet_name": update.sheet_name,
        "cell": update.cell,
        "column": update.column_name,
        "old_value": update.old_value,
        "new_value": update.new_value,
        "reason": update.reason,
    }


def append_row_to_dict(row: AppendRow, master: SheetTable) -> dict[str, Any]:
    column_lookup = {number: name for name, number in master.headers.items()}
    return {
        "operator": row.operator,
        "source_row_number": row.source_row_number,
        "target_row_number": row.target_row_number,
        "key": row.key_text,
        "columns": [column_lookup.get(column, col_to_a1(column)) for column in sorted(row.values_by_column)],
    }


def default_output_path(scenario_id: str) -> Path:
    output_dir = PROJECT_ROOT / "workspace" / "10表格同步" / "处理日志"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", scenario_id).strip("_") or "operator_sync"
    return output_dir / f"{stamp}_{safe}_operator_sync_summary.json"


def write_output_file(result: dict[str, Any], args: argparse.Namespace, scenario_id: str) -> str:
    if args.no_output_file:
        return ""
    path = Path(args.output_json).expanduser() if args.output_json else default_output_path(scenario_id)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lx-biaogetongbu 运营主体普通表格同步。")
    parser.add_argument("--scenario", default="", help="内置场景名，例如 beishen_shensu / jingmo_chengke")
    parser.add_argument("--profile", default="", help="JSON profile 路径；优先级高于 --scenario")
    parser.add_argument("--master-url", default="", help="飞书普通电子表格大表 URL；也可写入本机 config")
    parser.add_argument("--master-sheet", default="", help="大表 sheet 名；不传则用 profile 或单 sheet 自动识别")
    parser.add_argument("--contact-person", default="", help="对接人；不填则读 config 默认值")
    parser.add_argument("--operator", action="append", help="指定运营主体，可重复传，也可逗号分隔")
    parser.add_argument("--all-operators", action="store_true", help="同步根文件夹下全部运营主体")
    parser.add_argument("--operator-root-folder-token", default="")
    parser.add_argument("--operator-root-folder-url", default="")
    parser.add_argument("--operator-folder-template", default="", help="默认 {operator}-运营主体")
    parser.add_argument("--target-table-template", default="", help="默认读取 profile，例如 {operator}-背审申诉")
    parser.add_argument("--header-row", type=int, default=1)
    parser.add_argument("--allow-image-risk", action="store_true", help="允许在存在图片/富文本风险时继续写纯值；默认阻断")
    parser.add_argument("--confirmed", action="store_true", help="实际写入；不加时只 dry-run")
    parser.add_argument("--lark-cli", default="")
    parser.add_argument("--identity", choices=["user", "bot"], default="user")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--request-delay-seconds", type=float, default=1.2)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--no-output-file", action="store_true")
    return parser


def load_sources(
    cli: LarkCli,
    workbooks: list[OperatorWorkbook],
    *,
    expected_sheet_name: str,
    header_row: int,
    request_delay_seconds: float,
    tolerate_errors: bool,
) -> tuple[list[tuple[OperatorWorkbook, SheetTable]], list[dict[str, str]]]:
    sources: list[tuple[OperatorWorkbook, SheetTable]] = []
    skipped: list[dict[str, str]] = []
    for workbook in workbooks:
        try:
            source = read_table(
                cli,
                workbook.url or workbook.token,
                expected_sheet_name=expected_sheet_name,
                header_row=header_row,
                label=f"{workbook.operator}/{workbook.name}",
            )
        except OperatorSyncError as exc:
            if not tolerate_errors:
                raise
            skipped.append({"operator": workbook.operator, "workbook": workbook.name, "reason": str(exc)})
            continue
        sources.append((workbook, source))
        time.sleep(request_delay_seconds)
    return sources, skipped


def run(args: argparse.Namespace) -> int:
    config = load_config()
    profile = load_profile(args.profile or args.scenario)
    scenario_id = str(profile.get("scenario_id") or args.scenario or Path(str(profile.get("_profile_path"))).stem)
    profile["_cli"] = None

    contact_person = resolve_contact_person(args, config)
    if not contact_person:
        raise OperatorSyncError("缺少 --contact-person，且配置中没有默认对接人。")
    root_folder_token = resolve_operator_root_folder(args, config, contact_person)
    if not root_folder_token:
        raise OperatorSyncError("缺少运营主体根文件夹。请传 --operator-root-folder-url，或在 config/fog_config.yaml 配置。")
    master_url = resolve_master_url(args, config, profile)

    operator_folder_template = args.operator_folder_template or str(profile.get("operator_folder_template") or "{operator}-运营主体")
    target_table_template = args.target_table_template or str(profile.get("target_table_template") or "")
    if not target_table_template:
        raise OperatorSyncError("profile.target_table_template 不能为空。")
    master_sheet = args.master_sheet or str(profile.get("master_sheet_name") or "")
    source_sheet = str(profile.get("operator_sheet_name") or "")

    requested = parse_csv_arg(args.operator)
    if not args.all_operators and not requested:
        raise OperatorSyncError("请传 --operator，或使用 --all-operators。")

    cli = LarkCli(resolve_lark_cli(config, args.lark_cli), identity=args.identity, timeout=args.timeout)
    profile["_cli"] = cli
    master = read_table(cli, master_url, expected_sheet_name=master_sheet, header_row=args.header_row, label="大表格")
    workbooks, missing_targets, operators_requested = resolve_operator_workbooks(
        cli,
        root_folder_token,
        requested,
        operator_folder_template=operator_folder_template,
        target_table_template=target_table_template,
    )
    sources, skipped_sources = load_sources(
        cli,
        workbooks,
        expected_sheet_name=source_sheet,
        header_row=args.header_row,
        request_delay_seconds=args.request_delay_seconds,
        tolerate_errors=args.all_operators,
    )
    ctx = BuildContext(
        profile=profile,
        master=master,
        sources=sources,
        operators_requested=operators_requested,
        missing_targets=missing_targets,
        skipped_sources=skipped_sources,
    )
    plan = build_plan(ctx)
    if args.allow_image_risk:
        plan["blocking"]["image_risks"] = []
    has_blocking = any(plan["blocking"].values())
    if has_blocking and args.confirmed:
        raise OperatorSyncError("存在同步阻塞项，已停止写入: " + json.dumps(plan["blocking"], ensure_ascii=False)[:2000])

    append_rows: list[AppendRow] = plan["append_rows"]
    status_header_updates: list[CellUpdate] = plan["status_header_updates"]
    status_updates: list[CellUpdate] = plan["status_updates"]
    result_updates: list[CellUpdate] = plan["result_updates"]
    write_results: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    if args.confirmed:
        write_results["append"] = write_append_rows(cli, master, append_rows, args.request_delay_seconds) if append_rows else []
        updates = status_header_updates + status_updates + result_updates
        write_results["updates"] = write_updates(cli, updates, args.request_delay_seconds) if updates else []
        key_columns = profile_list(profile, "key_columns")
        verification["append_keys"] = verify_append_keys(cli, master, append_rows, key_columns)
        verification["updates"] = verify_updates(cli, updates)
        failed = [item for group in verification.values() for item in group if not item.get("ok")]
        if failed:
            raise OperatorSyncError("写后验证失败: " + json.dumps(failed[:10], ensure_ascii=False))

    result: dict[str, Any] = {
        "ok": not has_blocking,
        "dry_run": not args.confirmed,
        "scenario": scenario_id,
        "profile": profile.get("_profile_path"),
        "contact_person": contact_person,
        "master": {
            "url": master_url,
            "sheet_name": master.ref.sheet_name,
            "sheet_id": master.ref.sheet_id,
            "data_rows": len(master.rows),
            "last_nonblank_row": master.last_nonblank_row,
            "float_image_count": master.ref.float_image_count,
        },
        "operators_requested": operators_requested,
        "operators_loaded": [workbook.operator for workbook, _ in sources],
        "skipped_sources": skipped_sources,
        "append_count": len(append_rows),
        "append_rows": [append_row_to_dict(row, master) for row in append_rows[:200]],
        "already_in_master_count": len(plan["already_in_master"]),
        "already_in_master": plan["already_in_master"][:200],
        "status_header_update_count": len(status_header_updates),
        "status_update_count": len(status_updates),
        "status_updates": [cell_update_to_dict(update) for update in status_updates[:200]],
        "result_writeback_count": len(result_updates),
        "result_updates": [cell_update_to_dict(update) for update in result_updates[:200]],
        "skipped_count": len(plan["skipped"]),
        "skipped": plan["skipped"][:200],
        "blocking": plan["blocking"],
        "write_results": write_results,
        "verification": verification,
    }
    output_path = write_output_file(result, args, scenario_id)
    if output_path:
        result["output_json"] = output_path
        Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except OperatorSyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
