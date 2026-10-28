#!/usr/bin/env python3
"""Sync operator-owned Feishu workbooks back to recurring master sheets.

Default behavior is dry-run. Use --confirmed to write Feishu ordinary Sheets.
The command writes scalar values first, then remounts supported cell-internal
embed-image objects onto the target spreadsheet. A source image_token is
mounted only on its own workbook, so cross-workbook copies download the image
and upload it with cells-set-image instead of reusing that token. Floating
images and unrecognized rich objects remain blocking risks.
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
import tempfile
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
class SheetImage:
    image_token: str = ""
    image_uri: str = ""
    image_name: str = ""
    image_width: int = 0
    image_height: int = 0


@dataclass
class ImageCopyTask:
    operator: str
    source_token: str
    source_sheet_id: str
    source_sheet_name: str
    source_row_number: int
    source_column_number: int
    source_column_name: str
    target_token: str
    target_sheet_id: str
    target_sheet_name: str
    target_row_number: int
    target_column_number: int
    target_column_name: str
    images: list[SheetImage]

    @property
    def source_cell(self) -> str:
        return f"{col_to_a1(self.source_column_number)}{self.source_row_number}"

    @property
    def target_cell(self) -> str:
        return f"{col_to_a1(self.target_column_number)}{self.target_row_number}"

    @property
    def image(self) -> SheetImage:
        return self.images[0]


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
EMBED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
EMBED_IMAGE_TEMP_PREFIX = "lx-biaogetongbu-embed-"


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

    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        retries: int = 1,
        cwd: Path | str | None = None,
    ) -> dict[str, Any]:
        argv = [str(self.cli_path), *args]
        last_detail = ""
        run_cwd = os.fspath(cwd) if cwd is not None else None
        for attempt in range(1, retries + 2):
            proc = subprocess.run(
                argv,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                cwd=run_cwd,
            )
            if proc.returncode == 0:
                return parse_json_output(proc.stdout)
            last_detail = proc.stderr.strip() or proc.stdout.strip()
            if attempt <= retries:
                time.sleep(3 * attempt)
        raise OperatorSyncError(f"lark-cli 执行失败: {' '.join(args)}\n{last_detail[:2000]}")

    def sheets(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        retries: int = 1,
        cwd: Path | str | None = None,
    ) -> dict[str, Any]:
        return self.run(["sheets", *args, "--as", self.identity, "--json"], input_text=input_text, retries=retries, cwd=cwd)

    def drive(self, args: list[str], *, retries: int = 1, cwd: Path | str | None = None) -> dict[str, Any]:
        return self.run(["drive", *args, "--as", self.identity, "--json"], retries=retries, cwd=cwd)


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


def extract_sheet_id_from_url(url_or_token: str) -> str:
    value = url_or_token.strip()
    match = re.search(r"(?:[?&#]sheet=)([^&#]+)", value)
    return match.group(1).strip() if match else ""


def col_to_a1(column: int) -> str:
    if column < 1:
        raise OperatorSyncError(f"列号必须从 1 开始: {column}")
    result = ""
    current = column
    while current:
        current, rem = divmod(current - 1, 26)
        result = chr(65 + rem) + result
    return result


def a1_to_col(column: str) -> int:
    result = 0
    for char in column.strip().upper():
        if not ("A" <= char <= "Z"):
            raise OperatorSyncError(f"非法列名: {column}")
        result = result * 26 + ord(char) - 64
    return result


def col_index_to_number(value: Any, fallback: int) -> int:
    if isinstance(value, int):
        return value if value >= 1 else value + 1
    text = str(value or "").strip()
    if text.isdigit():
        number = int(text)
        return number if number >= 1 else number + 1
    if text:
        return a1_to_col(text)
    return fallback


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


def select_sheet(
    sheets: list[dict[str, Any]],
    expected_name: str = "",
    label: str = "",
    *,
    expected_sheet_id: str = "",
) -> SheetRef:
    if not sheets:
        raise OperatorSyncError(f"{label} 没有可读取的 sheet。")
    selected: dict[str, Any] | None = None
    if expected_sheet_id:
        for sheet in sheets:
            sheet_id = str(sheet.get("sheet_id") or sheet.get("id") or sheet.get("reference_id") or "")
            if sheet_id == expected_sheet_id:
                selected = sheet
                break
        if selected is None:
            ids = [str(sheet.get("sheet_id") or sheet.get("id") or sheet.get("reference_id") or "") for sheet in sheets]
            raise OperatorSyncError(f"{label} 没有 sheet_id: {expected_sheet_id}；可用: {', '.join(ids)}")
    elif expected_name:
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
        raise OperatorSyncError(f"{label} 有多个 sheet，请在 profile 或参数指定 sheet 名/sheet_id: {', '.join(names)}")

    title = str(selected.get("sheet_name") or selected.get("title") or selected.get("name") or "")
    sheet_id = str(selected.get("sheet_id") or selected.get("id") or selected.get("reference_id") or "")
    if not sheet_id:
        raise OperatorSyncError(f"{label} sheet 元数据不完整: {selected}")
    if not title:
        title = sheet_id
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


def strip_header_decoration(value: Any) -> str:
    """Drop a template URL or text after the first line from a header cell.

    Live sheets sometimes append a sample link or a note under the field name.
    The field name itself is kept. A same-line Chinese suffix is not removed.
    """
    text = str(value).strip() if value is not None else ""
    if not text:
        return ""
    first_line = re.split(r"[\r\n]", text, maxsplit=1)[0].strip()
    without_url = re.split(r"https?://", first_line, maxsplit=1, flags=re.IGNORECASE)[0]
    return without_url.strip().rstrip(" ：:\t")


def _header_decoration_candidate(header: str, name: str) -> bool:
    stripped = strip_header_decoration(header)
    if stripped == name:
        return True
    basis = stripped if stripped.startswith(name) else (header if header.startswith(name) else "")
    if not basis.startswith(name):
        return False
    suffix = basis[len(name):]
    return bool(suffix) and not suffix[0].isalnum()


def align_decorated_headers(table: SheetTable, names: list[str]) -> None:
    """Rename a unique decorated header onto the profile field name.

    Exact headers win. `承诺书https://…` and `手机号（必填）` can align.
    `车牌号` does not align to `车牌号码`, because the next character is alphanumeric.
    """
    if not names:
        return
    rename: dict[str, str] = {}
    used_targets = set(table.headers)
    for name in names:
        if not name or name in table.headers:
            continue
        candidates = [
            header
            for header in table.headers
            if header not in rename and _header_decoration_candidate(header, name)
        ]
        if len(candidates) != 1:
            continue
        chosen = candidates[0]
        if name in used_targets:
            continue
        rename[chosen] = name
        used_targets.add(name)
    if not rename:
        return
    for old, new in rename.items():
        number = table.headers.pop(old)
        table.headers[new] = number
    for row in table.rows:
        for old, new in rename.items():
            if old in row.values:
                row.values[new] = row.values.pop(old)


def profile_header_names(profile: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("append_columns", "key_columns", "required_columns", "require_nonempty_columns", "image_columns"):
        names.extend(profile_list(profile, key))
    status_column = str(profile.get("status_column") or "").strip()
    if status_column:
        names.append(status_column)
    for rule in profile.get("conditional_required") or []:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when")
        columns = rule.get("columns")
        if isinstance(when, dict):
            names.extend(str(item).strip() for item in when)
        if isinstance(columns, list):
            names.extend(str(item).strip() for item in columns)
    result_config = profile.get("result_writeback") if isinstance(profile.get("result_writeback"), dict) else {}
    if isinstance(result_config.get("key_columns"), list):
        names.extend(str(item).strip() for item in result_config["key_columns"])
    for spec in result_writeback_specs(profile):
        names.append(spec["column"])
        names.append(spec["source_column"])
    for group in require_any_image_groups(profile):
        names.extend(group)
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name and name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


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
    expected_sheet_id: str = "",
    header_row: int = 1,
    label: str,
) -> SheetTable:
    token = extract_sheet_token(url_or_token)
    sheets = workbook_info(cli, url_or_token)
    sheet_id = expected_sheet_id or extract_sheet_id_from_url(url_or_token)
    ref = select_sheet(sheets, expected_sheet_name, label, expected_sheet_id=sheet_id)
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


def resolve_configured_operator_entries(
    config: dict[str, Any],
    scenario_id: str,
    *,
    cli_urls: list[str] | None = None,
) -> list[dict[str, str]]:
    scenario = configured_map(config, ["lx_biaogetongbu", "operator_sync", "scenarios", scenario_id])
    entries: list[dict[str, str]] = []
    raw_operators = scenario.get("operators")
    if isinstance(raw_operators, list):
        for item in raw_operators:
            if isinstance(item, str):
                url = item.strip()
                if url:
                    entries.append({"operator": "", "url": url, "sheet_id": extract_sheet_id_from_url(url)})
            elif isinstance(item, dict):
                url = str(item.get("url") or item.get("workbook_url") or "").strip()
                if not url:
                    continue
                entries.append(
                    {
                        "operator": str(item.get("operator") or item.get("name") or "").strip(),
                        "url": url,
                        "sheet_id": str(item.get("sheet_id") or extract_sheet_id_from_url(url)).strip(),
                    }
                )
    for url in cli_urls or []:
        value = str(url).strip()
        if not value:
            continue
        entries.append({"operator": "", "url": value, "sheet_id": extract_sheet_id_from_url(value)})
    # de-dupe by token+sheet_id keeping first named operator
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        token = extract_sheet_token(entry["url"])
        key = (token, entry.get("sheet_id") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def resolve_operator_workbooks_from_urls(
    cli: LarkCli,
    entries: list[dict[str, str]],
    operators: list[str],
    *,
    request_delay_seconds: float = 0.0,
) -> tuple[list[OperatorWorkbook], list[dict[str, str]], list[str]]:
    discovered: list[OperatorWorkbook] = []
    missing: list[dict[str, str]] = []
    for entry in entries:
        url = entry["url"]
        try:
            result = cli.sheets(["+workbook-info", *spreadsheet_locator(url)])
            payload = result.get("data") if isinstance(result.get("data"), dict) else result
            sheets = payload.get("sheets", []) if isinstance(payload, dict) else []
            sheets = [item for item in sheets if isinstance(item, dict)]
            data_title = str(payload.get("title") or "") if isinstance(payload, dict) else ""
            operator = entry.get("operator") or operator_from_workbook_title(data_title) or extract_sheet_token(url)
            sheet_id = entry.get("sheet_id") or extract_sheet_id_from_url(url)
            select_sheet(sheets, "", operator, expected_sheet_id=sheet_id)
            # Keep sheet_id in URL so read_table can pick it up.
            normalized_url = url
            if sheet_id and "sheet=" not in url:
                joiner = "&" if "?" in url else "?"
                normalized_url = f"{url}{joiner}sheet={sheet_id}"
            discovered.append(
                OperatorWorkbook(
                    operator=operator,
                    folder_token="",
                    token=extract_sheet_token(url),
                    url=normalized_url,
                    name=data_title or operator,
                )
            )
        except OperatorSyncError as exc:
            missing.append({"operator": entry.get("operator") or url, "reason": str(exc), "url": url})
        if request_delay_seconds:
            time.sleep(request_delay_seconds)

    if not operators:
        operators = [item.operator for item in discovered]
    wanted = set(operators)
    workbooks = [item for item in discovered if item.operator in wanted]
    found = {item.operator for item in workbooks}
    for name in operators:
        if name not in found:
            missing.append({"operator": name, "reason": "configured_operator_not_found"})
    return workbooks, missing, operators


def collect_image_presence(
    cli: LarkCli | None,
    source: SheetTable,
    image_columns: list[str],
    row_numbers: list[int],
) -> dict[tuple[int, str], bool]:
    """Return {(row_number, column_name): has_embed_image}."""
    presence: dict[tuple[int, str], bool] = {}
    available = [column for column in image_columns if column in source.headers]
    if not available or not row_numbers:
        return presence
    if cli is None:
        for row in source.rows:
            if row.row_number not in row_numbers:
                continue
            for column in available:
                presence[(row.row_number, column)] = bool(normalize_value(row.values.get(column)))
        return presence
    min_col = min(source.headers[column] for column in available)
    max_col = max(source.headers[column] for column in available)
    start_row = min(row_numbers)
    end_row = max(row_numbers)
    result = cli.sheets(
        [
            "+cells-get",
            *spreadsheet_locator(source.ref.url or source.ref.token),
            "--sheet-id",
            source.ref.sheet_id,
            "--range",
            f"{col_to_a1(min_col)}{start_row}:{col_to_a1(max_col)}{end_row}",
            "--include",
            "value",
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    ranges = data.get("ranges", []) if isinstance(data, dict) else []
    if not ranges or not isinstance(ranges[0], dict):
        for row_number in row_numbers:
            for column in available:
                presence[(row_number, column)] = False
        return presence
    cells = ranges[0].get("cells", [])
    row_indices = ranges[0].get("row_indices", [])
    col_indices = ranges[0].get("col_indices", [])
    source_column_by_number = {source.headers[column]: column for column in available}
    wanted = set(row_numbers)
    if isinstance(cells, list):
        for row_offset, row_cells in enumerate(cells):
            if not isinstance(row_cells, list):
                continue
            row_number = row_indices[row_offset] if row_offset < len(row_indices) else start_row + row_offset
            row_number = int(row_number)
            if row_number not in wanted:
                continue
            for col_offset, cell in enumerate(row_cells):
                fallback_col = min_col + col_offset
                col_number = (
                    col_index_to_number(col_indices[col_offset], fallback_col)
                    if col_offset < len(col_indices)
                    else fallback_col
                )
                column_name = source_column_by_number.get(col_number)
                if not column_name:
                    continue
                presence[(row_number, column_name)] = bool(extract_embed_images(cell))
    for row_number in row_numbers:
        for column in available:
            presence.setdefault((row_number, column), False)
    return presence


def key_for(row: TableRow, columns: list[str]) -> tuple[str, ...]:
    return tuple(normalize_value(row.values.get(column)) for column in columns)


def key_text(key: tuple[str, ...]) -> str:
    return " | ".join(key)


def ensure_columns(table: SheetTable, columns: list[str], label: str) -> list[str]:
    return [column for column in columns if column not in table.headers]


def build_key_index(
    table: SheetTable,
    key_columns: list[str],
    *,
    keep: str = "first",
) -> tuple[dict[tuple[str, ...], TableRow], list[dict[str, Any]]]:
    """Index rows by key. keep=first is the historical match; keep=last uses the highest row number.

    Duplicate records always point first_row_number at the earliest row, even when the index keeps the last row.
    """
    if keep not in {"first", "last"}:
        raise OperatorSyncError(f"build_key_index.keep 必须是 first 或 last: {keep}")
    index: dict[tuple[str, ...], TableRow] = {}
    first_row_numbers: dict[tuple[str, ...], int] = {}
    duplicates: list[dict[str, Any]] = []
    for row in table.rows:
        key = key_for(row, key_columns)
        if not any(key):
            continue
        if key in index:
            duplicates.append(
                {
                    "key": key_text(key),
                    "row_number": row.row_number,
                    "first_row_number": first_row_numbers[key],
                }
            )
            if keep == "last" and row.row_number >= index[key].row_number:
                index[key] = row
            continue
        index[key] = row
        first_row_numbers[key] = row.row_number
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


def int_or_zero(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def first_text(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def rich_text_segments(cell: Any) -> list[dict[str, Any]]:
    if not isinstance(cell, dict):
        return []
    candidates = [
        cell.get("rich_text"),
        cell.get("richText"),
        cell.get("segments"),
    ]
    value = cell.get("value")
    if isinstance(value, dict):
        candidates.extend([value.get("rich_text"), value.get("richText"), value.get("segments")])
    elif isinstance(value, list):
        candidates.append(value)
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def extract_embed_images(cell: Any) -> list[SheetImage]:
    images: list[SheetImage] = []
    for segment in rich_text_segments(cell):
        segment_type = str(segment.get("type") or segment.get("segment_type") or "").strip()
        if segment_type not in {"embed-image", "image"}:
            continue
        image = SheetImage(
            image_token=first_text(segment.get("image_token"), segment.get("imageToken"), segment.get("file_token")),
            image_uri=first_text(segment.get("image_uri"), segment.get("imageUri"), segment.get("uri")),
            image_name=first_text(segment.get("image_name"), segment.get("imageName"), segment.get("name"), segment.get("text"), "image.png"),
            image_width=int_or_zero(segment.get("image_width") or segment.get("imageWidth") or segment.get("width")),
            image_height=int_or_zero(segment.get("image_height") or segment.get("imageHeight") or segment.get("height")),
        )
        if image.image_token or image.image_uri:
            images.append(image)
    return images


def image_to_rich_text(image: SheetImage) -> dict[str, Any]:
    segment: dict[str, Any] = {
        "type": "embed-image",
        "text": image.image_name or "image.png",
        "image_name": image.image_name or "image.png",
    }
    if image.image_token:
        segment["image_token"] = image.image_token
    elif image.image_uri:
        segment["image_uri"] = image.image_uri
    if image.image_width > 0:
        segment["image_width"] = image.image_width
    if image.image_height > 0:
        segment["image_height"] = image.image_height
    return segment


def collect_image_copy_tasks(
    cli: LarkCli,
    source: SheetTable,
    master: SheetTable,
    image_columns: list[str],
    append_rows: list[AppendRow],
    *,
    max_examples: int = 20,
) -> tuple[list[ImageCopyTask], list[dict[str, Any]]]:
    available = [column for column in image_columns if column in source.headers and column in master.headers]
    append_by_source_row = {row.source_row_number: row for row in append_rows}
    if not available or not append_by_source_row:
        return [], []
    min_col = min(source.headers[column] for column in available)
    max_col = max(source.headers[column] for column in available)
    start_row = min(append_by_source_row)
    end_row = max(append_by_source_row)
    result = cli.sheets(
        [
            "+cells-get",
            *spreadsheet_locator(source.ref.url or source.ref.token),
            "--sheet-id",
            source.ref.sheet_id,
            "--range",
            f"{col_to_a1(min_col)}{start_row}:{col_to_a1(max_col)}{end_row}",
            "--include",
            "value",
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    ranges = data.get("ranges", []) if isinstance(data, dict) else []
    if not ranges or not isinstance(ranges[0], dict):
        return [], []
    cells = ranges[0].get("cells", [])
    row_indices = ranges[0].get("row_indices", [])
    col_indices = ranges[0].get("col_indices", [])
    if not isinstance(cells, list):
        return [], []
    source_column_by_number = {source.headers[column]: column for column in available}
    risks: list[dict[str, Any]] = []
    copies: list[ImageCopyTask] = []
    for row_offset, row_cells in enumerate(cells):
        if not isinstance(row_cells, list):
            continue
        row_number = row_indices[row_offset] if row_offset < len(row_indices) else start_row + row_offset
        row_number = int(row_number)
        append_row = append_by_source_row.get(row_number)
        if append_row is None:
            continue
        for col_offset, cell in enumerate(row_cells):
            fallback_col = min_col + col_offset
            col_number = col_index_to_number(col_indices[col_offset], fallback_col) if col_offset < len(col_indices) else fallback_col
            column_name = source_column_by_number.get(col_number)
            if not column_name:
                continue
            images = extract_embed_images(cell)
            if images:
                copies.append(
                    ImageCopyTask(
                        operator=append_row.operator,
                        source_token=source.ref.token,
                        source_sheet_id=source.ref.sheet_id,
                        source_sheet_name=source.ref.sheet_name,
                        source_row_number=row_number,
                        source_column_number=col_number,
                        source_column_name=column_name,
                        target_token=master.ref.token,
                        target_sheet_id=master.ref.sheet_id,
                        target_sheet_name=master.ref.sheet_name,
                        target_row_number=append_row.target_row_number,
                        target_column_number=master.headers[column_name],
                        target_column_name=column_name,
                        images=images,
                    )
                )
                continue
            if plain_cell_risk(cell):
                col_letter = col_to_a1(col_number)
                risks.append({"row_number": row_number, "column": col_letter, "cell": f"{col_letter}{row_number}", "cell_keys": sorted(cell) if isinstance(cell, dict) else []})
                if len(risks) >= max_examples:
                    return copies, risks
    return copies, risks


def profile_int(profile: dict[str, Any], key: str) -> int | None:
    value = profile.get(key)
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise OperatorSyncError(f"profile.{key} 必须是正整数: {value}") from exc
    if number < 1:
        raise OperatorSyncError(f"profile.{key} 必须是正整数: {value}")
    return number


def submitted_values_for(profile: dict[str, Any]) -> set[str]:
    """Only values in accepted_submitted_values skip when that list is set.

    Empty accepted list keeps legacy behavior: submitted_value (default 填写已提交).
    """
    accepted = [normalize_value(item) for item in profile_list(profile, "accepted_submitted_values")]
    accepted = [item for item in accepted if item]
    if accepted:
        return set(accepted)
    primary = normalize_value(profile.get("submitted_value") or "填写已提交")
    return {primary} if primary else set()


def profile_bool(profile: dict[str, Any], key: str, default: bool = False) -> bool:
    value = profile.get(key, default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def conditional_required_columns(profile: dict[str, Any], row: TableRow) -> list[str]:
    rules = profile.get("conditional_required")
    if not isinstance(rules, list):
        return []
    required: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when")
        columns = rule.get("columns")
        if not isinstance(when, dict) or not isinstance(columns, list):
            continue
        matched = True
        for header, expected in when.items():
            if normalize_value(row.values.get(str(header))) != normalize_value(expected):
                matched = False
                break
        if not matched:
            continue
        for column in columns:
            name = str(column).strip()
            if name and name not in seen:
                seen.add(name)
                required.append(name)
    return required


def column_letter_for(table: SheetTable, column_name: str) -> str:
    if column_name in table.headers:
        return col_to_a1(table.headers[column_name])
    return column_name


def require_any_image_groups(profile: dict[str, Any]) -> list[list[str]]:
    """Image column groups that pass when any one column in the group has an image.

    Profile field require_any_image_columns is a list of groups. A flat list of
    strings is one group.
    """
    value = profile.get("require_any_image_columns")
    if not isinstance(value, list) or not value:
        return []
    if all(isinstance(item, str) for item in value):
        names = [item.strip() for item in value if item.strip()]
        return [names] if names else []
    groups: list[list[str]] = []
    for group in value:
        if isinstance(group, str):
            name = group.strip()
            if name:
                groups.append([name])
            continue
        if not isinstance(group, list):
            continue
        names = [str(item).strip() for item in group if str(item).strip()]
        if names:
            groups.append(names)
    return groups


def _contiguous_column_letters(letters: list[str]) -> bool:
    if len(letters) < 2:
        return False
    numbers: list[int] = []
    for letter in letters:
        if not letter.isascii() or not letter.isalpha():
            return False
        numbers.append(a1_to_col(letter))
    return numbers == list(range(numbers[0], numbers[0] + len(numbers)))


def format_any_image_gap(source: SheetTable, columns: list[str]) -> str:
    ordered = sorted(columns, key=lambda name: source.headers.get(name, 10**9))
    letters = [column_letter_for(source, column) for column in ordered]
    if len(letters) == 1:
        return f"缺少{letters[0]}列图片"
    if _contiguous_column_letters(letters):
        return f"缺少{letters[0]}\u2013{letters[-1]}列图片"
    joined = "、".join(f"{letter}列" for letter in letters)
    return f"缺少{joined}图片"


def format_validation_message(
    *,
    missing_text_columns: list[str],
    missing_image_columns: list[str],
    source: SheetTable,
    missing_any_image_groups: list[list[str]] | None = None,
) -> str:
    parts: list[str] = []
    if missing_text_columns:
        letters = [f"{column_letter_for(source, column)}列" for column in missing_text_columns]
        if len(letters) == 1:
            parts.append(f"缺少{letters[0]}信息")
        else:
            parts.append(f"缺少{'、'.join(letters)}信息")
    for column in missing_image_columns:
        parts.append(f"缺少{column_letter_for(source, column)}列图片")
    for group in missing_any_image_groups or []:
        if group:
            parts.append(format_any_image_gap(source, group))
    return "；".join(parts)


def result_writeback_specs(profile: dict[str, Any]) -> list[dict[str, str]]:
    result_config = profile.get("result_writeback") if isinstance(profile.get("result_writeback"), dict) else {}
    if not result_config.get("enabled"):
        return []
    specs: list[dict[str, str]] = []
    columns = result_config.get("columns")
    if isinstance(columns, list) and columns:
        for item in columns:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    specs.append({"column": name, "source_column": name})
            elif isinstance(item, dict):
                column = str(item.get("column") or "").strip()
                source_column = str(item.get("source_column") or column).strip()
                if column:
                    specs.append({"column": column, "source_column": source_column})
        return specs
    column = str(result_config.get("column") or "").strip()
    if not column:
        return []
    source_column = str(result_config.get("source_column") or column).strip()
    return [{"column": column, "source_column": source_column}]


def writeback_skip_source_values(result_config: dict[str, Any]) -> set[str]:
    """Operator result-cell values that must not be overwritten.

    Compared after strip. An empty list keeps the old behavior: a different
    non-empty master result is written.
    """
    return {
        item
        for item in (normalize_value(value) for value in profile_list(result_config, "skip_source_values"))
        if item
    }


def operator_from_workbook_title(title: str) -> str:
    text_value = str(title or "").strip()
    for suffix in ("-运营主体-日常信息", "-异常判责case登记-新", "-日常信息", "-静默乘客", "-背审申诉"):
        if text_value.endswith(suffix):
            return text_value[: -len(suffix)].strip()
    return text_value


def resolve_status_column(
    source: SheetTable,
    *,
    status_column: str,
    status_column_number: int | None,
) -> tuple[int, str, bool]:
    """Return (column_number, header_name, needs_header_write).

    When status_column_number is set, write status to that column. Prefer the
    existing header at that column; otherwise use status_column and add the
    header. When unset, keep legacy behavior: find/create by status_column name.
    """
    if status_column_number is not None:
        for name, number in source.headers.items():
            if number == status_column_number:
                return status_column_number, name, False
        return status_column_number, status_column, True
    if status_column in source.headers:
        return source.headers[status_column], status_column, False
    return next_status_column(source, status_column), status_column, True


def common_append_columns(source: SheetTable, master: SheetTable, profile: dict[str, Any]) -> list[str]:
    configured = profile_list(profile, "append_columns")
    if configured:
        columns = configured
    else:
        columns = [
            header
            for header, _ in sorted(master.headers.items(), key=lambda item: item[1])
            if header in source.headers
        ]
    max_source_column = profile_int(profile, "max_source_column")
    if max_source_column is None:
        return columns
    return [
        header
        for header in columns
        if header in source.headers and source.headers[header] <= max_source_column
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
    submitted_value = normalize_value(profile.get("submitted_value") or "填写已提交")
    submitted_values = submitted_values_for(profile)
    status_column_number = profile_int(profile, "status_column_number")
    key_columns = profile_list(profile, "key_columns")
    required_columns = profile_list(profile, "required_columns")
    require_nonempty_columns = profile_list(profile, "require_nonempty_columns")
    image_columns = profile_list(profile, "image_columns")
    any_image_groups = require_any_image_groups(profile)
    any_image_columns = [column for group in any_image_groups for column in group]
    skip_already_in_master = profile_bool(profile, "skip_already_in_master", True)
    same_batch_duplicate_status = normalize_value(profile.get("same_batch_duplicate_status") or "")
    if profile_bool(profile, "match_decorated_headers", False):
        header_names = profile_header_names(profile)
        align_decorated_headers(ctx.master, header_names)
        for _workbook, source in ctx.sources:
            align_decorated_headers(source, header_names)

    if not key_columns:
        raise OperatorSyncError("profile.key_columns 不能为空。")
    missing_master_key = ensure_columns(ctx.master, key_columns, "大表格")
    if missing_master_key:
        ctx.missing_headers.append({"table": "master", "missing": missing_master_key})

    master_index, _ = build_key_index(ctx.master, key_columns) if not missing_master_key else ({}, [])
    master_duplicate_blockers: list[dict[str, Any]] = []
    master_duplicate_warnings: list[dict[str, Any]] = []
    append_rows: list[AppendRow] = []
    status_updates: list[CellUpdate] = []
    status_header_updates: list[CellUpdate] = []
    result_updates: list[CellUpdate] = []
    image_copies: list[ImageCopyTask] = []
    skipped: list[dict[str, Any]] = []
    already_in_master: list[dict[str, Any]] = []
    source_duplicates: list[dict[str, Any]] = []
    reported_source_duplicates: list[dict[str, Any]] = []
    seen_source_keys: dict[tuple[str, ...], tuple[str, int]] = {}
    next_master_row = ctx.master.last_nonblank_row + 1

    conditional_headers: list[str] = []
    for rule in profile.get("conditional_required") or []:
        if isinstance(rule, dict) and isinstance(rule.get("columns"), list):
            conditional_headers.extend(str(item).strip() for item in rule["columns"] if str(item).strip())
        if isinstance(rule, dict) and isinstance(rule.get("when"), dict):
            conditional_headers.extend(str(item).strip() for item in rule["when"] if str(item).strip())

    for workbook, source in ctx.sources:
        needed = sorted(
            set(required_columns + key_columns + require_nonempty_columns + conditional_headers + any_image_columns)
        )
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

        status_col_num, status_header_name, needs_status_header = resolve_status_column(
            source,
            status_column=status_column,
            status_column_number=status_column_number,
        )
        if needs_status_header:
            status_header_updates.append(
                make_update(
                    operator=workbook.operator,
                    table=source,
                    row_number=1,
                    column_number=status_col_num,
                    column_name=status_header_name,
                    old_value="",
                    new_value=status_header_name,
                    reason="add_status_header",
                )
            )

        write_validation_status = profile_bool(profile, "write_validation_status", False)
        image_column_set = set(image_columns)
        candidate_rows = []
        for row in source.rows:
            current_status = normalize_value(row.values.get(status_header_name))
            if current_status in submitted_values:
                continue
            candidate_rows.append(row.row_number)
        presence_columns: list[str] = []
        seen_presence: set[str] = set()
        for column in image_columns + any_image_columns:
            if column and column not in seen_presence:
                seen_presence.add(column)
                presence_columns.append(column)
        should_scan_images = bool(presence_columns) and (
            write_validation_status
            or any(column in image_column_set for column in require_nonempty_columns)
            or bool(any_image_groups)
        )
        image_presence = (
            collect_image_presence(
                ctx.profile.get("_cli"),
                source,
                presence_columns,
                candidate_rows,
            )
            if should_scan_images
            else {}
        )

        append_source_row_numbers: set[int] = set()
        for row in source.rows:
            current_status = normalize_value(row.values.get(status_header_name))
            if current_status in submitted_values:
                skipped.append(
                    {
                        "operator": workbook.operator,
                        "row_number": row.row_number,
                        "reason": "source_already_submitted",
                    }
                )
                continue
            required_for_row = list(require_nonempty_columns)
            for column in conditional_required_columns(profile, row):
                if column not in required_for_row:
                    required_for_row.append(column)
            missing_text: list[str] = []
            missing_image: list[str] = []
            if required_for_row:
                for column in required_for_row:
                    if column in image_column_set:
                        has_image = image_presence.get((row.row_number, column))
                        if has_image is None:
                            has_image = bool(normalize_value(row.values.get(column)))
                        if not has_image:
                            missing_image.append(column)
                    elif not normalize_value(row.values.get(column)):
                        missing_text.append(column)
            missing_any_groups: list[list[str]] = []
            for group in any_image_groups:
                group_filled = False
                for column in group:
                    has_image = image_presence.get((row.row_number, column))
                    if has_image is None:
                        has_image = bool(normalize_value(row.values.get(column)))
                    if has_image:
                        group_filled = True
                        break
                if not group_filled:
                    missing_any_groups.append(group)
            if missing_text or missing_image or missing_any_groups:
                message = format_validation_message(
                    missing_text_columns=missing_text,
                    missing_image_columns=missing_image,
                    missing_any_image_groups=missing_any_groups,
                    source=source,
                )
                missing_group_columns = [column for group in missing_any_groups for column in group]
                skipped.append(
                    {
                        "operator": workbook.operator,
                        "row_number": row.row_number,
                        "reason": "missing_required_values",
                        "missing": missing_text + missing_image + missing_group_columns,
                        "missing_text": missing_text,
                        "missing_image": missing_image,
                        "missing_any_image": missing_any_groups,
                        "validation_message": message,
                        "values": {
                            column: normalize_value(row.values.get(column))
                            for column in required_for_row + missing_group_columns
                        },
                    }
                )
                if write_validation_status and message and current_status != message:
                    status_updates.append(
                        make_update(
                            operator=workbook.operator,
                            table=source,
                            row_number=row.row_number,
                            column_number=status_col_num,
                            column_name=status_header_name,
                            old_value=current_status,
                            new_value=message,
                            reason="validation_status",
                        )
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
                duplicate_item = {
                    "key": key_text(key),
                    "operator": workbook.operator,
                    "row_number": row.row_number,
                    "first_operator": first_operator,
                    "first_row_number": first_row,
                }
                reported_source_duplicates.append(duplicate_item)
                if same_batch_duplicate_status:
                    skipped.append(
                        {
                            "operator": workbook.operator,
                            "row_number": row.row_number,
                            "reason": "source_duplicate",
                            "first_row_number": first_row,
                        }
                    )
                    if current_status != same_batch_duplicate_status:
                        status_updates.append(
                            make_update(
                                operator=workbook.operator,
                                table=source,
                                row_number=row.row_number,
                                column_number=status_col_num,
                                column_name=status_header_name,
                                old_value=current_status,
                                new_value=same_batch_duplicate_status,
                                reason="source_duplicate",
                            )
                        )
                else:
                    source_duplicates.append(duplicate_item)
                continue
            seen_source_keys[key] = (workbook.operator, row.row_number)

            existing = master_index.get(key) if skip_already_in_master else None
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
                        column_name=status_header_name,
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
                    column_name=status_header_name,
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
            source_append_rows = [
                row
                for row in append_rows
                if row.operator == workbook.operator and row.source_row_number in append_source_row_numbers
            ]
            new_image_copies, cell_risks = (
                collect_image_copy_tasks(ctx.profile["_cli"], source, ctx.master, image_columns, source_append_rows)
                if image_columns and ctx.profile.get("_cli") is not None
                else ([], [])
            )
            image_copies.extend(new_image_copies)
            if cell_risks:
                ctx.image_risks.append(
                    {
                        "operator": workbook.operator,
                        "type": "uncopyable_image_cells",
                        "examples": cell_risks,
                        "message": "本次追加行存在无法复制的图片/富文本单元格。",
                    }
                )

    result_config = profile.get("result_writeback") if isinstance(profile.get("result_writeback"), dict) else {}
    writeback_specs = result_writeback_specs(profile)
    if writeback_specs:
        result_keys = [str(item).strip() for item in result_config.get("key_columns", key_columns) if str(item).strip()]
        master_needed = result_keys + [spec["column"] for spec in writeback_specs]
        missing_master_result = ensure_columns(ctx.master, master_needed, "大表格")
        if missing_master_result:
            ctx.missing_headers.append({"table": "master", "missing_result_writeback": missing_master_result})
        else:
            use_last_row = profile_bool(result_config, "use_last_row", False)
            skip_source_values = writeback_skip_source_values(result_config)
            result_master_index, result_master_duplicates = build_key_index(
                ctx.master,
                result_keys,
                keep="last" if use_last_row else "first",
            )
            duplicate_items = [
                {"reason": "result_writeback_duplicate", **item} for item in result_master_duplicates
            ]
            # 默认回填用第一行。use_last_row 时改用行号最大的一行；该行结果为空则不回填，不用更早行补。
            # skip_source_values：主体结果格去掉首尾空白后命中这些占位时不回填。
            # ignore_duplicates 时重复只记警告、不阻断 confirmed。
            if result_config.get("ignore_duplicates") or profile.get("ignore_master_duplicates"):
                master_duplicate_warnings.extend(duplicate_items)
            else:
                master_duplicate_blockers.extend(duplicate_items)
            for workbook, source in ctx.sources:
                source_needed = result_keys + [spec["source_column"] for spec in writeback_specs]
                missing_source_result = ensure_columns(source, source_needed, workbook.operator)
                if missing_source_result:
                    ctx.missing_headers.append(
                        {
                            "operator": workbook.operator,
                            "missing_result_writeback": missing_source_result,
                        }
                    )
                    continue
                for row in source.rows:
                    key = key_for(row, result_keys)
                    if not any(key):
                        continue
                    master_row = result_master_index.get(key)
                    if not master_row:
                        continue
                    for spec in writeback_specs:
                        result_column = spec["column"]
                        source_result_column = spec["source_column"]
                        source_col = source.headers[source_result_column]
                        new_value = normalize_value(master_row.values.get(result_column))
                        old_value = normalize_value(row.values.get(source_result_column))
                        if not new_value or old_value == new_value or old_value in skip_source_values:
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
        "image_copies": image_copies,
        "status_header_updates": status_header_updates,
        "status_updates": status_updates,
        "result_updates": result_updates,
        "already_in_master": already_in_master,
        "skipped": skipped,
        "blocking": blocking,
        "duplicate_warnings": master_duplicate_warnings,
        "source_duplicates": reported_source_duplicates,
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


def embed_image_filename(image: SheetImage, index: int) -> str:
    suffix = Path(image.image_name or "").suffix.lower()
    if suffix not in EMBED_IMAGE_SUFFIXES:
        suffix = ".png"
    return f"embed-{index}{suffix}"


def require_cwd_relative_filename(relative_name: str) -> str:
    if Path(relative_name).name != relative_name or relative_name in {"", ".", ".."}:
        raise OperatorSyncError(f"单元格图片路径必须是当前目录下的文件名: {relative_name}")
    return relative_name


def download_embed_image(cli: LarkCli, image: SheetImage, directory: Path, index: int) -> str:
    if not image.image_token:
        raise OperatorSyncError("单元格图片缺少 image_token，无法挂到目标工作簿。")
    relative_name = require_cwd_relative_filename(embed_image_filename(image, index))
    cli.drive(
        [
            "+preview",
            "--file-token",
            image.image_token,
            "--type",
            "source_file",
            "--output",
            relative_name,
        ],
        cwd=directory,
    )
    downloaded = directory / relative_name
    if not downloaded.is_file() or downloaded.stat().st_size <= 0:
        raise OperatorSyncError(f"下载单元格图片失败: {image.image_token}")
    return relative_name


def set_target_cell_image(cli: LarkCli, copy_task: ImageCopyTask, relative_image: str, directory: Path) -> dict[str, Any]:
    relative_image = require_cwd_relative_filename(relative_image)
    return cli.sheets(
        [
            "+cells-set-image",
            "--spreadsheet-token",
            copy_task.target_token,
            "--sheet-id",
            copy_task.target_sheet_id,
            "--range",
            copy_task.target_cell,
            "--image",
            relative_image,
        ],
        cwd=directory,
    )


def mounted_image_from_readback(
    actual: list[SheetImage],
    already_mounted: list[SheetImage],
    source: SheetImage,
    copy_task: ImageCopyTask,
) -> SheetImage:
    known_tokens = {item.image_token for item in already_mounted if item.image_token}
    fresh = [item for item in actual if item.image_token and item.image_token not in known_tokens]
    if len(fresh) != 1:
        raise OperatorSyncError(
            f"{copy_task.target_cell} 重新挂载后读到 {len(fresh)} 个新 image_token，无法确认目标工作簿挂载结果。"
        )
    mounted = fresh[0]
    if copy_task.source_token != copy_task.target_token and mounted.image_token == source.image_token:
        raise OperatorSyncError(f"{copy_task.target_cell} 仍复用来源 image_token，目标工作簿未完成挂载。")
    if not mounted.image_name:
        mounted.image_name = source.image_name or "image.png"
    if mounted.image_width <= 0:
        mounted.image_width = source.image_width
    if mounted.image_height <= 0:
        mounted.image_height = source.image_height
    return mounted


def write_mounted_embed_images(cli: LarkCli, copy_task: ImageCopyTask, images: list[SheetImage]) -> dict[str, Any]:
    payload = [[{"rich_text": [image_to_rich_text(image) for image in images]}]]
    return cli.sheets(
        [
            "+cells-set",
            "--spreadsheet-token",
            copy_task.target_token,
            "--sheet-id",
            copy_task.target_sheet_id,
            "--range",
            copy_task.target_cell,
            "--cells",
            "-",
        ],
        input_text=json.dumps(payload, ensure_ascii=False),
    )


def remount_image_copy(cli: LarkCli, copy_task: ImageCopyTask, delay_seconds: float) -> dict[str, Any]:
    if not copy_task.images:
        raise OperatorSyncError(f"{copy_task.source_cell} 没有可挂载的单元格图片。")
    missing_token = [image for image in copy_task.images if not image.image_token]
    if missing_token:
        raise OperatorSyncError(
            f"{copy_task.operator} {copy_task.source_cell} 的单元格图片缺少 image_token，无法挂到目标表 {copy_task.target_cell}。"
        )
    with tempfile.TemporaryDirectory(prefix=EMBED_IMAGE_TEMP_PREFIX) as raw_directory:
        directory = Path(raw_directory)
        relative_names = [
            download_embed_image(cli, image, directory, index) for index, image in enumerate(copy_task.images)
        ]
        if len(copy_task.images) == 1:
            return set_target_cell_image(cli, copy_task, relative_names[0], directory)
        mounted: list[SheetImage] = []
        for image, relative_name in zip(copy_task.images, relative_names):
            set_target_cell_image(cli, copy_task, relative_name, directory)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            actual = read_single_cell_images(
                cli,
                copy_task.target_token,
                copy_task.target_sheet_id,
                copy_task.target_cell,
            )
            mounted.append(mounted_image_from_readback(actual, mounted, image, copy_task))
        return write_mounted_embed_images(cli, copy_task, mounted)


def write_image_copies(cli: LarkCli, copies: list[ImageCopyTask], delay_seconds: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for copy_task in copies:
        result = remount_image_copy(cli, copy_task, delay_seconds)
        results.append(
            {
                "operator": copy_task.operator,
                "source_cell": copy_task.source_cell,
                "target_cell": copy_task.target_cell,
                "column": copy_task.target_column_name,
                "image_count": len(copy_task.images),
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


def verify_updates(cli: LarkCli, updates: list[CellUpdate]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for update in updates:
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


def verify_append_keys(cli: LarkCli, master: SheetTable, rows: list[AppendRow], key_columns: list[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    key_col_numbers = [master.headers[column] for column in key_columns if column in master.headers]
    for row in rows:
        actual_by_column = {
            column: read_single_cell(
                cli,
                master.ref.token,
                master.ref.sheet_id,
                f"{col_to_a1(column)}{row.target_row_number}",
            )
            for column in sorted(row.values_by_column)
        }
        actual_key = tuple(actual_by_column.get(column, "") for column in key_col_numbers)
        cell_checks = [
            {
                "cell": f"{col_to_a1(column)}{row.target_row_number}",
                "expected": normalize_value(expected),
                "actual": actual_by_column[column],
                "ok": actual_by_column[column] == normalize_value(expected),
            }
            for column, expected in sorted(row.values_by_column.items())
        ]
        key_ok = key_text(actual_key) == row.key_text
        checks.append(
            {
                "operator": row.operator,
                "target_row_number": row.target_row_number,
                "expected_key": row.key_text,
                "actual_key": key_text(actual_key),
                "cells": cell_checks,
                "ok": key_ok and all(cell["ok"] for cell in cell_checks),
            }
        )
    return checks


def read_single_cell_images(cli: LarkCli, token: str, sheet_id: str, cell: str) -> list[SheetImage]:
    result = cli.sheets(
        [
            "+cells-get",
            "--spreadsheet-token",
            token,
            "--sheet-id",
            sheet_id,
            "--range",
            cell,
            "--include",
            "value",
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    ranges = data.get("ranges", []) if isinstance(data, dict) else []
    if not ranges or not isinstance(ranges[0], dict):
        return []
    rows = ranges[0].get("cells", [])
    if not rows or not isinstance(rows[0], list) or not rows[0]:
        return []
    return extract_embed_images(rows[0][0])


def positive_image_dimensions(images: list[SheetImage]) -> list[list[int]]:
    sizes = [
        [image.image_width, image.image_height]
        for image in images
        if image.image_width > 0 and image.image_height > 0
    ]
    return sorted(sizes)


def verify_image_copies(cli: LarkCli, copies: list[ImageCopyTask]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for copy_task in copies:
        actual = read_single_cell_images(cli, copy_task.target_token, copy_task.target_sheet_id, copy_task.target_cell)
        expected_count = len(copy_task.images)
        actual_count = len(actual)
        checks.append(
            {
                "operator": copy_task.operator,
                "target_cell": copy_task.target_cell,
                "expected_image_count": expected_count,
                "actual_image_count": actual_count,
                "expected_dimensions": positive_image_dimensions(copy_task.images),
                "actual_dimensions": positive_image_dimensions(actual),
                "ok": expected_count > 0 and actual_count == expected_count,
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


def image_copy_to_dict(copy_task: ImageCopyTask) -> dict[str, Any]:
    return {
        "operator": copy_task.operator,
        "source_cell": copy_task.source_cell,
        "target_cell": copy_task.target_cell,
        "column": copy_task.target_column_name,
        "image_count": len(copy_task.images),
    }


def default_output_path(scenario_id: str) -> Path:
    output_dir = PROJECT_ROOT / "workspace" / "10表格同步" / "处理日志"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", scenario_id).strip("_") or "operator_sync"
    return output_dir / f"{stamp}_{safe}_operator_sync_summary.json"


def resolve_output_path(args: argparse.Namespace, scenario_id: str) -> Path | None:
    if args.no_output_file:
        return None
    path = Path(args.output_json).expanduser() if args.output_json else default_output_path(scenario_id)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def ensure_output_write_authorized(args: argparse.Namespace, scenario_id: str) -> None:
    path = resolve_output_path(args, scenario_id)
    if path is not None and path.exists() and not (args.confirmed and args.overwrite):
        raise OperatorSyncError(f"输出已存在，拒绝覆盖: {path}；需要同时传 --overwrite --confirmed")


def write_output_file(result: dict[str, Any], args: argparse.Namespace, scenario_id: str) -> str:
    if not args.confirmed or args.no_output_file:
        return ""
    path = resolve_output_path(args, scenario_id)
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lx-biaogetongbu 运营主体普通表格同步。")
    parser.add_argument("--scenario", default="", help="内置场景名，例如 beishen_shensu / jingmo_chengke / yichang_panzhe_case")
    parser.add_argument("--profile", default="", help="JSON profile 路径；优先级高于 --scenario")
    parser.add_argument("--master-url", default="", help="飞书普通电子表格大表 URL；也可写入本机 config")
    parser.add_argument("--master-sheet", default="", help="大表 sheet 名；不传则用 profile 或单 sheet 自动识别")
    parser.add_argument("--contact-person", default="", help="对接人；不填则读 config 默认值")
    parser.add_argument("--operator", action="append", help="指定运营主体，可重复传，也可逗号分隔")
    parser.add_argument("--all-operators", action="store_true", help="同步根文件夹下全部运营主体，或配置 URL 列表中的全部主体")
    parser.add_argument("--operator-workbook-url", action="append", default=[], help="直接指定主体普通表格 URL，可重复；跳过文件夹发现")
    parser.add_argument("--operator-root-folder-token", default="")
    parser.add_argument("--operator-root-folder-url", default="")
    parser.add_argument("--operator-folder-template", default="", help="默认 {operator}-运营主体")
    parser.add_argument("--target-table-template", default="", help="默认读取 profile，例如 {operator}-背审申诉")
    parser.add_argument("--header-row", type=int, default=1)
    parser.add_argument("--allow-image-risk", action="store_true", help="允许在存在浮动图片或不可复制富文本风险时继续写纯值；默认阻断")
    parser.add_argument("--confirmed", action="store_true", help="实际写入总表追加+成功行标已提报+结果回填；不加时只 dry-run")
    parser.add_argument(
        "--apply-validation-status",
        action="store_true",
        help="仅把缺项中文提示写入主体状态列（如 M）；不追加总表。可与 dry-run 预览区分：本开关会真实写飞书缺项",
    )
    parser.add_argument("--lark-cli", default="")
    parser.add_argument("--identity", choices=["user", "bot"], default="user")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--request-delay-seconds", type=float, default=1.2)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--no-output-file", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="与 --confirmed 一起允许覆盖已有 summary JSON")
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
    scenario_hint = args.scenario or (Path(args.profile).stem if args.profile else "operator_sync")
    ensure_output_write_authorized(args, scenario_hint)
    config = load_config()
    profile = load_profile(args.profile or args.scenario)
    scenario_id = str(profile.get("scenario_id") or args.scenario or Path(str(profile.get("_profile_path"))).stem)
    profile["_cli"] = None

    master_url = resolve_master_url(args, config, profile)
    operator_folder_template = args.operator_folder_template or str(profile.get("operator_folder_template") or "{operator}-运营主体")
    target_table_template = args.target_table_template or str(profile.get("target_table_template") or "")
    master_sheet = args.master_sheet or str(profile.get("master_sheet_name") or "")
    master_sheet_id = str(profile.get("master_sheet_id") or "").strip()
    source_sheet = str(profile.get("operator_sheet_name") or "")

    cli_urls = [str(item).strip() for item in (args.operator_workbook_url or []) if str(item).strip()]
    configured_entries = resolve_configured_operator_entries(config, scenario_id, cli_urls=cli_urls)
    use_url_operators = bool(configured_entries) or profile_bool(profile, "use_configured_operator_urls", False)

    contact_person = resolve_contact_person(args, config)
    root_folder_token = ""
    if not use_url_operators or not configured_entries:
        if not contact_person:
            raise OperatorSyncError("缺少 --contact-person，且配置中没有默认对接人。")
        root_folder_token = resolve_operator_root_folder(args, config, contact_person)
        if not root_folder_token and not configured_entries:
            raise OperatorSyncError("缺少运营主体根文件夹。请传 --operator-root-folder-url，或在 config/fog_config.yaml 配置。")
    elif not contact_person:
        contact_person = "config"

    requested = parse_csv_arg(args.operator)
    if not args.all_operators and not requested:
        requested = profile_list(profile, "default_operators")
    if not args.all_operators and not requested and not configured_entries:
        raise OperatorSyncError("请传 --operator，或使用 --all-operators；也可在 profile 配置 default_operators。")

    if configured_entries and not target_table_template:
        target_table_template = "{operator}"
    if not configured_entries and not target_table_template:
        raise OperatorSyncError("profile.target_table_template 不能为空。")

    cli = LarkCli(resolve_lark_cli(config, args.lark_cli), identity=args.identity, timeout=args.timeout)
    profile["_cli"] = cli
    master = read_table(
        cli,
        master_url,
        expected_sheet_name=master_sheet,
        expected_sheet_id=master_sheet_id,
        header_row=args.header_row,
        label="大表格",
    )
    if configured_entries:
        workbooks, missing_targets, operators_requested = resolve_operator_workbooks_from_urls(
            cli,
            configured_entries,
            [] if args.all_operators and not requested else requested,
            request_delay_seconds=args.request_delay_seconds,
        )
    else:
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
        tolerate_errors=args.all_operators or bool(configured_entries),
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
    if args.apply_validation_status and args.confirmed:
        raise OperatorSyncError("请勿同时传 --apply-validation-status 与 --confirmed；confirmed 已包含缺项提示写入。")

    append_rows: list[AppendRow] = plan["append_rows"]
    image_copies: list[ImageCopyTask] = plan["image_copies"]
    status_header_updates: list[CellUpdate] = plan["status_header_updates"]
    status_updates: list[CellUpdate] = plan["status_updates"]
    result_updates: list[CellUpdate] = plan["result_updates"]
    write_results: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    validation_updates = [item for item in status_updates if item.reason == "validation_status"]
    duplicate_status_updates = [item for item in status_updates if item.reason == "source_duplicate"]
    submitted_updates = [
        item for item in status_updates if item.reason not in {"validation_status", "source_duplicate"}
    ]
    if args.confirmed:
        write_results["append"] = write_append_rows(cli, master, append_rows, args.request_delay_seconds) if append_rows else []
        write_results["image_copies"] = write_image_copies(cli, image_copies, args.request_delay_seconds) if image_copies else []
        updates = status_header_updates + status_updates + result_updates
        write_results["updates"] = write_updates(cli, updates, args.request_delay_seconds) if updates else []
        key_columns = profile_list(profile, "key_columns")
        verification["append_keys"] = verify_append_keys(cli, master, append_rows, key_columns)
        verification["image_copies"] = verify_image_copies(cli, image_copies)
        verification["updates"] = verify_updates(cli, updates)
        failed = [item for group in verification.values() for item in group if not item.get("ok")]
        if failed:
            raise OperatorSyncError("写后验证失败: " + json.dumps(failed[:10], ensure_ascii=False))
    elif args.apply_validation_status:
        updates = status_header_updates + validation_updates + duplicate_status_updates
        write_results["validation_status"] = write_updates(cli, updates, args.request_delay_seconds) if updates else []
        verification["validation_status"] = verify_updates(cli, updates)
        failed = [item for item in verification["validation_status"] if not item.get("ok")]
        if failed:
            raise OperatorSyncError("缺项提示写后验证失败: " + json.dumps(failed[:10], ensure_ascii=False))

    result: dict[str, Any] = {
        "ok": not has_blocking,
        "dry_run": not args.confirmed and not args.apply_validation_status,
        "apply_validation_status": bool(args.apply_validation_status and not args.confirmed),
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
        "image_copy_count": len(image_copies),
        "image_copies": [image_copy_to_dict(copy_task) for copy_task in image_copies[:200]],
        "already_in_master_count": len(plan["already_in_master"]),
        "already_in_master": plan["already_in_master"][:200],
        "status_header_update_count": len(status_header_updates),
        "status_update_count": len(status_updates),
        "validation_status_update_count": len(validation_updates),
        "submitted_status_update_count": len(submitted_updates),
        "status_updates": [cell_update_to_dict(update) for update in status_updates[:200]],
        "result_writeback_count": len(result_updates),
        "result_updates": [cell_update_to_dict(update) for update in result_updates[:200]],
        "skipped_count": len(plan["skipped"]),
        "skipped": plan["skipped"][:200],
        "blocking": plan["blocking"],
        "duplicate_warnings": plan.get("duplicate_warnings") or [],
        "source_duplicates": plan.get("source_duplicates") or [],
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
