#!/usr/bin/env python3
"""Refresh hhdata weekly aggregate tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import run_weekly_report as report


SCHEMA_PATH = Path(__file__).resolve().with_name("db_schema.sql")


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements


def ensure_schema(db: report.DatabaseConnector) -> None:
    statements = split_sql_statements(SCHEMA_PATH.read_text(encoding="utf-8"))
    with db.connect() as conn:
        cursor = conn.cursor()
        for statement in statements:
            cursor.execute(statement)
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND column_name = 'dimension_key_hash'
            """,
            [report.WEEKLY_METRICS_TABLE],
        )
        has_hash_column = bool(cursor.fetchone()[0])
        if not has_hash_column:
            cursor.execute(
                f"""
                ALTER TABLE {report.WEEKLY_METRICS_TABLE}
                ADD COLUMN dimension_key_hash CHAR(64) NOT NULL DEFAULT '' AFTER source_row_count
                """
            )
            cursor.execute(
                f"""
                UPDATE {report.WEEKLY_METRICS_TABLE}
                SET dimension_key_hash = SHA2(
                    CONCAT(dimension_code, CHAR(31), operator_name, CHAR(31), brand_name, CHAR(31), city_name),
                    256
                )
                WHERE dimension_key_hash = ''
                """
            )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND index_name = 'uk_hhdata_weekly_metrics_dim'
            """,
            [report.WEEKLY_METRICS_TABLE],
        )
        if cursor.fetchone()[0]:
            cursor.execute(f"ALTER TABLE {report.WEEKLY_METRICS_TABLE} DROP INDEX uk_hhdata_weekly_metrics_dim")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND index_name = 'uk_hhdata_weekly_metrics_dim_hash'
            """,
            [report.WEEKLY_METRICS_TABLE],
        )
        if not cursor.fetchone()[0]:
            cursor.execute(
                f"""
                ALTER TABLE {report.WEEKLY_METRICS_TABLE}
                ADD UNIQUE KEY uk_hhdata_weekly_metrics_dim_hash (week_start, dimension_key_hash)
                """
            )
        conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="刷新 hhdata 周聚合表")
    parser.add_argument("--week-start", type=report.parse_date, required=True, help="自然周周一日期 YYYY-MM-DD")
    parser.add_argument("--weeks", type=int, default=1, help="从 week-start 开始连续刷新 N 周")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的该周聚合数据")
    parser.add_argument("--dry-run", action="store_true", help="只计算行数和缺口，不写数据库")
    return parser.parse_args()


def validate_week_start(value) -> None:
    if value.weekday() != 0:
        raise ValueError(f"--week-start 必须是周一: {value.isoformat()}")


