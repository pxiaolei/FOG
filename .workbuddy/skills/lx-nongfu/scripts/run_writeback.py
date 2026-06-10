#!/usr/bin/env python3
"""Write operator-filled rows back to a Feishu master sheet.

Default behavior is dry-run. Use --confirmed to update the master sheet.
Rows are matched by brand + city, never by row number.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from run_split_publish import (
    LarkCli,
    NongfuError,
    PROJECT_ROOT,
    TargetWorkbook,
    a1_range,
    auto_header_row,
    choose_source_sheet,
    col_to_a1,
    configured_list,
    configured_value_map,
    find_column,
    load_config,
    parse_annotated_csv,
    read_sheet_rows,
    resolve_lark_cli,
    resolve_operator_root_folder,
    resolve_targets,
    rows_to_csv,
    sheet_records,
    workbook_info,
)


@dataclass
class SheetTable:
    operator: str
    target: TargetWorkbook
    sheet_id: str
    sheet_name: str
    rows: list[list[str]]
    header_row_number: int
    headers: list[str]
    brand_col: int
    city_col: int
    update_cols: dict[str, int]


@dataclass
class Change:
    operator: str
    brand: str
    city: str
    column: str
    row_number: int
    column_number: int
    cell: str
    old_value: str
    new_value: str


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_update_columns(raw: str, config_columns: list[str]) -> list[str]:
    columns = parse_csv_list(raw) if raw else [str(item).strip() for item in config_columns if str(item).strip()]
    seen: set[str] = set()
    result: list[str] = []
    for column in columns:
        if column in seen:
            continue
        seen.add(column)
        result.append(column)
    if not result:
        raise NongfuError("缺少回填字段。请传 --update-columns，或在配置 lx_nongfu.large_doc.writeback_update_columns 中提供默认值。")
    return result


def parse_operator_args(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for item in parse_csv_list(raw):
            if item not in seen:
                seen.add(item)
                result.append(item)
    return result


def read_sheet_by_id(cli: LarkCli, token: str, sheet_id: str, row_count: int, column_count: int) -> list[list[str]]:
    result = cli.sheets(
        [
            "+csv-get",
            "--spreadsheet-token",
            token,
            "--sheet-id",
            sheet_id,
            "--range",
            a1_range(max(row_count, 1), max(column_count, 1)),
        ]
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return parse_annotated_csv(str(data.get("annotated_csv") or ""))


def find_existing_sheet(cli: LarkCli, target: TargetWorkbook, sheet_name: str) -> tuple[str, int, int]:
    info = workbook_info(cli, token=target.spreadsheet_token)
    for sheet in sheet_records(info):
        title = str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "")
        if title != sheet_name:
            continue
        sheet_id = str(sheet.get("sheet_id") or sheet.get("id") or sheet.get("reference_id") or "")
        row_count = int(sheet.get("row_count") or sheet.get("rowCount") or 200)
        column_count = int(sheet.get("column_count") or sheet.get("columnCount") or 20)
        if sheet_id:
            return sheet_id, row_count, column_count
    raise NongfuError(f"{target.operator} 的日常信息表里没有 sheet: {sheet_name}")


def build_table(
    *,
    operator: str,
    target: TargetWorkbook,
    sheet_id: str,
    sheet_name: str,
    rows: list[list[str]],
    brand_fields: list[str],
    city_fields: list[str],
    update_columns: list[str],
    header_row: int,
    max_header_scan_rows: int,
) -> SheetTable:
    if not rows:
        raise NongfuError(f"{operator} / {sheet_name} 没有读到任何行。")
    header_row_number = header_row or auto_header_row(rows, brand_fields, city_fields, max_header_scan_rows)
    headers = rows[header_row_number - 1]
    brand_col = find_column(headers, brand_fields, "品牌")
    city_col = find_column(headers, city_fields, "城市")
    update_cols = {column: find_column(headers, [column], column) for column in update_columns}
    return SheetTable(
        operator=operator,
        target=target,
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        rows=rows,
        header_row_number=header_row_number,
        headers=headers,
        brand_col=brand_col,
        city_col=city_col,
        update_cols=update_cols,
    )


def row_value(row: list[str], index: int) -> str:
    return str(row[index]).strip() if index < len(row) else ""


def build_row_index(table: SheetTable) -> tuple[dict[tuple[str, str], tuple[int, list[str]]], list[dict[str, Any]]]:
    index: dict[tuple[str, str], tuple[int, list[str]]] = {}
    duplicates: list[dict[str, Any]] = []
    for logical_index, row in enumerate(table.rows[table.header_row_number :], start=table.header_row_number + 1):
        brand = row_value(row, table.brand_col)
        city = row_value(row, table.city_col)
        if not brand and not city:
            continue
        key = (brand, city)
        if key in index:
            duplicates.append({"brand": brand, "city": city, "row_number": logical_index})
            continue
        index[key] = (logical_index, row)
    return index, duplicates


def build_writeback_plan(
    master: SheetTable,
    sources: list[SheetTable],
    update_columns: list[str],
    *,
    allow_empty_overwrite: bool = False,
) -> dict[str, Any]:
    master_index, master_duplicates = build_row_index(master)
    source_seen: dict[tuple[str, str], str] = {}
    source_duplicates: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    skipped_empty: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    changes: list[Change] = []

    for source in sources:
        source_index, duplicates = build_row_index(source)
        for duplicate in duplicates:
            source_duplicates.append({"operator": source.operator, **duplicate})
        for (brand, city), (_, row) in source_index.items():
            key = (brand, city)
            if key in source_seen:
                source_duplicates.append(
                    {"operator": source.operator, "brand": brand, "city": city, "previous_operator": source_seen[key]}
                )
                continue
            source_seen[key] = source.operator
            master_hit = master_index.get(key)
            if not master_hit:
                unmatched.append({"operator": source.operator, "brand": brand, "city": city})
                continue
            master_row_number, master_row = master_hit
            for column in update_columns:
                source_col = source.update_cols[column]
                master_col = master.update_cols[column]
                new_value = row_value(row, source_col)
                old_value = row_value(master_row, master_col)
                cell = f"{col_to_a1(master_col + 1)}{master_row_number}"
                if new_value == "" and not allow_empty_overwrite:
                    skipped_empty.append(
                        {"operator": source.operator, "brand": brand, "city": city, "column": column, "cell": cell}
                    )
                    continue
                if old_value == new_value:
                    unchanged.append(
                        {"operator": source.operator, "brand": brand, "city": city, "column": column, "cell": cell}
                    )
                    continue
                changes.append(
                    Change(
                        operator=source.operator,
                        brand=brand,
                        city=city,
                        column=column,
                        row_number=master_row_number,
                        column_number=master_col + 1,
                        cell=cell,
                        old_value=old_value,
                        new_value=new_value,
                    )
                )

    return {
        "changes": changes,
        "master_duplicates": master_duplicates,
        "source_duplicates": source_duplicates,
        "unmatched": unmatched,
        "skipped_empty": skipped_empty,
        "unchanged": unchanged,
    }


def group_contiguous_changes(changes: list[Change]) -> list[list[Change]]:
    groups: list[list[Change]] = []
    for change in sorted(changes, key=lambda item: (item.row_number, item.column_number)):
        if (
            groups
            and groups[-1][-1].row_number == change.row_number
            and groups[-1][-1].column_number + 1 == change.column_number
        ):
            groups[-1].append(change)
        else:
            groups.append([change])
    return groups


def write_changes(cli: LarkCli, master_token: str, master_sheet_id: str, changes: list[Change]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for group in group_contiguous_changes(changes):
        start = group[0]
        values = [[change.new_value for change in group]]
        result = cli.sheets(
            [
                "+csv-put",
                "--spreadsheet-token",
                master_token,
                "--sheet-id",
                master_sheet_id,
                "--start-cell",
                start.cell,
                "--csv",
                "-",
            ],
            input_text=rows_to_csv(values),
        )
        results.append({"range_start": start.cell, "cell_count": len(group), "result": result})
    return results


def verify_changes(cli: LarkCli, master_token: str, master_sheet_id: str, changes: list[Change]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for change in changes:
        result = cli.sheets(
            [
                "+csv-get",
                "--spreadsheet-token",
                master_token,
                "--sheet-id",
                master_sheet_id,
                "--range",
                change.cell,
            ]
        )
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        rows = parse_annotated_csv(str(data.get("annotated_csv") or ""))
        actual = rows[0][0].strip() if rows and rows[0] else ""
        ok = actual == change.new_value
        checks.append({"cell": change.cell, "expected": change.new_value, "actual": actual, "ok": ok})
    return checks


def change_to_dict(change: Change) -> dict[str, Any]:
    return {
        "operator": change.operator,
        "brand": change.brand,
        "city": change.city,
        "column": change.column,
        "cell": change.cell,
        "old_value": change.old_value,
        "new_value": change.new_value,
    }


def default_output_path(sheet_name: str) -> Path:
    output_dir = PROJECT_ROOT / "workspace" / "12农夫协作" / "输出"
    safe_sheet = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", sheet_name).strip("_") or "writeback"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{stamp}_{safe_sheet}_writeback_summary.json"


def write_output_file(result: dict[str, Any], args: argparse.Namespace, sheet_name: str) -> str:
    if args.no_output_file:
        return ""
    path = Path(args.output_json).expanduser() if args.output_json else default_output_path(sheet_name)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lx-nongfu 按品牌+城市回填飞书大文档。")
    parser.add_argument("--master-url", "--source-url", dest="master_url", required=True, help="飞书普通电子表格大文档 URL")
    parser.add_argument("--sheet-name", "--master-sheet", dest="sheet_name", default="", help="要回填的 sheet 名；不填且大文档只有一个 sheet 时自动使用")
    parser.add_argument("--master-range", default="", help="读取大文档范围；默认按工作簿元数据读取全表")
    parser.add_argument("--contact-person", default="", help="对接人；不填则使用 config/fog_config.yaml 的默认对接人")
    parser.add_argument("--operator", action="append", help="要回填的运营主体，可重复传，也可逗号分隔")
    parser.add_argument("--all-operators", action="store_true", help="回填该对接人名下所有可找到同名 sheet 的运营主体")
    parser.add_argument("--update-columns", default="", help="本次回填字段，逗号分隔；优先级高于配置")
    parser.add_argument("--allow-empty-overwrite", action="store_true", help="允许用主体表空值覆盖大文档已有值；默认跳过空值")
    parser.add_argument("--operator-root-folder-token", default="")
    parser.add_argument("--operator-root-folder-url", default="")
    parser.add_argument("--operator-folder-template", default="", help="运营主体文件夹名模板；默认读取配置或 {operator}-运营主体")
    parser.add_argument("--target-table-template", default="", help="目标普通表格名模板；默认读取配置或 {operator}-日常信息")
    parser.add_argument("--header-row", type=int, default=0, help="品牌/城市表头所在行，1-based；默认自动识别")
    parser.add_argument("--max-header-scan-rows", type=int, default=10)
    parser.add_argument("--confirmed", action="store_true", help="实际写入大文档；不加时只 dry-run")
    parser.add_argument("--lark-cli", default="")
    parser.add_argument("--identity", choices=["user", "bot"], default="user")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--no-output-file", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    nongfu = configured_value_map(config, ["lx_nongfu"])
    operator_doc = configured_value_map(config, ["lx_nongfu", "operator_doc"])

    contact_person = args.contact_person
    if not contact_person:
        defaults = configured_list(config, ["lx_nongfu", "default_contact_persons"], [])
        contact_person = defaults[0] if defaults else ""
    if not contact_person:
        raise NongfuError("缺少 --contact-person，且配置里没有 lx_nongfu.default_contact_persons。")

    update_columns = parse_update_columns(
        args.update_columns,
        configured_list(config, ["lx_nongfu", "large_doc", "writeback_update_columns"], []),
    )

    root_folder_token = resolve_operator_root_folder(args, config, contact_person)
    if not root_folder_token:
        raise NongfuError("缺少运营主体根文件夹。请传 --operator-root-folder-url，或在配置中按对接人配置。")

    operator_folder_template = args.operator_folder_template or str(
        operator_doc.get("operator_folder_name_template") or "{operator}-运营主体"
    )
    target_table_template = args.target_table_template or str(
        operator_doc.get("target_table_name_template") or "{operator}-日常信息"
    )

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

    cli = LarkCli(resolve_lark_cli(config, args.lark_cli), identity=args.identity, timeout=args.timeout)

    master_source = choose_source_sheet(cli, args.master_url, args.sheet_name)
    sheet_name = args.sheet_name or master_source.sheet_name
    master_rows = read_sheet_rows(cli, master_source, args.master_range)
    master_stub = TargetWorkbook("MASTER", "", master_source.token, master_source.url, {sheet_name: master_source.sheet_id})
    master = build_table(
        operator="MASTER",
        target=master_stub,
        sheet_id=master_source.sheet_id,
        sheet_name=sheet_name,
        rows=master_rows,
        brand_fields=brand_fields,
        city_fields=city_fields,
        update_columns=update_columns,
        header_row=args.header_row,
        max_header_scan_rows=args.max_header_scan_rows,
    )

    requested_operators = parse_operator_args(args.operator)
    if args.all_operators:
        # Use the database mapping already maintained by split-publish through the operator folders.
        # Resolving targets below naturally limits work to existing operator folders and daily-info sheets.
        from run_split_publish import load_operator_mapping

        mapping, conflicts, _ = load_operator_mapping(contact_person, 1000)
        if conflicts:
            raise NongfuError("operator_brand 存在品牌城市归属冲突: " + json.dumps(conflicts, ensure_ascii=False))
        requested_operators = sorted(set(mapping.values()))
    if not requested_operators:
        raise NongfuError("请传 --operator，或使用 --all-operators。")

    targets = resolve_targets(
        cli,
        root_folder_token,
        requested_operators,
        operator_folder_template,
        target_table_template,
    )

    sources: list[SheetTable] = []
    missing_targets: list[dict[str, str]] = []
    missing_sheets: list[dict[str, str]] = []
    for operator in requested_operators:
        target = targets.get(operator)
        if not target:
            missing_targets.append({"operator": operator, "reason": "target_workbook_not_found"})
            continue
        try:
            sheet_id, row_count, column_count = find_existing_sheet(cli, target, sheet_name)
        except NongfuError as exc:
            missing_sheets.append({"operator": operator, "reason": str(exc)})
            continue
        rows = read_sheet_by_id(cli, target.spreadsheet_token, sheet_id, row_count, column_count)
        sources.append(
            build_table(
                operator=operator,
                target=target,
                sheet_id=sheet_id,
                sheet_name=sheet_name,
                rows=rows,
                brand_fields=brand_fields,
                city_fields=city_fields,
                update_columns=update_columns,
                header_row=args.header_row,
                max_header_scan_rows=args.max_header_scan_rows,
            )
        )

    plan = build_writeback_plan(
        master,
        sources,
        update_columns,
        allow_empty_overwrite=args.allow_empty_overwrite,
    )
    blocking = {
        "missing_targets": missing_targets,
        "missing_sheets": missing_sheets,
        "master_duplicates": plan["master_duplicates"],
        "source_duplicates": plan["source_duplicates"],
        "unmatched": plan["unmatched"],
    }
    has_blocking = any(blocking.values())
    if has_blocking and args.confirmed:
        raise NongfuError("存在回填阻塞项，已停止写入: " + json.dumps(blocking, ensure_ascii=False)[:2000])

    changes: list[Change] = plan["changes"]
    write_results: list[dict[str, Any]] = []
    verification: list[dict[str, Any]] = []
    if args.confirmed and changes:
        write_results = write_changes(cli, master_source.token, master_source.sheet_id, changes)
        verification = verify_changes(cli, master_source.token, master_source.sheet_id, changes)
        if not all(item["ok"] for item in verification):
            raise NongfuError("写后验证失败: " + json.dumps(verification, ensure_ascii=False))

    result: dict[str, Any] = {
        "ok": not has_blocking,
        "dry_run": not args.confirmed,
        "contact_person": contact_person,
        "master": {
            "url": master_source.url,
            "sheet_name": sheet_name,
            "sheet_id": master_source.sheet_id,
            "read_rows": len(master_rows),
        },
        "operators_requested": requested_operators,
        "operators_loaded": [source.operator for source in sources],
        "update_columns": update_columns,
        "change_count": len(changes),
        "changes": [change_to_dict(change) for change in changes],
        "unchanged_count": len(plan["unchanged"]),
        "unchanged": plan["unchanged"][:50],
        "skipped_empty_count": len(plan["skipped_empty"]),
        "skipped_empty": plan["skipped_empty"][:50],
        "blocking": blocking,
        "write_results": write_results,
        "verification": verification,
    }
    output_path = write_output_file(result, args, sheet_name)
    if output_path:
        result["output_json"] = output_path
        Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NongfuError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
