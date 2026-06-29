#!/usr/bin/env python3
"""Refresh hhdata daily brand-city aggregate table."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from typing import Any

import pandas as pd
import run_weekly_report as report
from refresh_weekly_agg import ensure_schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="刷新 hhdata 日粒度品牌城市聚合表")
    parser.add_argument("--start", type=report.parse_date, required=True, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=report.parse_date, required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="覆盖日期范围内已有聚合数据")
    parser.add_argument("--dry-run", action="store_true", help="只计算行数，不写数据库")
    return parser.parse_args()


def load_daily_source(db: report.DatabaseConnector, start, end) -> pd.DataFrame:
    field_sql = ",\n            ".join(f"SUM(f.{field}) AS {field}" for field in report.SUM_FIELDS)
    sql = f"""
        SELECT
            f.date_day AS metric_date,
            b.brand_name,
            c.city_name,
            COUNT(*) AS source_row_count,
            {field_sql}
        FROM hhdata__fact_daily_metrics f
        JOIN mabiao__dim_cities c ON f.city_id = c.city_id
        JOIN mabiao__dim_brands b ON f.brand_id = b.brand_id
        WHERE f.date_day >= %s AND f.date_day <= %s
        GROUP BY f.date_day, b.brand_name, c.city_name
        ORDER BY f.date_day, b.brand_name, c.city_name
    """
    df = db.execute(sql, [start.isoformat(), end.isoformat()])
    if df.empty:
        return df
    df = df.copy()
    df["metric_date"] = df["metric_date"].map(lambda value: datetime.strptime(report.fmt_date(value), "%Y-%m-%d").date())
    df["brand_name"] = df["brand_name"].map(report.clean_text)
    df["city_name"] = df["city_name"].map(report.clean_text)
    df["source_row_count"] = pd.to_numeric(df["source_row_count"], errors="coerce").fillna(0).astype(int)
    for field in report.SUM_FIELDS:
        df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0)
    return df


def existing_count(db: report.DatabaseConnector, start, end) -> int:
    if not report.table_exists(db, report.DAILY_BRAND_CITY_METRICS_TABLE):
        return 0
    value = db.execute_scalar(
        f"""
        SELECT COUNT(*)
        FROM {report.DAILY_BRAND_CITY_METRICS_TABLE}
        WHERE metric_date >= %s AND metric_date <= %s
        """,
        [start.isoformat(), end.isoformat()],
    )
    return int(value or 0)


def brand_city_hash(brand: str, city: str) -> str:
    return hashlib.sha256(f"{brand}\x1f{city}".encode("utf-8")).hexdigest()


def insert_sql() -> str:
    columns = [
        "metric_date",
        "brand_name",
        "city_name",
        "source_row_count",
        "brand_city_key_hash",
        *report.SUM_FIELDS,
        "refresh_run_id",
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {report.DAILY_BRAND_CITY_METRICS_TABLE} ({', '.join(columns)}) VALUES ({placeholders})"


def row_values(row: pd.Series, run_id: str) -> tuple[Any, ...]:
    brand = report.clean_text(row["brand_name"])
    city = report.clean_text(row["city_name"])
    return (
        row["metric_date"].isoformat(),
        brand,
        city,
        int(row["source_row_count"] or 0),
        brand_city_hash(brand, city),
        *(float(row[field] or 0) for field in report.SUM_FIELDS),
        run_id,
    )


def refresh(args: argparse.Namespace) -> dict[str, Any]:
    if args.end < args.start:
        raise ValueError("--end 不能早于 --start")
    db = report.DatabaseConnector()
    if not args.dry_run:
        ensure_schema(db)
    existing = existing_count(db, args.start, args.end)
    if existing and not args.force and not args.dry_run:
        raise RuntimeError(f"{args.start.isoformat()} 到 {args.end.isoformat()} 已有 {existing} 条日聚合数据；如需重刷请加 --force")

    df = load_daily_source(db, args.start, args.end)
    run_id = f"daily-brand-city-{args.start:%Y%m%d}-{args.end:%Y%m%d}-{datetime.now():%Y%m%d%H%M%S%f}"
    summary = {
        "run_id": run_id,
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "day_count": (args.end - args.start).days + 1,
        "dry_run": args.dry_run,
        "force": args.force,
        "existing_rows": existing,
        "agg_row_count": int(len(df)),
        "date_count": int(df["metric_date"].nunique()) if not df.empty else 0,
    }
    if args.dry_run:
        return summary

    payload = [row_values(row, run_id) for _, row in df.iterrows()]
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            DELETE FROM {report.DAILY_BRAND_CITY_METRICS_TABLE}
            WHERE metric_date >= %s AND metric_date <= %s
            """,
            [args.start.isoformat(), args.end.isoformat()],
        )
        if payload:
            cursor.executemany(insert_sql(), payload)
        conn.commit()
    return summary


def main() -> int:
    args = parse_args()
    try:
        summary = refresh(args)
    except Exception as exc:
        print(f"❌ 日聚合刷新失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