def dedupe_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for gap in gaps:
        key = json.dumps(gap, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(gap)
    return result


def existing_metric_count(db: report.DatabaseConnector, period: report.Period) -> int:
    if not report.table_exists(db, report.WEEKLY_METRICS_TABLE):
        return 0
    value = db.execute_scalar(
        f"SELECT COUNT(*) FROM {report.WEEKLY_METRICS_TABLE} WHERE week_start = %s AND week_end = %s",
        [period.start.isoformat(), period.end.isoformat()],
    )
    return int(value or 0)


def load_week_source(db: report.DatabaseConnector, period: report.Period):
    periods = report.Periods(previous=period, current=period)
    return report.load_hhdata(db, periods)


def metric_insert_sql() -> str:
    columns = [
        "week_start",
        "week_end",
        "day_count",
        "dimension_code",
        "dimension_name",
        "contact_person",
        "operator_name",
        "brand_name",
        "city_name",
        "mapping_status",
        "source_row_count",
        "dimension_key_hash",
        *report.SUM_FIELDS,
        "refresh_run_id",
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {report.WEEKLY_METRICS_TABLE} ({', '.join(columns)}) VALUES ({placeholders})"


def metric_key_hash(row: dict[str, Any]) -> str:
    raw_key = "\x1f".join([row["dimension_code"], row["operator"], row["brand"], row["city"]])
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def metric_values(period: report.Period, row: dict[str, Any], run_id: str) -> tuple[Any, ...]:
    source = row["source"]
    return (
        period.start.isoformat(),
        period.end.isoformat(),
        period.day_count,
        row["dimension_code"],
        row["dimension"],
        row["contact_person"],
        row["operator"],
        row["brand"],
        row["city"],
        row["mapping_status"],
        int(source.get("row_count", 0) or 0),
        metric_key_hash(row),
        *(float(source.get(field, 0) or 0) for field in report.SUM_FIELDS),
        run_id,
    )


def gap_insert_sql() -> str:
    return """
        INSERT INTO hhdata__agg_weekly_gaps (
            refresh_run_id,
            week_start,
            week_end,
            gap_type,
            dimension_code,
            dimension_name,
            contact_person,
            operator_name,
            brand_name,
            city_name,
            field_name,
            period_name,
            reason,
            payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """


def gap_values(period: report.Period, gap: dict[str, Any], run_id: str) -> tuple[Any, ...]:
    dimension = report.clean_text(gap.get("dimension") or gap.get("dimension_name"))
    dimension_code = report.clean_text(gap.get("dimension_code")) or report.DIMENSION_CODE_BY_NAME.get(dimension, "")
    return (
        run_id,
        period.start.isoformat(),
        period.end.isoformat(),
        report.clean_text(gap.get("type")),
        dimension_code or None,
        dimension or None,
        report.clean_text(gap.get("contact_person")) or None,
        report.clean_text(gap.get("operator")) or report.clean_text(gap.get("operator_name")) or None,
        report.clean_text(gap.get("brand")) or report.clean_text(gap.get("brand_name")) or None,
        report.clean_text(gap.get("city")) or report.clean_text(gap.get("city_name")) or None,
        report.clean_text(gap.get("field")) or report.clean_text(gap.get("field_name")) or None,
        report.clean_text(gap.get("period")) or report.clean_text(gap.get("period_name")) or None,
        report.clean_text(gap.get("reason")) or None,
        json.dumps(gap, ensure_ascii=False, default=str),
    )


def refresh_one_week(args: argparse.Namespace, week_start) -> dict[str, Any]:
    validate_week_start(week_start)
    period = report.Period(week_start, week_start + timedelta(days=6))
    db = report.DatabaseConnector()
    if not args.dry_run:
        ensure_schema(db)
        existing = existing_metric_count(db, period)
        if existing and not args.force:
            raise RuntimeError(f"{period.file_label} 已有 {existing} 条聚合数据；如需重刷请加 --force")
    else:
        existing = existing_metric_count(db, period)

    df = load_week_source(db, period)
    mapping_rows = report.load_operator_brand_rows()
    mapping = report.build_mapping(mapping_rows)
    rows, gaps = report.build_weekly_aggregate_rows(df, mapping, period)
    gaps = dedupe_gaps(gaps)
    run_id = f"weekly-{period.file_label}-{datetime.now():%Y%m%d%H%M%S%f}"

    summary = {
        "run_id": run_id,
        "week_start": period.start.isoformat(),
        "week_end": period.end.isoformat(),
        "day_count": period.day_count,
        "dry_run": args.dry_run,
        "force": args.force,
        "existing_metric_rows": existing,
        "source_row_count": int(len(df)),
        "mapping_row_count": len(mapping_rows),
        "metric_row_count": len(rows),
        "gap_count": len(gaps),
        "dimension_counts": dict(report.Counter(row["dimension"] for row in rows)),
        "gap_counts": dict(report.Counter(gap["type"] for gap in gaps)),
    }
    if args.dry_run:
        return summary

    params = json.dumps(
        {
            "week_start": period.start.isoformat(),
            "week_end": period.end.isoformat(),
            "force": args.force,
        },
        ensure_ascii=False,
    )
    db.execute_non_query(
        """
        INSERT INTO hhdata__agg_weekly_refresh_runs (
            id,
            week_start,
            week_end,
            mode,
            status,
            source_row_count,
            metric_row_count,
            gap_count,
            mapping_row_count,
            params
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            run_id,
            period.start.isoformat(),
            period.end.isoformat(),
            "refresh",
            "running",
            int(len(df)),
            len(rows),
            len(gaps),
            len(mapping_rows),
            params,
        ],
    )

    try:
        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {report.WEEKLY_METRICS_TABLE} WHERE week_start = %s AND week_end = %s",
                [period.start.isoformat(), period.end.isoformat()],
            )
            metric_payload = [metric_values(period, row, run_id) for row in rows]
            if metric_payload:
                cursor.executemany(metric_insert_sql(), metric_payload)
            gap_payload = [gap_values(period, gap, run_id) for gap in gaps]
            if gap_payload:
                cursor.executemany(gap_insert_sql(), gap_payload)
            cursor.execute(
                """
                UPDATE hhdata__agg_weekly_refresh_runs
                SET status = %s,
                    finished_at = CURRENT_TIMESTAMP(6),
                    message = %s
                WHERE id = %s
                """,
                ["success", "ok", run_id],
            )
            conn.commit()
    except Exception as exc:
        db.execute_non_query(
            """
            UPDATE hhdata__agg_weekly_refresh_runs
            SET status = %s,
                finished_at = CURRENT_TIMESTAMP(6),
                message = %s
            WHERE id = %s
            """,
            ["failed", str(exc), run_id],
        )
        raise

    return summary


def main() -> int:
    args = parse_args()
    try:
        summaries = [
            refresh_one_week(args, args.week_start + timedelta(days=7 * offset))
            for offset in range(args.weeks)
        ]
    except Exception as exc:
        print(f"❌ 周聚合刷新失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summaries[0] if len(summaries) == 1 else summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
