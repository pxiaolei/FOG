#!/usr/bin/env python3
"""
从公司 dataReporting 库按 date_day + city_name + brand_name 导出 hhdata B补相关金额。
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


def _find_project_root() -> Path:
    for candidate in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
        if (candidate / ".workbuddy" / "skills").is_dir() and (candidate / "config").is_dir():
            return candidate
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _find_project_root()
SKILLS_DIR = PROJECT_ROOT / ".workbuddy" / "skills"
LX_SHUJUKU_SCRIPTS_DIR = SKILLS_DIR / "lx_shujuku" / "scripts"

for path in (SKILLS_DIR, LX_SHUJUKU_SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lxx_share.fog_config import get_section, resolve_project_path  # noqa: E402
from lx_shujuku import create_client  # noqa: E402


Q2 = Decimal("0.01")
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
WRITABLE_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "workspace" / "02数据导入" / "处理日志" / "lx-hhbbu"
DEFAULT_HHDATA_DIR = PROJECT_ROOT / "workspace" / "02数据导入" / "待处理" / "hhdata"
TARGET_COLUMN_ALIASES = {
    "date": ("日期",),
    "city_name": ("城市名称", "城市"),
    "brand_name": ("品牌名称", "品牌"),
    "total_b_subsidy": ("总b补金额", "总B补金额"),
    "merchant_b_subsidy": ("商家b补金额", "商家B补金额"),
    "card_merchant_income": ("售卡商家收入金额", "售卡商家收入"),
}
UPDATE_FIELDS = {
    "total_b_subsidy": "总b补金额",
    "merchant_b_subsidy": "商家b补金额",
    "card_merchant_income": "售卡商家收入金额",
}


@dataclass(frozen=True)
class LocalHhdataInfo:
    status: str
    source: str
    path: str
    message: str
    selected_file: str = ""
    candidate_count: int = 0
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Key:
    date_day: str
    city_name: str
    brand_name: str


@dataclass
class SourceAmounts:
    activity_total_reward: Decimal = Decimal("0")
    activity_merchant_subsidy: Decimal = Decimal("0")
    coupon_total_subsidy: Decimal = Decimal("0")
    coupon_merchant_subsidy: Decimal = Decimal("0")
    merchant_coupon_sales_revenue: Decimal = Decimal("0")

    @property
    def total_b_subsidy(self) -> Decimal:
        return money(self.activity_total_reward + self.coupon_total_subsidy)

    @property
    def merchant_b_subsidy(self) -> Decimal:
        return money(self.activity_merchant_subsidy + self.coupon_merchant_subsidy)

    @property
    def card_merchant_income(self) -> Decimal:
        return money(self.merchant_coupon_sales_revenue)

    @property
    def has_nonzero_target_amount(self) -> bool:
        return any(
            value != 0
            for value in (
                self.total_b_subsidy,
                self.merchant_b_subsidy,
                self.card_merchant_income,
            )
        )


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日期格式必须是 YYYY-MM-DD: {value}") from exc


def iter_dates(start: date, end: date) -> list[str]:
    if start > end:
        raise ValueError("--start-date 不能晚于 --end-date")
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    return to_decimal(value).quantize(Q2, rounding=ROUND_HALF_UP)


def fmt_money(value: Any) -> str:
    return f"{money(value):.2f}"


def normalize_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = normalize_text(value)
    if not text:
        return ""
    text = text.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def load_hhbbu_config() -> dict[str, Any]:
    return get_section("lx_hhbbu", PROJECT_ROOT)


def resolve_runtime_path(value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return resolve_project_path(path, PROJECT_ROOT)


def is_excel_candidate(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in EXCEL_SUFFIXES and not path.name.startswith("~$")


def list_excel_candidates(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    candidates = [path for path in directory.iterdir() if is_excel_candidate(path)]
    return sorted(candidates, key=lambda path: (-path.stat().st_mtime, path.name))


def inspect_local_hhdata(
    *,
    hhdata_file: str | None,
    hhdata_dir: str | None,
    require_local_hhdata: bool,
    config: dict[str, Any],
) -> LocalHhdataInfo:
    local_config = config.get("local_hhdata", {}) if isinstance(config.get("local_hhdata", {}), dict) else {}
    config_requires = bool(local_config.get("required_before_run"))
    required = require_local_hhdata or config_requires

    location_value: str | Path | None
    location_type: str
    source: str
    explicit = False
    if hhdata_file:
        location_value = hhdata_file
        location_type = "file"
        source = "--hhdata-file"
        explicit = True
    elif hhdata_dir:
        location_value = hhdata_dir
        location_type = "dir"
        source = "--hhdata-dir"
        explicit = True
    elif local_config.get("file"):
        location_value = local_config.get("file")
        location_type = "file"
        source = "fog_config.yaml:lx_hhbbu.local_hhdata.file"
    elif local_config.get("input_dir"):
        location_value = local_config.get("input_dir")
        location_type = "dir"
        source = "fog_config.yaml:lx_hhbbu.local_hhdata.input_dir"
    else:
        location_value = DEFAULT_HHDATA_DIR
        location_type = "dir"
        source = "default"

    path = resolve_runtime_path(location_value)
    failure_status = "error" if required or explicit else "warning"

    if location_type == "file":
        if is_excel_candidate(path):
            return LocalHhdataInfo(
                status="ok",
                source=source,
                path=str(path),
                message=f"已定位本地 hhdata Excel: {path}",
                selected_file=str(path),
                candidate_count=1,
                candidates=(str(path),),
            )
        return LocalHhdataInfo(
            status=failure_status,
            source=source,
            path=str(path),
            message=f"未找到可用本地 hhdata Excel: {path}",
        )

    if not path.is_dir():
        return LocalHhdataInfo(
            status=failure_status,
            source=source,
            path=str(path),
            message=f"本地 hhdata 目录不存在: {path}",
        )

    candidates = list_excel_candidates(path)
    if not candidates:
        return LocalHhdataInfo(
            status=failure_status,
            source=source,
            path=str(path),
            message=f"本地 hhdata 目录存在，但没有 Excel 候选文件: {path}",
        )

    shown = tuple(str(candidate) for candidate in candidates[:20])
    if len(candidates) == 1:
        message = f"已定位 1 个本地 hhdata Excel: {candidates[0]}"
        selected_file = str(candidates[0])
    else:
        message = f"已定位 {len(candidates)} 个本地 hhdata Excel 候选；写回前必须用 --hhdata-file 或配置 file 固定某个文件"
        selected_file = ""
    return LocalHhdataInfo(
        status="ok",
        source=source,
        path=str(path),
        message=message,
        selected_file=selected_file,
        candidate_count=len(candidates),
        candidates=shown,
    )


def local_hhdata_to_dict(info: LocalHhdataInfo) -> dict[str, Any]:
    return {
        "status": info.status,
        "source": info.source,
        "path": info.path,
        "message": info.message,
        "selected_file": info.selected_file,
        "candidate_count": info.candidate_count,
        "candidates": list(info.candidates),
    }


def print_local_hhdata_info(info: LocalHhdataInfo) -> None:
    prefix = {"ok": "[ok]", "warning": "[warning]", "error": "[error]"}.get(info.status, "[info]")
    print(f"{prefix} 本地 hhdata 定位: {info.message}")
    print(f"来源: {info.source}")
    if info.selected_file:
        print(f"写回文件: {info.selected_file}")
    if info.candidates:
        print("候选文件:")
        for candidate in info.candidates:
            print(f"- {candidate}")


def find_header(headers: dict[str, int], field: str) -> int | None:
    for alias in TARGET_COLUMN_ALIASES[field]:
        if alias in headers:
            return headers[alias]
    return None


def detect_hhdata_sheet(workbook: Any, sheet_name: str = "") -> tuple[Any, int, dict[str, int]]:
    sheets = [workbook[sheet_name]] if sheet_name else [workbook[name] for name in workbook.sheetnames]
    for ws in sheets:
        if ws.sheet_state != "visible":
            continue
        for row_idx in range(1, min(ws.max_row, 10) + 1):
            headers = {
                normalize_text(ws.cell(row=row_idx, column=col_idx).value): col_idx
                for col_idx in range(1, ws.max_column + 1)
                if normalize_text(ws.cell(row=row_idx, column=col_idx).value)
            }
            resolved = {field: find_header(headers, field) for field in TARGET_COLUMN_ALIASES}
            if all(resolved.values()):
                return ws, row_idx, {field: int(col_idx) for field, col_idx in resolved.items() if col_idx}
    target = f"工作表 {sheet_name!r}" if sheet_name else "任一可见工作表"
    raise RuntimeError(f"未在{target}找到 hhdata 表头：需要日期、城市名称、品牌名称、总b补金额、商家b补金额、售卡商家收入金额")


def source_update_values(amounts: SourceAmounts) -> dict[str, Decimal]:
    return {
        "total_b_subsidy": amounts.total_b_subsidy,
        "merchant_b_subsidy": amounts.merchant_b_subsidy,
        "card_merchant_income": amounts.card_merchant_income,
    }


def make_backup(file_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{file_path.stem}.before_lx-hhbbu_{timestamp}{file_path.suffix}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def build_hhdata_update(
    *,
    source: dict[Key, SourceAmounts],
    local_hhdata: LocalHhdataInfo,
    output_dir: Path,
    sheet_name: str = "",
    backup_dir: str = "",
    confirmed: bool = False,
) -> dict[str, Any]:
    if not local_hhdata.selected_file:
        return {
            "status": "error",
            "message": "未能唯一定位要写回的 hhdata Excel；请用 --hhdata-file 或 lx_hhbbu.local_hhdata.file 指定单个文件",
            "confirmed": confirmed,
        }

    file_path = Path(local_hhdata.selected_file)
    if file_path.suffix.lower() not in WRITABLE_EXCEL_SUFFIXES:
        return {
            "status": "error",
            "message": f"当前只支持写回 .xlsx/.xlsm 文件，不支持: {file_path}",
            "confirmed": confirmed,
        }

    workbook = load_workbook(file_path)
    try:
        ws, header_row, columns = detect_hhdata_sheet(workbook, sheet_name)
        rows_by_key: dict[Key, list[int]] = defaultdict(list)
        row_meta: dict[int, Key] = {}
        for row_idx in range(header_row + 1, ws.max_row + 1):
            date_day = normalize_date(ws.cell(row=row_idx, column=columns["date"]).value)
            city_name = normalize_text(ws.cell(row=row_idx, column=columns["city_name"]).value)
            brand_name = normalize_text(ws.cell(row=row_idx, column=columns["brand_name"]).value)
            if not date_day or not city_name or not brand_name:
                continue
            key = Key(date_day, city_name, brand_name)
            rows_by_key[key].append(row_idx)
            row_meta[row_idx] = key

        duplicate_keys = {key for key, row_indexes in rows_by_key.items() if len(row_indexes) > 1}
        source_keys = {key for key, amounts in source.items() if amounts.has_nonzero_target_amount}
        changed_rows: set[int] = set()
        unchanged_rows = 0
        missing_source_rows = []
        skipped_duplicate_rows = []
        changes = []

        for row_idx, key in sorted(row_meta.items()):
            if key in duplicate_keys:
                skipped_duplicate_rows.append({
                    "row": row_idx,
                    "date": key.date_day,
                    "city_name": key.city_name,
                    "brand_name": key.brand_name,
                    "reason": "本地 Excel 存在重复 date+city_name+brand_name，跳过避免重复写入",
                })
                continue
            amounts = source.get(key)
            if amounts is None or not amounts.has_nonzero_target_amount:
                missing_source_rows.append({
                    "row": row_idx,
                    "date": key.date_day,
                    "city_name": key.city_name,
                    "brand_name": key.brand_name,
                })
                continue

            row_changed = False
            for field, display_name in UPDATE_FIELDS.items():
                col_idx = columns[field]
                cell = ws.cell(row=row_idx, column=col_idx)
                old_value = money(cell.value)
                new_value = source_update_values(amounts)[field]
                if old_value == new_value:
                    continue
                row_changed = True
                changed_rows.add(row_idx)
                changes.append({
                    "row": row_idx,
                    "date": key.date_day,
                    "city_name": key.city_name,
                    "brand_name": key.brand_name,
                    "field": field,
                    "column": display_name,
                    "old_value": fmt_money(old_value),
                    "new_value": fmt_money(new_value),
                })
                if confirmed:
                    cell.value = float(new_value)
                    cell.number_format = "0.00"
            if not row_changed:
                unchanged_rows += 1

        local_unique_keys = {key for key, row_indexes in rows_by_key.items() if len(row_indexes) == 1}
        source_not_in_local = sorted(source_keys - local_unique_keys, key=lambda key: (key.date_day, key.city_name, key.brand_name))
        backup_path = ""
        if confirmed and changes:
            backup_root = resolve_runtime_path(backup_dir) if backup_dir else output_dir / "backups"
            backup_path = str(make_backup(file_path, backup_root))
            workbook.save(file_path)

        mode = "confirmed" if confirmed else "dry_run"
        status = "updated" if confirmed and changes else "no_changes" if not changes else "dry_run"
        return {
            "status": status,
            "mode": mode,
            "confirmed": confirmed,
            "message": "已写回本地 hhdata Excel" if confirmed and changes else "未保存 Excel；这是 dry-run 更新计划" if changes else "没有需要写回的单元格",
            "file": str(file_path),
            "sheet": ws.title,
            "header_row": header_row,
            "backup_path": backup_path,
            "local_key_count": len(rows_by_key),
            "duplicate_local_key_count": len(duplicate_keys),
            "skipped_duplicate_row_count": len(skipped_duplicate_rows),
            "missing_source_row_count": len(missing_source_rows),
            "source_not_in_local_count": len(source_not_in_local),
            "changed_row_count": len(changed_rows),
            "changed_cell_count": len(changes),
            "unchanged_matched_row_count": unchanged_rows,
            "changes_sample": changes[:200],
            "skipped_duplicate_rows_sample": skipped_duplicate_rows[:50],
            "missing_source_rows_sample": missing_source_rows[:50],
            "source_not_in_local_sample": [
                {"date": key.date_day, "city_name": key.city_name, "brand_name": key.brand_name}
                for key in source_not_in_local[:50]
            ],
        }
    finally:
        workbook.close()


def fetch_source(dates: list[str], source_limit: int) -> tuple[dict[Key, SourceAmounts], dict[str, Any]]:
    client = create_client()
    source: dict[Key, SourceAmounts] = defaultdict(SourceAmounts)
    source_counts: dict[str, dict[str, int]] = {}

    for date_day in dates:
        activity_sql = f"""
            SELECT date_day, city_name, brand_name,
                   SUM(COALESCE(total_reward_amount, 0)) AS activity_total_reward,
                   SUM(COALESCE(merchant_subsidy_amount, 0)) AS activity_merchant_subsidy
            FROM honghu_activity_marketing_data
            WHERE date_day = '{date_day}'
            GROUP BY date_day, city_name, brand_name
            LIMIT {source_limit}
        """
        coupon_sql = f"""
            SELECT date_day, city_name, brand_name,
                   SUM(COALESCE(total_subsidy_amount, 0)) AS coupon_total_subsidy,
                   SUM(COALESCE(merchant_subsidy_amount, 0)) AS coupon_merchant_subsidy,
                   SUM(COALESCE(merchant_coupon_sales_revenue, 0)) AS merchant_coupon_sales_revenue
            FROM honghu_coupon_marketing_data
            WHERE date_day = '{date_day}'
            GROUP BY date_day, city_name, brand_name
            LIMIT {source_limit}
        """
        activity_rows = client.execute(activity_sql)
        coupon_rows = client.execute(coupon_sql)
        if len(activity_rows) >= source_limit or len(coupon_rows) >= source_limit:
            raise RuntimeError(
                f"{date_day} 公司库聚合结果达到 source_limit={source_limit}，可能被截断；"
                "请提高 lx_shujuku max_limit 或缩小日期范围后重试。"
            )

        source_counts[date_day] = {
            "activity_groups": len(activity_rows),
            "coupon_groups": len(coupon_rows),
        }

        for row in activity_rows:
            key = Key(row["date_day"], row.get("city_name") or "", row.get("brand_name") or "")
            source[key].activity_total_reward += to_decimal(row.get("activity_total_reward"))
            source[key].activity_merchant_subsidy += to_decimal(row.get("activity_merchant_subsidy"))

        for row in coupon_rows:
            key = Key(row["date_day"], row.get("city_name") or "", row.get("brand_name") or "")
            source[key].coupon_total_subsidy += to_decimal(row.get("coupon_total_subsidy"))
            source[key].coupon_merchant_subsidy += to_decimal(row.get("coupon_merchant_subsidy"))
            source[key].merchant_coupon_sales_revenue += to_decimal(row.get("merchant_coupon_sales_revenue"))

    return source, {"group_counts": source_counts}


def build_rows(source: dict[Key, SourceAmounts]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, amounts in sorted(source.items(), key=lambda item: (item[0].date_day, item[0].city_name, item[0].brand_name)):
        if not amounts.has_nonzero_target_amount:
            continue
        rows.append({
            "date": key.date_day,
            "city_name": key.city_name,
            "brand_name": key.brand_name,
            "total_b_subsidy": fmt_money(amounts.total_b_subsidy),
            "merchant_b_subsidy": fmt_money(amounts.merchant_b_subsidy),
            "card_merchant_income": fmt_money(amounts.card_merchant_income),
            "activity_total_reward": fmt_money(amounts.activity_total_reward),
            "activity_merchant_subsidy": fmt_money(amounts.activity_merchant_subsidy),
            "coupon_total_subsidy": fmt_money(amounts.coupon_total_subsidy),
            "coupon_merchant_subsidy": fmt_money(amounts.coupon_merchant_subsidy),
            "merchant_coupon_sales_revenue": fmt_money(amounts.merchant_coupon_sales_revenue),
        })
    return rows


def summarize_by_date(source: dict[Key, SourceAmounts], dates: list[str]) -> dict[str, dict[str, str]]:
    summary: dict[str, dict[str, Decimal]] = {
        day: {
            "total_b_subsidy": Decimal("0"),
            "merchant_b_subsidy": Decimal("0"),
            "card_merchant_income": Decimal("0"),
        }
        for day in dates
    }
    for key, amounts in source.items():
        if key.date_day not in summary:
            continue
        summary[key.date_day]["total_b_subsidy"] += amounts.total_b_subsidy
        summary[key.date_day]["merchant_b_subsidy"] += amounts.merchant_b_subsidy
        summary[key.date_day]["card_merchant_income"] += amounts.card_merchant_income
    return {
        day: {metric: fmt_money(value) for metric, value in values.items()}
        for day, values in summary.items()
    }


def write_outputs(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"{timestamp}_lx-hhbbu_source.csv"
    json_path = output_dir / f"{timestamp}_lx-hhbbu_source.json"
    md_path = output_dir / f"{timestamp}_lx-hhbbu_source.md"

    fieldnames = [
        "date",
        "city_name",
        "brand_name",
        "total_b_subsidy",
        "merchant_b_subsidy",
        "card_merchant_income",
        "activity_total_reward",
        "activity_merchant_subsidy",
        "coupon_total_subsidy",
        "coupon_merchant_subsidy",
        "merchant_coupon_sales_revenue",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report["rows"])

    report["outputs"] = {
        "csv": str(csv_path),
        "json": str(json_path),
        "markdown": str(md_path),
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return csv_path, json_path, md_path


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# lx-hhbbu 公司库来源导出",
        "",
        f"- 聚合键: `date + city_name + brand_name`",
        f"- 日期范围: {report['date_range']['start']} 至 {report['date_range']['end']}",
        f"- 输出行数: {report['row_count']}",
        f"- CSV: `{report['outputs']['csv']}`",
        "",
        "## 本地 hhdata 定位",
        "",
        f"- 状态: `{report['local_hhdata']['status']}`",
        f"- 来源: `{report['local_hhdata']['source']}`",
        f"- 路径: `{report['local_hhdata']['path']}`",
        f"- 说明: {report['local_hhdata']['message']}",
        "",
    ]
    if report.get("workbook_update"):
        update = report["workbook_update"]
        lines.extend([
            "## 本地 hhdata Excel 写回",
            "",
            f"- 状态: `{update['status']}`",
            f"- 模式: `{update['mode']}`",
            f"- 文件: `{update.get('file', '')}`",
            f"- 工作表: `{update.get('sheet', '')}`",
            f"- 变更行数: {update.get('changed_row_count', 0)}",
            f"- 变更单元格数: {update.get('changed_cell_count', 0)}",
            f"- 跳过重复 key 行数: {update.get('skipped_duplicate_row_count', 0)}",
            f"- 本地无公司源行数: {update.get('missing_source_row_count', 0)}",
            f"- 公司源未命中本地 key 数: {update.get('source_not_in_local_count', 0)}",
            f"- 备份: `{update.get('backup_path', '')}`",
            f"- 说明: {update.get('message', '')}",
            "",
        ])
    lines.extend([
        "## 来源汇总",
        "",
        "| 日期 | 总b补金额 | 商家b补金额 | 售卡商家收入金额 |",
        "|---|---:|---:|---:|",
    ])
    for day, values in report["source_summary"].items():
        lines.append(
            f"| {day} | {values['total_b_subsidy']} | "
            f"{values['merchant_b_subsidy']} | {values['card_merchant_income']} |"
        )
    lines.extend([
        "",
        "## 字段说明",
        "",
        "- `date`、`city_name`、`brand_name`：公司库聚合键。",
        "- `total_b_subsidy`：活动总奖励金额 + 卡券总补贴金额。",
        "- `merchant_b_subsidy`：活动商家补贴金额 + 卡券商家补贴金额。",
        "- `card_merchant_income`：卡券商家券后售卡收入。",
        "- 其余 `activity_*` / `coupon_*` 字段是来源拆分金额。",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    config = load_hhbbu_config()
    source_limit = int(config.get("source_limit") or 1000)
    parser = argparse.ArgumentParser(description="按 date + city_name + brand_name 导出 hhdata B补来源金额")
    parser.add_argument("--start-date", type=parse_date, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=parse_date, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--source-limit", type=int, default=source_limit, help="公司库单日聚合查询 LIMIT，默认 1000")
    parser.add_argument("--hhdata-file", help="本地 hhdata Excel 文件路径；优先于 fog_config.yaml")
    parser.add_argument("--hhdata-dir", help="本地 hhdata Excel 目录；优先于 fog_config.yaml")
    parser.add_argument("--require-local-hhdata", action="store_true", help="找不到本地 hhdata Excel 时失败")
    parser.add_argument("--check-local-hhdata", action="store_true", help="只检查本地 hhdata 位置，不查询公司库")
    parser.add_argument("--update-hhdata", action="store_true", help="按公司源生成本地 hhdata Excel 三列写回计划；默认不保存")
    parser.add_argument("--confirmed", action="store_true", help="确认保存本地 hhdata Excel；必须和 --update-hhdata 一起使用")
    parser.add_argument("--hhdata-sheet", help="本地 hhdata 工作表名称；默认自动检测")
    parser.add_argument("--backup-dir", help="确认写回前的备份目录；默认写到输出目录 backups 子目录")
    parser.add_argument(
        "--output-dir",
        help="审计文件输出目录；默认读取 fog_config.yaml 的 lx_hhbbu.output_dir",
    )
    args = parser.parse_args()
    output_dir = args.output_dir or config.get("output_dir") or DEFAULT_OUTPUT_DIR
    args.output_dir = str(resolve_runtime_path(output_dir))
    args.hhbbu_config = config
    local_config = config.get("local_hhdata", {}) if isinstance(config.get("local_hhdata", {}), dict) else {}
    args.hhdata_sheet = args.hhdata_sheet or local_config.get("sheet_name") or ""
    args.backup_dir = args.backup_dir or local_config.get("backup_dir") or ""
    if args.confirmed and not args.update_hhdata:
        parser.error("--confirmed 必须和 --update-hhdata 一起使用")
    if not args.check_local_hhdata and (not args.start_date or not args.end_date):
        parser.error("导出公司源时必须同时提供 --start-date 和 --end-date；只检查本地 hhdata 位置可使用 --check-local-hhdata")
    return args


def main() -> int:
    args = parse_args()
    local_hhdata = inspect_local_hhdata(
        hhdata_file=args.hhdata_file,
        hhdata_dir=args.hhdata_dir,
        require_local_hhdata=args.require_local_hhdata or args.update_hhdata,
        config=args.hhbbu_config,
    )
    if args.check_local_hhdata:
        print_local_hhdata_info(local_hhdata)
        return 1 if local_hhdata.status == "error" else 0
    if local_hhdata.status == "error":
        print_local_hhdata_info(local_hhdata)
        return 1

    dates = iter_dates(args.start_date, args.end_date)
    source, source_meta = fetch_source(dates, args.source_limit)
    source_meta["local_hhdata"] = local_hhdata_to_dict(local_hhdata)
    rows = build_rows(source)
    source_summary = summarize_by_date(source, dates)
    workbook_update = None
    if args.update_hhdata:
        workbook_update = build_hhdata_update(
            source=source,
            local_hhdata=local_hhdata,
            output_dir=Path(args.output_dir),
            sheet_name=args.hhdata_sheet,
            backup_dir=args.backup_dir,
            confirmed=args.confirmed,
        )
        if workbook_update.get("status") == "error":
            print(f"[error] 本地 hhdata Excel 写回失败: {workbook_update.get('message', '')}")
            return 1
    report = {
        "type": "lx-hhbbu.source_export",
        "version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "args": {
            "start_date": dates[0],
            "end_date": dates[-1],
            "source_limit": args.source_limit,
            "output_dir": args.output_dir,
            "hhdata_file": args.hhdata_file,
            "hhdata_dir": args.hhdata_dir,
            "require_local_hhdata": args.require_local_hhdata,
            "update_hhdata": args.update_hhdata,
            "confirmed": args.confirmed,
            "hhdata_sheet": args.hhdata_sheet,
            "backup_dir": args.backup_dir,
        },
        "date_range": {"start": dates[0], "end": dates[-1], "days": len(dates)},
        "key": ["date", "city_name", "brand_name"],
        "local_hhdata": local_hhdata_to_dict(local_hhdata),
        "workbook_update": workbook_update,
        "source_meta": source_meta,
        "source_summary": source_summary,
        "row_count": len(rows),
        "rows": rows,
    }
    csv_path, json_path, md_path = write_outputs(report, Path(args.output_dir))

    print("lx-hhbbu 公司库来源导出")
    print("聚合键: date + city_name + brand_name")
    print(f"日期范围: {dates[0]} 至 {dates[-1]}")
    print(f"输出行数: {len(rows)}")
    print("来源汇总:")
    for day, values in source_summary.items():
        print(
            f"- {day}: 总b补={values['total_b_subsidy']} "
            f"商家b补={values['merchant_b_subsidy']} "
            f"售卡商家收入={values['card_merchant_income']}"
        )
    print_local_hhdata_info(local_hhdata)
    if workbook_update:
        print("本地 hhdata Excel 写回:")
        print(f"- 状态: {workbook_update['status']}")
        print(f"- 模式: {workbook_update['mode']}")
        print(f"- 变更行数: {workbook_update.get('changed_row_count', 0)}")
        print(f"- 变更单元格数: {workbook_update.get('changed_cell_count', 0)}")
        if workbook_update.get("backup_path"):
            print(f"- 备份: {workbook_update['backup_path']}")
        print(f"- 说明: {workbook_update.get('message', '')}")
    print(f"CSV: {csv_path}")
    print(f"审计 JSON: {json_path}")
    print(f"审计 Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
