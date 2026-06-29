#!/usr/bin/env python3
"""Incrementally sync operator-filled resource IDs back to the master sheet.

Detects newly-filled resource IDs by comparing current operator sheet state
against a snapshot from the previous sync run. Only writes ID values that
have changed from empty -> filled since the last sync.

Default is dry-run (preview only). Use --confirmed to write to the master.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from run_split_publish import (
    LarkCli,
    NongfuError,
    PROJECT_ROOT,
    a1_range,
    TargetWorkbook,
    col_to_a1,
    configured_list,
    configured_value_map,
    extract_sheet_token,
    file_type,
    file_url,
    list_drive_files,
    load_config,
    parse_annotated_csv,
    resolve_lark_cli,
    resolve_operator_root_folder,
    rows_to_csv,
    sheet_records,
    workbook_info,
)

# ── column layout types ──────────────────────────────────────────────
# Type A: D=对接同学, E=首页banner, F=首页横栏, G=首页开屏, H=首页侧边栏banner
# Type B: D=首页banner, E=首页横栏, F=首页开屏, G=首页侧边栏banner
ID_FIELDS = ["首页banner", "首页横栏", "首页开屏", "首页侧边栏banner"]
MASTER_COLUMNS = {  # field -> master column letter
    "首页banner": "E",
    "首页横栏": "F",
    "首页开屏": "G",
    "首页侧边栏banner": "H",
}
CONTACT_OPERATORS = {"LX", "哈啰文山", "小象快跑", "逸乘金华"}


@dataclass
class SyncChange:
    """A single ID value that changed from empty to filled since last snapshot."""

    operator: str
    brand: str
    city: str
    field: str
    master_row: int
    cell: str
    old_value: str
    new_value: str


# ── snapshot I/O ─────────────────────────────────────────────────────


def snapshot_dir() -> Path:
    path = PROJECT_ROOT / "workspace" / "12农夫协作" / "缓存"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_file(contact_person: str, topic_sheet_name: str) -> Path:
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", topic_sheet_name).strip("_") or "sync"
    return snapshot_dir() / f"id_sync_{contact_person}_{safe}.json"


def load_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "operators": {}}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def merge_snapshot(
    prev: dict[str, Any],
    operator: str,
    token: str,
    sheet_id: str,
    current_ids: dict[tuple[str, str], dict[str, str]],
    master_index: dict[tuple[str, str], int],
    timestamp: str,
) -> dict[str, Any]:
    """Merge current operator state into snapshot, preserving previously-synced values."""
    new_snapshot = prev.copy()
    new_snapshot["timestamp"] = timestamp
    if "operators" not in new_snapshot:
        new_snapshot["operators"] = {}

    op_data: dict[str, Any] = {
        "spreadsheet_token": token,
        "sheet_id": sheet_id,
        "rows": {},
    }
    for (brand, city), ids in current_ids.items():
        key = f"{brand}/{city}"
        master_row = master_index.get((brand, city))
        op_data["rows"][key] = {
            "master_row": master_row,
            "banner": ids.get("banner", ""),
            "henglan": ids.get("henglan", ""),
            "kaiping": ids.get("kaiping", ""),
            "sidebar": ids.get("sidebar", ""),
        }

    new_snapshot["operators"][operator] = op_data
    return new_snapshot


# ── reading operator / master sheets ─────────────────────────────────


def detect_operator_layout(cli: LarkCli, target: Any, sheet_id: str, operator_name: str) -> str:
    """Detect operator sheet column layout: A (D=对接同学) or B (D=ID)."""
    # Fast path: known operators
    if operator_name in CONTACT_OPERATORS:
        return "A"
    # Verify by reading header row 2 column D
    result = cli.sheets(
        [
            "+cells-get",
            "--spreadsheet-token",
            target.spreadsheet_token,
            "--sheet-id",
            sheet_id,
            "--range",
            "D2:D2",
        ]
    )
    ranges = result.get("data", {}).get("ranges", [])
    if ranges and ranges[0].get("cells") and ranges[0]["cells"][0]:
        value = ranges[0]["cells"][0][0].get("value", "")
        if "对接" in str(value):
            return "A"
    return "B"


def read_operator_ids(
    cli: LarkCli, target: Any, sheet_id: str, operator_name: str
) -> tuple[dict[tuple[str, str], dict[str, str]], str]:
    """Read (brand, city) -> {banner, henglan, kaiping, sidebar} mapping."""
    layout = detect_operator_layout(cli, target, sheet_id, operator_name)
    if layout == "A":
        cols = [4, 5, 6, 7]  # E, F, G, H (0-indexed)
        end_col = "H"
    else:
        cols = [3, 4, 5, 6]  # D, E, F, G
        end_col = "G"

    result = cli.sheets(
        [
            "+csv-get",
            "--spreadsheet-token",
            target.spreadsheet_token,
            "--sheet-id",
            sheet_id,
            "--range",
            f"A3:{end_col}500",
        ]
    )
    data = result.get("data", {})
    rows = parse_annotated_csv(str(data.get("annotated_csv", "")))

    records: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        brand = str(row[0]).strip() if len(row) > 0 else ""
        city = str(row[1]).strip() if len(row) > 1 else ""
        if not brand:
            continue
        records[(brand, city)] = {
            "banner": str(row[cols[0]]).strip() if len(row) > cols[0] else "",
            "henglan": str(row[cols[1]]).strip() if len(row) > cols[1] else "",
            "kaiping": str(row[cols[2]]).strip() if len(row) > cols[2] else "",
            "sidebar": str(row[cols[3]]).strip() if len(row) > cols[3] else "",
        }
    return records, layout


def read_master_index(cli: LarkCli, master_token: str, master_sheet_id: str) -> dict[tuple[str, str], int]:
    """Read master sheet A-B columns in segments, return (brand, city) -> 1-based row."""
    index: dict[tuple[str, str], int] = {}
    for start in range(1, 3000, 50):
        result = cli.sheets(
            [
                "+csv-get",
                "--spreadsheet-token",
                master_token,
                "--sheet-id",
                master_sheet_id,
                "--range",
                f"A{start}:B{start + 49}",
            ]
        )
        data = result.get("data", {})
        rows = parse_annotated_csv(str(data.get("annotated_csv", "")))
        if not rows:
            break
        for i, row in enumerate(rows):
            brand = str(row[0]).strip() if len(row) > 0 else ""
            city = str(row[1]).strip() if len(row) > 1 else ""
            # Skip empty rows but keep partial entries
            if not brand:
                continue
            key = (brand, city)
            if key not in index:  # first occurrence wins
                index[key] = start + i
        if len(rows) < 50:
            break
    return index


def read_master_existing_ids(
    cli: LarkCli, master_token: str, master_sheet_id: str, master_index: dict[tuple[str, str], int]
) -> dict[tuple[str, str], dict[str, str]]:
    """Read existing E-H values from master for matched rows, in segments."""
    existing: dict[tuple[str, str], dict[str, str]] = {}

    # Group rows into 50-row segments
    all_rows = sorted(set(master_index.values()))
    for seg_start in range(0, len(all_rows), 50):
        batch = all_rows[seg_start : seg_start + 50]
        if not batch:
            break
        range_text = f"E{min(batch)}:H{max(batch)}"
        result = cli.sheets(
            [
                "+csv-get",
                "--spreadsheet-token",
                master_token,
                "--sheet-id",
                master_sheet_id,
                "--range",
                range_text,
            ]
        )
        rows = parse_annotated_csv(str(result.get("data", {}).get("annotated_csv", "")))
        # Map each row back to its original row number
        for i, internal_row in enumerate(rows):
            real_row = batch[0] + i
            # Find which (brand, city) maps to this row
            for key, row_num in master_index.items():
                if row_num == real_row:
                    existing[key] = {
                        "banner": str(internal_row[0]).strip() if len(internal_row) > 0 else "",
                        "henglan": str(internal_row[1]).strip() if len(internal_row) > 1 else "",
                        "kaiping": str(internal_row[2]).strip() if len(internal_row) > 2 else "",
                        "sidebar": str(internal_row[3]).strip() if len(internal_row) > 3 else "",
                    }
                    break

    return existing


# ── auto-discover operator targets ───────────────────────────────────


def discover_operator_targets(
    cli: LarkCli,
    root_folder_token: str,
    operator_folder_template: str,
    target_table_template: str,
) -> dict[str, TargetWorkbook]:
    """Auto-discover all operator daily-info workbooks under the root folder."""
    root_files = list_drive_files(cli, root_folder_token)
    folder_by_name: dict[str, str] = {}
    for item in root_files:
        if file_type(item) == "folder":
            name = str(item.get("name") or "")
            token = str(item.get("token") or item.get("file_token") or "")
            if name and token:
                folder_by_name[name] = token

    # Extract operator name from folder name using the template pattern
    # Template: "{operator}-运营主体" -> extract operator part
    prefix = operator_folder_template.split("{operator}")[0]
    suffix = operator_folder_template.split("{operator}")[1] if "{operator}" in operator_folder_template else ""

    result: dict[str, TargetWorkbook] = {}
    for folder_name, folder_token in sorted(folder_by_name.items()):
        # Match template pattern
        if not (folder_name.startswith(prefix) and folder_name.endswith(suffix)):
            continue
        operator_name = folder_name[len(prefix) : -len(suffix)] if suffix else folder_name[len(prefix) :]
        if not operator_name:
            continue

        target_name = target_table_template.format(operator=operator_name)
        files = list_drive_files(cli, folder_token)
        target_file = next(
            (
                f
                for f in files
                if str(f.get("name") or "") == target_name and file_type(f) == "sheet"
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
            sn = str(sheet.get("sheet_name") or sheet.get("title") or sheet.get("name") or "")
            si = str(sheet.get("sheet_id") or sheet.get("id") or sheet.get("reference_id") or "")
            if sn and si:
                existing[sn] = si
        result[operator_name] = TargetWorkbook(
            operator=operator_name,
            folder_token=folder_token,
            spreadsheet_token=token,
            url=url,
            existing_sheets=existing,
        )

    return result


# ── diff logic ───────────────────────────────────────────────────────


def diff(
    current: dict[tuple[str, str], dict[str, str]],
    snapshot_operator: dict[str, Any],
    master_index: dict[tuple[str, str], int],
    master_existing: dict[tuple[str, str], dict[str, str]],
    operator_name: str,
) -> list[SyncChange]:
    """Find IDs that are new since the last snapshot and master cell is still empty."""
    changes: list[SyncChange] = []
    prev_rows = snapshot_operator.get("rows", {})

    for (brand, city), ids in current.items():
        key = f"{brand}/{city}"
        prev_ids = prev_rows.get(key, {})
        master_row = master_index.get((brand, city))
        if not master_row:
            continue

        master_ids = master_existing.get((brand, city), {})

        for field, col_letter in MASTER_COLUMNS.items():
            new_val = ids.get(field, "")
            old_snapshot_val = prev_ids.get(field, "")
            master_current_val = master_ids.get(field, "")

            # Skip if no new value, or already had a value in snapshot
            if not new_val:
                continue
            if old_snapshot_val and old_snapshot_val != "(空)":
                continue

            # Check master: skip if master already has this value (or a different one)
            if master_current_val:
                # Already filled in master — treat snapshot as stale, update it
                continue

            changes.append(
                SyncChange(
                    operator=operator_name,
                    brand=brand,
                    city=city,
                    field=field,
                    master_row=master_row,
                    cell=f"{col_letter}{master_row}",
                    old_value=old_snapshot_val or master_current_val or "(空)",
                    new_value=new_val,
                )
            )

    return changes


# ── writeback ────────────────────────────────────────────────────────


def write_changes(
    cli: LarkCli, master_token: str, master_sheet_id: str, changes: list[SyncChange]
) -> list[dict[str, Any]]:
    """Write individual cell values to master sheet using cells-set."""
    results: list[dict[str, Any]] = []
    for change in changes:
        cells_json = json.dumps([[{"value": change.new_value}]], ensure_ascii=False)
        result = cli.sheets(
            [
                "+cells-set",
                "--spreadsheet-token",
                master_token,
                "--sheet-id",
                master_sheet_id,
                "--range",
                f"{change.cell}:{change.cell}",
                "--cells",
                cells_json,
            ]
        )
        results.append(
            {
                "cell": change.cell,
                "value": change.new_value,
                "ok": result.get("ok", False),
            }
        )
        time.sleep(0.6)  # rate limit
    return results


# ── report ───────────────────────────────────────────────────────────


def report_text(changes: list[SyncChange], no_id_summary: dict[str, list[str]]) -> str:
    """Generate human-readable preview report."""
    lines = ["# 增量同步预览\n"]

    if not changes:
        lines.append("**无新增 ID，所有已填 ID 均已同步。**")
    else:
        lines.append(f"## 待同步 ({len(changes)} 个单元格)\n")
        by_op: dict[str, list[SyncChange]] = {}
        for ch in changes:
            by_op.setdefault(ch.operator, []).append(ch)

        for op_name, items in sorted(by_op.items()):
            lines.append(f"### {op_name}\n")
            for ch in items:
                lines.append(f"- **{ch.brand}** / {ch.city}  `{ch.field}`: {ch.old_value} → **{ch.new_value}**  ({ch.cell})")
            lines.append("")

    if no_id_summary:
        lines.append("## 尚未填写 ID\n")
        for op_name, items in sorted(no_id_summary.items()):
            lines.append(f"- **{op_name}**: {', '.join(items)}（共 {len(items)} 个品牌城市）")
        lines.append("")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lx-nongfu 增量同步运营主体 ID 到飞书大文档。")
    parser.add_argument("--master-url", required=True, help="飞书大文档普通电子表格 URL")
    parser.add_argument("--master-sheet", default="", help="大文档 sheet 名；不填且仅 1 个 sheet 时自动使用")
    parser.add_argument("--topic-sheet-name", required=True, help="运营主体日常信息中的 topic sheet 名，如 0624飞涨卡资源位&触达配置")
    parser.add_argument("--contact-person", default="", help="对接人；不填则使用配置中的默认对接人")
    parser.add_argument("--operator-root-folder-token", default="")
    parser.add_argument("--operator-root-folder-url", default="")
    parser.add_argument("--confirmed", action="store_true", help="实际写入大文档；不加时只 dry-run")
    parser.add_argument("--lark-cli", default="")
    parser.add_argument("--identity", choices=["user", "bot"], default="user")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--no-output-files", action="store_true")
    return parser


def extract_sheet_id_from_url(url: str) -> str:
    """Parse ?sheet=xxxxx from a Feishu sheets URL."""
    match = re.search(r"[?&]sheet=([^&?#]+)", url)
    return match.group(1) if match else ""


def choose_master_sheet(cli: LarkCli, master_url: str, master_sheet_name: str) -> tuple[str, str]:
    """Resolve master token and sheet_id."""
    token = extract_sheet_token(master_url)
    url_sheet_id = extract_sheet_id_from_url(master_url)

    if url_sheet_id and not master_sheet_name:
        # Use sheet_id from URL directly when no name specified
        return token, url_sheet_id

    info = workbook_info(cli, token=token)
    sheets = sheet_records(info)
    if not sheets:
        raise NongfuError("大文档没有可读取的 sheet。")
    if master_sheet_name:
        selected = next(
            (s for s in sheets if (s.get("sheet_name") or s.get("title") or s.get("name")) == master_sheet_name),
            None,
        )
        if not selected:
            raise NongfuError(f"大文档中没有 sheet: {master_sheet_name}")
    elif len(sheets) == 1:
        selected = sheets[0]
    else:
        names = [str(s.get("sheet_name") or s.get("title") or s.get("name") or "") for s in sheets]
        raise NongfuError("大文档有多个 sheet，请用 --master-sheet 指定: " + "、".join(names))
    sheet_id = str(selected.get("sheet_id") or selected.get("id") or selected.get("reference_id") or "")
    return token, sheet_id


def default_output_path(topic: str, stamp: str) -> Path:
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", topic).strip("_") or "sync"
    return PROJECT_ROOT / "workspace" / "12农夫协作" / "输出" / f"{stamp}_{safe}_sync_summary.json"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    operator_doc = configured_value_map(config, ["lx_nongfu", "operator_doc"])

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

    target_table_template = str(operator_doc.get("target_table_name_template") or "{operator}-日常信息")
    operator_folder_template = str(operator_doc.get("operator_folder_name_template") or "{operator}-运营主体")

    cli = LarkCli(resolve_lark_cli(config, args.lark_cli), identity=args.identity, timeout=args.timeout)

    # 1. Resolve master sheet
    master_token, master_sheet_id = choose_master_sheet(cli, args.master_url, args.master_sheet)

    # 2. Read master index: (brand, city) -> row number
    print("读取大文档品牌城市索引...", file=sys.stderr)
    master_index = read_master_index(cli, master_token, master_sheet_id)
    print(f"  大文档有效行数: {len(master_index)}", file=sys.stderr)

    # 3. Read master existing IDs for all matched rows
    print("读取大文档已有 ID...", file=sys.stderr)
    master_existing = read_master_existing_ids(cli, master_token, master_sheet_id, master_index)

    # 4. Auto-discover operator targets from root folder
    print("扫描运营主体日常信息表...", file=sys.stderr)
    targets = discover_operator_targets(
        cli,
        root_folder_token,
        operator_folder_template,
        target_table_template,
    )
    print(f"  发现 {len(targets)} 个运营主体日常信息表", file=sys.stderr)

    # 5. Load snapshot
    snap_path = snapshot_file(contact_person, args.topic_sheet_name)
    snapshot = load_snapshot(snap_path)
    print(f"快照: {'已有记录' if snapshot.get('operators') else '新建'} ({snap_path})", file=sys.stderr)

    # 6. Read current operator sheet IDs and diff
    all_changes: list[SyncChange] = []
    no_id_operators: dict[str, list[str]] = {}
    operators_processed = 0
    new_snapshot = snapshot.copy()
    new_snapshot["contact_person"] = contact_person
    new_snapshot["topic_sheet_name"] = args.topic_sheet_name
    new_snapshot["master_url"] = args.master_url
    new_snapshot["master_sheet_id"] = master_sheet_id

    timestamp = datetime.now().isoformat(timespec="seconds")

    for operator_name, target in sorted(targets.items()):
        sheet_id = target.existing_sheets.get(args.topic_sheet_name, "")
        if not sheet_id:
            # Check if the sheet was just published with a slightly different name
            # Try to find any sheet containing the topic name
            for existing_name, existing_id in target.existing_sheets.items():
                if args.topic_sheet_name in existing_name:
                    sheet_id = existing_id
                    break
        if not sheet_id:
            print(f"  [{operator_name}] 无 {args.topic_sheet_name} sheet，跳过", file=sys.stderr)
            continue

        print(f"  读取 [{operator_name}] {args.topic_sheet_name}...", file=sys.stderr)
        operators_processed += 1

        try:
            current_ids, layout = read_operator_ids(cli, target, sheet_id, operator_name)
        except Exception as exc:
            print(f"  [{operator_name}] 读取失败: {exc}", file=sys.stderr)
            continue

        # Check if any IDs are filled
        filled_count = sum(
            1 for ids in current_ids.values() if any(ids.get(f, "") for f in ["banner", "henglan", "kaiping", "sidebar"])
        )
        total_count = len(current_ids)
        print(f"    {filled_count}/{total_count} 行已填 ID，布局{'A' if layout == 'A' else 'B'}", file=sys.stderr)

        # Collect unfilled brand/city pairs
        unfilled = [
            f"{brand}/{city}"
            for (brand, city), ids in current_ids.items()
            if not any(ids.get(f, "") for f in ["banner", "henglan", "kaiping", "sidebar"])
        ]
        if unfilled:
            no_id_operators[operator_name] = unfilled

        # Diff against snapshot
        prev_op = snapshot.get("operators", {}).get(operator_name, {})
        op_changes = diff(current_ids, prev_op, master_index, master_existing, operator_name)
        all_changes.extend(op_changes)

        # Merge into new snapshot
        new_snapshot = merge_snapshot(
            new_snapshot, operator_name, target.spreadsheet_token, sheet_id, current_ids, master_index, timestamp
        )

    print(f"\n处理 {operators_processed} 个运营主体", file=sys.stderr)
    print(f"检出 {len(all_changes)} 个新增 ID", file=sys.stderr)

    # 7. Preview / write
    report = report_text(all_changes, no_id_operators)
    print(report)

    if args.confirmed and all_changes:
        print(f"\n写入 {len(all_changes)} 个单元格到飞书大文档...", file=sys.stderr)
        results = write_changes(cli, master_token, master_sheet_id, all_changes)
        ok_count = sum(1 for r in results if r.get("ok"))
        fail_count = sum(1 for r in results if not r.get("ok"))
        print(f"写入完成: {ok_count} 成功, {fail_count} 失败", file=sys.stderr)

        if fail_count:
            for r in results:
                if not r.get("ok"):
                    print(f"  失败: {r['cell']} = {r['value']}", file=sys.stderr)

        # Save updated snapshot
        save_snapshot(snap_path, new_snapshot)
        print(f"快照已更新: {snap_path}", file=sys.stderr)
    elif not args.confirmed and all_changes:
        print(f"\n[DRY-RUN] 未实际写入。使用 --confirmed 执行写入。", file=sys.stderr)
    elif not all_changes:
        print(f"\n无需更新：所有已填 ID 均已同步。", file=sys.stderr)

    # 8. Output JSON
    result: dict[str, Any] = {
        "ok": True,
        "dry_run": not args.confirmed,
        "contact_person": contact_person,
        "topic_sheet_name": args.topic_sheet_name,
        "master_url": args.master_url,
        "operators_processed": operators_processed,
        "changes": [
            {
                "operator": ch.operator,
                "brand": ch.brand,
                "city": ch.city,
                "field": ch.field,
                "cell": ch.cell,
                "old_value": ch.old_value,
                "new_value": ch.new_value,
            }
            for ch in all_changes
        ],
        "no_id_operators": {op: items for op, items in no_id_operators.items()},
        "wrote": args.confirmed and bool(all_changes),
        "snapshot_path": str(snap_path),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not args.no_output_files:
        json_path = Path(args.output_json).expanduser() if args.output_json else default_output_path(args.topic_sheet_name, stamp)
        if not json_path.is_absolute():
            json_path = PROJECT_ROOT / json_path
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n摘要: {json_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NongfuError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
