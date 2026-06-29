#!/usr/bin/env python3
"""
从公司 dataReporting 库按 date_day + city_name + brand_name 导出 hhdata B补相关金额。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


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

from lx_shujuku import create_client  # noqa: E402


Q2 = Decimal("0.01")


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
        "## 来源汇总",
        "",
        "| 日期 | 总b补金额 | 商家b补金额 | 售卡商家收入金额 |",
        "|---|---:|---:|---:|",
    ]
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
    parser = argparse.ArgumentParser(description="按 date + city_name + brand_name 导出 hhdata B补来源金额")
    parser.add_argument("--start-date", required=True, type=parse_date, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, type=parse_date, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--source-limit", type=int, default=1000, help="公司库单日聚合查询 LIMIT，默认 1000")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "workspace" / "02数据导入" / "处理日志" / "lx-hhbbu"),
        help="审计文件输出目录",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dates = iter_dates(args.start_date, args.end_date)
    source, source_meta = fetch_source(dates, args.source_limit)
    rows = build_rows(source)
    source_summary = summarize_by_date(source, dates)
    report = {
        "type": "lx-hhbbu.source_export",
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "args": {
            "start_date": dates[0],
            "end_date": dates[-1],
            "source_limit": args.source_limit,
        },
        "date_range": {"start": dates[0], "end": dates[-1], "days": len(dates)},
        "key": ["date", "city_name", "brand_name"],
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
    print(f"CSV: {csv_path}")
    print(f"审计 JSON: {json_path}")
    print(f"审计 Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
