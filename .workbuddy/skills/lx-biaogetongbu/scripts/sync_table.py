#!/usr/bin/env python3
"""Append rows from one local Excel table into another with audit output."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet


SUPPORTED_SUFFIXES = {".xlsx", ".xlsm"}


class SyncError(Exception):
    """Expected user-facing sync failure."""


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".workbuddy" / "skills").is_dir() and (candidate / "workspace").is_dir():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()


def resolve_path(value: str | None, *, required: bool = False) -> Path | None:
    if not value:
        if required:
            raise SyncError("缺少必填路径参数")
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_profile(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        raise SyncError(f"profile 不存在: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SyncError(f"profile 必须是 JSON object: {path}")
    return data


def first_value(cli_value: Any, profile: dict[str, Any], key: str, default: Any = None) -> Any:
    if cli_value not in (None, "", []):
        return cli_value
    return profile.get(key, default)


def parse_pairs(values: list[str] | None, label: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise SyncError(f"{label} 参数格式错误，应为 源=目标: {raw}")
        left, right = raw.split("=", 1)
        left = left.strip()
        right = right.strip()
        if not left or not right:
            raise SyncError(f"{label} 参数不能为空: {raw}")
        pairs[left] = right
    return pairs


def profile_mapping(value: Any) -> dict[str, str]:
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, list):
        return parse_pairs([str(item) for item in value], "profile.mapping")
    raise SyncError("profile.mapping 必须是 object 或 list")


def split_keys(values: list[str] | str | None) -> list[str]:
    if not values:
        return []
    raw_values = [values] if isinstance(values, str) else values
    keys: list[str] = []
    for raw in raw_values:
        for part in str(raw).split(","):
            key = part.strip()
            if key:
                keys.append(key)
    return keys


def normalize_header(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalize_key_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def require_excel(path: Path, label: str) -> None:
    if not path.exists():
        raise SyncError(f"{label} 不存在: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SyncError(f"{label} 只支持 .xlsx / .xlsm: {path}")


def select_sheet(workbook: Any, sheet_name: str | None, label: str) -> Worksheet:
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            raise SyncError(f"{label} sheet 不存在: {sheet_name}")
        return workbook[sheet_name]
    return workbook.active


def read_headers(ws: Worksheet, header_row: int) -> dict[str, int]:
    headers: dict[str, int] = {}
    duplicates: list[str] = []
    for cell in ws[header_row]:
        name = normalize_header(cell.value)
        if not name:
            continue
        if name in headers:
            duplicates.append(name)
            continue
        headers[name] = cell.column
    if duplicates:
        raise SyncError(f"{ws.title} 表头存在重复列: {', '.join(sorted(set(duplicates)))}")
    if not headers:
        raise SyncError(f"{ws.title} 第 {header_row} 行没有可用表头")
    return headers


def row_is_blank(values: dict[str, Any]) -> bool:
    return all(value in (None, "") for value in values.values())


def read_rows(ws: Worksheet, headers: dict[str, int], header_row: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_idx in range(header_row + 1, ws.max_row + 1):
        row = {header: ws.cell(row=row_idx, column=col_idx).value for header, col_idx in headers.items()}
        if row_is_blank(row):
            continue
        rows.append(row)
    return rows


def add_missing_target_columns(
    ws: Worksheet,
    target_headers: dict[str, int],
    needed_columns: list[str],
    header_row: int,
) -> dict[str, int]:
    next_col = max(target_headers.values(), default=0) + 1
    for column_name in needed_columns:
        if column_name in target_headers:
            continue
        ws.cell(row=header_row, column=next_col).value = column_name
        target_headers[column_name] = next_col
        next_col += 1
    return target_headers


def build_mapping(
    source_headers: dict[str, int],
    target_headers: dict[str, int],
    explicit_mapping: dict[str, str],
) -> dict[str, str]:
    if explicit_mapping:
        missing_source = [name for name in explicit_mapping if name not in source_headers]
        if missing_source:
            raise SyncError(f"A 表缺少映射源列: {', '.join(missing_source)}")
        missing_target = [name for name in explicit_mapping.values() if name not in target_headers]
        if missing_target:
            raise SyncError(f"B 表缺少映射目标列: {', '.join(missing_target)}")
        return explicit_mapping

    common = sorted(set(source_headers) & set(target_headers))
    if not common:
        raise SyncError("A 表和 B 表没有同名列，请使用 --map 显式指定字段映射")
    return {name: name for name in common}


def resolve_key_columns(keys: list[str], mapping: dict[str, str], target_headers: dict[str, int]) -> list[str]:
    resolved: list[str] = []
    for key in keys:
        if key in target_headers:
            resolved.append(key)
        elif key in mapping:
            target_key = mapping[key]
            if target_key not in target_headers:
                raise SyncError(f"去重键映射到不存在的 B 表列: {key} -> {target_key}")
            resolved.append(target_key)
        else:
            raise SyncError(f"去重键不在 B 表列或映射源列中: {key}")
    return resolved


def target_key(row: dict[str, Any], key_columns: list[str]) -> tuple[str, ...]:
    return tuple(normalize_key_value(row.get(column)) for column in key_columns)


def make_target_rows(
    source_rows: list[dict[str, Any]],
    mapping: dict[str, str],
    literals: dict[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source_row in source_rows:
        target_row = {target: source_row.get(source) for source, target in mapping.items()}
        target_row.update(literals)
        result.append(target_row)
    return result


def existing_keys(
    target_rows: list[dict[str, Any]],
    key_columns: list[str],
) -> set[tuple[str, ...]]:
    keys: set[tuple[str, ...]] = set()
    for row in target_rows:
        key = target_key(row, key_columns)
        if any(key):
            keys.add(key)
    return keys


def filter_append_rows(
    rows: list[dict[str, Any]],
    key_columns: list[str],
    seen: set[tuple[str, ...]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    append_rows: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    batch_seen: set[tuple[str, ...]] = set()

    for index, row in enumerate(rows, 1):
        if not key_columns:
            append_rows.append(row)
            continue

        key = target_key(row, key_columns)
        key_text = " | ".join(key)
        if not any(key):
            skipped.append((str(index), "去重键为空"))
            continue
        if key in seen:
            skipped.append((key_text, "B 表已存在"))
            continue
        if key in batch_seen:
            skipped.append((key_text, "A 表本次重复"))
            continue
        batch_seen.add(key)
        append_rows.append(row)

    return append_rows, skipped


def copy_row_style(ws: Worksheet, from_row: int, to_row: int, max_col: int) -> None:
    if from_row < 1:
        return
    for col in range(1, max_col + 1):
        source = ws.cell(row=from_row, column=col)
        target = ws.cell(row=to_row, column=col)
        if source.has_style:
            target._style = copy.copy(source._style)
        if source.number_format:
            target.number_format = source.number_format
        if source.alignment:
            target.alignment = copy.copy(source.alignment)


def append_to_sheet(ws: Worksheet, rows: list[dict[str, Any]], target_headers: dict[str, int]) -> None:
    header_order = sorted(target_headers.items(), key=lambda item: item[1])
    start_row = ws.max_row + 1
    style_row = ws.max_row if ws.max_row >= 1 else 0
    max_col = max(target_headers.values(), default=0)

    for offset, row_data in enumerate(rows):
        row_idx = start_row + offset
        copy_row_style(ws, style_row, row_idx, max_col)
        for header, col_idx in header_order:
            if header in row_data:
                ws.cell(row=row_idx, column=col_idx).value = row_data[header]


def write_report(
    report_dir: Path,
    *,
    mode: str,
    source: Path,
    target: Path,
    output: Path | None,
    backup: Path | None,
    source_sheet: str,
    target_sheet: str,
    mapping: dict[str, str],
    literals: dict[str, str],
    key_columns: list[str],
    source_count: int,
    target_count: int,
    append_count: int,
    skipped: list[tuple[str, str]],
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"{timestamp}_lx-biaogetongbu_处理日志.md"

    lines = [
        "# lx-biaogetongbu 表格同步处理日志",
        "",
        f"**处理时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**模式**: {mode}",
        f"**A 表**: {source}",
        f"**B 表**: {target}",
        f"**A sheet**: {source_sheet}",
        f"**B sheet**: {target_sheet}",
    ]
    if output:
        lines.append(f"**输出文件**: {output}")
    if backup:
        lines.append(f"**B 表备份**: {backup}")

    lines.extend(
        [
            "",
            "## 统计",
            "",
            "| 指标 | 数值 |",
            "|---|---:|",
            f"| A 表有效行 | {source_count} |",
            f"| B 表已有行 | {target_count} |",
            f"| 本次追加行 | {append_count} |",
            f"| 跳过行 | {len(skipped)} |",
            "",
            "## 字段映射",
            "",
            "| A 表列 | B 表列 |",
            "|---|---|",
        ]
    )
    for source_col, target_col in mapping.items():
        lines.append(f"| {source_col} | {target_col} |")

    if literals:
        lines.extend(["", "## 固定写入", "", "| B 表列 | 固定值 |", "|---|---|"])
        for target_col, value in literals.items():
            lines.append(f"| {target_col} | {value} |")

    lines.extend(["", "## 去重键", "", ", ".join(key_columns) if key_columns else "未设置，全部追加"])

    if skipped:
        lines.extend(["", "## 跳过记录", "", "| 标识 | 原因 |", "|---|---|"])
        for identifier, reason in skipped[:200]:
            lines.append(f"| {identifier} | {reason} |")
        if len(skipped) > 200:
            lines.append(f"| ... | 还有 {len(skipped) - 200} 条未展示 |")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 A 表追加同步记录到 B 表。")
    parser.add_argument("--profile", help="JSON profile 路径，可预置 sheet、mapping、key、literal")
    parser.add_argument("--source", help="A 表 Excel 路径")
    parser.add_argument("--target", help="B 表 Excel 路径")
    parser.add_argument("--output", help="另存输出路径；不传则 confirmed 时写回 B 表")
    parser.add_argument("--source-sheet", help="A 表 sheet 名")
    parser.add_argument("--target-sheet", help="B 表 sheet 名")
    parser.add_argument("--source-header-row", type=int, help="A 表表头行，默认 1")
    parser.add_argument("--target-header-row", type=int, help="B 表表头行，默认 1")
    parser.add_argument("--map", action="append", default=[], help="字段映射，格式 源列=目标列，可重复")
    parser.add_argument("--key", action="append", default=[], help="去重键，可重复，也可逗号分隔")
    parser.add_argument("--literal", action="append", default=[], help="固定写入，格式 目标列=固定值，可重复")
    parser.add_argument("--add-missing-target-columns", action="store_true", help="B 表缺少目标列时自动追加表头")
    parser.add_argument("--report-dir", default="workspace/10表格同步/处理日志", help="处理日志输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入")
    parser.add_argument("--confirmed", action="store_true", help="确认写入")
    return parser


def run(args: argparse.Namespace) -> int:
    profile_path = resolve_path(args.profile) if args.profile else None
    profile = load_profile(profile_path)

    source = resolve_path(first_value(args.source, profile, "source"), required=True)
    target = resolve_path(first_value(args.target, profile, "target"), required=True)
    assert source is not None and target is not None
    output = resolve_path(first_value(args.output, profile, "output")) if first_value(args.output, profile, "output") else None
    report_dir = resolve_path(args.report_dir, required=True)
    assert report_dir is not None

    source_sheet_name = first_value(args.source_sheet, profile, "source_sheet")
    target_sheet_name = first_value(args.target_sheet, profile, "target_sheet")
    source_header_row = int(first_value(args.source_header_row, profile, "source_header_row", 1))
    target_header_row = int(first_value(args.target_header_row, profile, "target_header_row", 1))
    explicit_mapping = profile_mapping(profile.get("mapping"))
    explicit_mapping.update(parse_pairs(args.map, "--map"))
    literals = profile_mapping(profile.get("literals"))
    literals.update(parse_pairs(args.literal, "--literal"))
    key_columns_raw = split_keys(first_value(args.key, profile, "keys", []))
    add_missing = bool(args.add_missing_target_columns or profile.get("add_missing_target_columns"))

    if args.dry_run == args.confirmed:
        raise SyncError("必须且只能选择一个模式：--dry-run 或 --confirmed")
    require_excel(source, "A 表")
    require_excel(target, "B 表")
    if output and output.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SyncError(f"输出文件只支持 .xlsx / .xlsm: {output}")

    source_wb = load_workbook(source, data_only=True)
    target_wb = load_workbook(target, keep_vba=target.suffix.lower() == ".xlsm")
    source_ws = select_sheet(source_wb, source_sheet_name, "A 表")
    target_ws = select_sheet(target_wb, target_sheet_name, "B 表")

    source_headers = read_headers(source_ws, source_header_row)
    target_headers = read_headers(target_ws, target_header_row)
    missing_literal_columns = [name for name in literals if name not in target_headers]
    if add_missing:
        target_headers = add_missing_target_columns(
            target_ws,
            target_headers,
            list(explicit_mapping.values()) + list(literals),
            target_header_row,
        )
    elif missing_literal_columns:
        raise SyncError(f"B 表缺少固定写入目标列: {', '.join(missing_literal_columns)}")

    mapping = build_mapping(source_headers, target_headers, explicit_mapping)
    key_columns = resolve_key_columns(key_columns_raw, mapping, target_headers)
    source_rows = read_rows(source_ws, source_headers, source_header_row)
    target_rows = read_rows(target_ws, target_headers, target_header_row)
    mapped_rows = make_target_rows(source_rows, mapping, literals)
    append_rows, skipped = filter_append_rows(mapped_rows, key_columns, existing_keys(target_rows, key_columns))

    mode = "dry-run" if args.dry_run else "confirmed"
    backup: Path | None = None
    if args.confirmed and append_rows:
        save_path = output or target
        save_path.parent.mkdir(parents=True, exist_ok=True)
        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = target.with_name(f"{target.name}.bak.{timestamp}")
            shutil.copy2(target, backup)
        append_to_sheet(target_ws, append_rows, target_headers)
        target_wb.save(save_path)

    report_path = write_report(
        report_dir,
        mode=mode,
        source=source,
        target=target,
        output=output,
        backup=backup,
        source_sheet=source_ws.title,
        target_sheet=target_ws.title,
        mapping=mapping,
        literals=literals,
        key_columns=key_columns,
        source_count=len(source_rows),
        target_count=len(target_rows),
        append_count=len(append_rows),
        skipped=skipped,
    )

    print(f"模式: {mode}")
    print(f"A 表有效行: {len(source_rows)}")
    print(f"B 表已有行: {len(target_rows)}")
    print(f"本次追加行: {len(append_rows)}")
    print(f"跳过行: {len(skipped)}")
    if backup:
        print(f"B 表备份: {backup}")
    if output:
        print(f"输出文件: {output}")
    print(f"处理日志: {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SyncError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
