import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_weekly_report.py"
SPEC = importlib.util.spec_from_file_location("run_weekly_report", SCRIPT_PATH)
zhoubao = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["run_weekly_report"] = zhoubao
SPEC.loader.exec_module(zhoubao)


def sample_rows():
    base = {field: 0 for field in zhoubao.SUM_FIELDS}
    rows = []
    for period, day, completed, placed, answered, matched, gmv in [
        ("previous", date(2026, 6, 8), 100, 200, 150, 160, 1000),
        ("current", date(2026, 6, 15), 120, 240, 180, 200, 1200),
        ("current", date(2026, 6, 15), 10, 0, 0, 0, 100),
    ]:
        row = {
            **base,
            "period": period,
            "date": day,
            "brand_name": "品牌A" if completed != 10 else "未映射品牌",
            "city_name": "上海市" if completed != 10 else "未知市",
            "completed_order_count": completed,
            "passenger_order_count": placed,
            "response_count": answered,
            "match_count": matched,
            "gmv": gmv,
            "brand_commission": gmv * 0.1,
            "merchant_b_subsidy": gmv * 0.02,
            "card_merchant_income": gmv * 0.01,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def weekly_records(rows, period):
    records = []
    for row in rows:
        source = row["source"]
        records.append(
            {
                "week_start": period.start,
                "week_end": period.end,
                "day_count": period.day_count,
                "dimension_code": row["dimension_code"],
                "dimension_name": row["dimension"],
                "contact_person": row["contact_person"],
                "operator_name": row["operator"],
                "brand_name": row["brand"],
                "city_name": row["city"],
                "mapping_status": row["mapping_status"],
                "source_row_count": source["row_count"],
                **{field: source[field] for field in zhoubao.SUM_FIELDS},
            }
        )
    return records


def daily_agg_frame(dates):
    base = {field: 0 for field in zhoubao.SUM_FIELDS}
    rows = []
    for day in dates:
        rows.append(
            {
                **base,
                "metric_date": day,
                "date": day,
                "brand_name": "品牌A",
                "city_name": "上海市",
                "source_row_count": 1,
                "completed_order_count": 10,
            }
        )
    return pd.DataFrame(rows)


class WeeklyReportTest(unittest.TestCase):
    def test_latest_complete_week_when_latest_is_sunday(self):
        period = zhoubao.latest_complete_week(date(2026, 6, 21))
        self.assertEqual(period.start, date(2026, 6, 15))
        self.assertEqual(period.end, date(2026, 6, 21))

    def test_latest_complete_week_when_latest_is_midweek(self):
        period = zhoubao.latest_complete_week(date(2026, 6, 24))
        self.assertEqual(period.start, date(2026, 6, 15))
        self.assertEqual(period.end, date(2026, 6, 21))

    def test_custom_period_shifts_previous_by_seven_days(self):
        periods = zhoubao.resolve_periods(date(2026, 6, 15), date(2026, 6, 17), None)
        self.assertEqual(periods.current.day_count, 3)
        self.assertEqual(periods.previous.start, date(2026, 6, 8))
        self.assertEqual(periods.previous.end, date(2026, 6, 10))

    def test_build_rows_has_five_dimensions_and_unmapped_gap(self):
        periods = zhoubao.resolve_periods(date(2026, 6, 15), date(2026, 6, 15), None)
        mapping = zhoubao.build_mapping(
            [
                {
                    "operator": "主体A",
                    "brand": "品牌A",
                    "city": "上海市",
                    "contact_person": "雷维亮",
                }
            ]
        )

        rows, gaps = zhoubao.build_report_rows(sample_rows(), mapping, periods)

        dims = {row["dimension"] for row in rows}
        self.assertEqual(dims, {"品牌城市维度", "城市维度", "品牌维度", "主体纬度", "大盘维度"})
        self.assertTrue(any(row["operator"] == "主体A" for row in rows if row["dimension"] == "品牌城市维度"))
        self.assertTrue(any(gap["type"] == "unmapped_brand_city" for gap in gaps))

    def test_dimension_order(self):
        periods = zhoubao.resolve_periods(date(2026, 6, 15), date(2026, 6, 15), None)
        mapping = zhoubao.build_mapping(
            [
                {
                    "operator": "主体A",
                    "brand": "品牌A",
                    "city": "上海市",
                    "contact_person": "雷维亮",
                }
            ]
        )

        rows, _ = zhoubao.build_report_rows(sample_rows(), mapping, periods)
        order = []
        for row in rows:
            if row["dimension"] not in order:
                order.append(row["dimension"])

        self.assertEqual(order, ["大盘维度", "主体纬度", "品牌维度", "品牌城市维度", "城市维度"])

    def test_zero_denominator_is_reported_as_missing(self):
        periods = zhoubao.resolve_periods(date(2026, 6, 15), date(2026, 6, 15), None)
        mapping = zhoubao.build_mapping([])
        rows, gaps = zhoubao.build_report_rows(sample_rows(), mapping, periods)

        self.assertTrue(
            any(
                gap["type"] == "metric_missing"
                and gap["field"] == "成交率"
                and "分母为0" in gap["reason"]
                for gap in gaps
            )
        )
        self.assertTrue(any(gap["type"] == "change_missing" for gap in gaps))

    def test_change_formula_does_not_divide_inside_or_checks(self):
        cols = {name: name for name in zhoubao.source_columns()}
        metric = next(metric for metric in zhoubao.METRICS if metric.label == "人均完单")

        formula = zhoubao.formula_change(metric, cols)
        or_checks = formula.split("OR(", 1)[1].split(f'),"{zhoubao.MISSING_DISPLAY}"', 1)[0]

        self.assertTrue(formula.startswith("=IFERROR("))
        self.assertNotIn("/", or_checks)

    def test_weekly_aggregate_rows_include_dimension_codes(self):
        period = zhoubao.Period(date(2026, 6, 15), date(2026, 6, 21))
        mapping = zhoubao.build_mapping(
            [
                {
                    "operator": "主体A",
                    "brand": "品牌A",
                    "city": "上海市",
                    "contact_person": "雷维亮",
                }
            ]
        )

        rows, gaps = zhoubao.build_weekly_aggregate_rows(sample_rows(), mapping, period)

        self.assertEqual(rows[0]["dimension_code"], "all")
        self.assertTrue(any(row["dimension_code"] == "brand_city" for row in rows))
        self.assertTrue(any(row["mapping_status"] == "unmapped" for row in rows))
        self.assertTrue(any(gap["type"] == "unmapped_brand_city" for gap in gaps))

    def test_report_rows_from_weekly_agg_keep_order(self):
        periods = zhoubao.resolve_periods(date(2026, 6, 15), date(2026, 6, 21), None)
        mapping = zhoubao.build_mapping(
            [
                {
                    "operator": "主体A",
                    "brand": "品牌A",
                    "city": "上海市",
                    "contact_person": "雷维亮",
                }
            ]
        )
        df = sample_rows()
        prev_rows, _ = zhoubao.build_weekly_aggregate_rows(df, mapping, periods.previous, "previous")
        curr_rows, _ = zhoubao.build_weekly_aggregate_rows(df, mapping, periods.current, "current")
        weekly_df = pd.DataFrame(weekly_records(prev_rows, periods.previous) + weekly_records(curr_rows, periods.current))

        rows, _ = zhoubao.build_report_rows_from_weekly_agg(weekly_df, periods)
        order = []
        for row in rows:
            if row["dimension"] not in order:
                order.append(row["dimension"])

        self.assertEqual(order, ["大盘维度", "主体纬度", "品牌维度", "品牌城市维度", "城市维度"])
        self.assertEqual(rows[0]["source"]["current_completed_order_count"], 130)

    def test_daily_agg_requires_all_previous_and_current_dates(self):
        periods = zhoubao.resolve_periods(date(2026, 6, 15), date(2026, 6, 17), None)
        complete_dates = [
            date(2026, 6, 8),
            date(2026, 6, 9),
            date(2026, 6, 10),
            date(2026, 6, 15),
            date(2026, 6, 16),
            date(2026, 6, 17),
        ]

        self.assertTrue(zhoubao.daily_agg_has_periods(daily_agg_frame(complete_dates), periods))
        self.assertFalse(zhoubao.daily_agg_has_periods(daily_agg_frame(complete_dates[:-1]), periods))


if __name__ == "__main__":
    unittest.main()
