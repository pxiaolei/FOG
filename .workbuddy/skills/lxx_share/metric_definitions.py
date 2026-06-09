"""
LX 业务指标定义（自包含版本，无外部包依赖）。

本模块是 lxx_ops.metrics.definitions 的独立副本，
供 p-fog 项目的日报等 Skill 直接使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


MetricType = Literal["volume", "rate"]
Aggregation = Literal["sum", "derived_after_sum", "identity", "max", "count", "flag"]
Comparison = Literal["pct_change", "pp_delta", "none"]


@dataclass(frozen=True)
class FieldDefinition:
    table: str
    column: str
    name: str
    category: str
    aggregation: Aggregation
    description: str = ""


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    name: str
    metric_type: MetricType
    formula: str
    source_fields: tuple[str, ...]
    aggregation: Aggregation
    comparison: Comparison
    current_unit: str
    change_unit: str
    higher_is_better: bool = True
    preferred_source: str = "hhdata.fact_daily_metrics"
    ontology_object: str = "DailyMetric"
    description: str = ""


HH_FIELD_DEFINITIONS: tuple[FieldDefinition, ...] = (
    FieldDefinition("hhdata.fact_daily_metrics", "id", "主键", "system", "identity"),
    FieldDefinition("hhdata.fact_daily_metrics", "date", "日期", "dimension", "identity"),
    FieldDefinition("hhdata.fact_daily_metrics", "city_id", "城市ID", "dimension", "identity"),
    FieldDefinition("hhdata.fact_daily_metrics", "brand_id", "品牌ID", "dimension", "identity"),
    FieldDefinition("hhdata.fact_daily_metrics", "placed_orders", "发单量", "order", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "completed_orders", "完单数", "order", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "answered_orders", "应答量", "order", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "matched_orders", "匹配量", "order", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "online_drivers", "在线司机数", "driver", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "online_duration_hours", "在线时长", "driver", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "completed_drivers", "完单司机数", "driver", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "first_completed_drivers", "首次完单司机数", "driver", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "gmv", "GMV", "finance", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "merchant_b_subsidy", "商家B补金额", "finance", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "brand_commission", "品牌抽佣", "finance", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "total_commission", "总抽佣", "finance", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "card_merchant_income", "售卡商家收入", "finance", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "cancelled_by_driver", "司机取消量", "cancel", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "cancelled_by_passenger", "乘客取消量", "cancel", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "cancelled_before_answer", "应答前取消量", "cancel", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "peak_online_drivers", "峰期在线司机数", "driver", "sum"),
    FieldDefinition("hhdata.fact_daily_metrics", "peak_valid_drivers", "峰期有效司机数", "driver", "sum"),
)


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "completed_orders", "完单", "volume", "SUM(completed_orders)",
        ("completed_orders",), "sum", "pct_change", "orders", "%",
    ),
    MetricDefinition(
        "placed_orders", "发单", "volume", "SUM(placed_orders)",
        ("placed_orders",), "sum", "pct_change", "orders", "%",
    ),
    MetricDefinition(
        "gmv", "GMV", "volume", "SUM(gmv)", ("gmv",), "sum",
        "pct_change", "currency", "%",
    ),
    MetricDefinition(
        "online_drivers", "在线司机", "volume", "SUM(online_drivers)",
        ("online_drivers",), "sum", "pct_change", "drivers", "%",
    ),
    MetricDefinition(
        "online_duration_hours", "TSH/在线时长", "volume", "SUM(online_duration_hours)",
        ("online_duration_hours",), "sum", "pct_change", "hours", "%",
    ),
    MetricDefinition(
        "first_completed_drivers", "首次完单司机数", "volume", "SUM(first_completed_drivers)",
        ("first_completed_drivers",), "sum", "pct_change", "drivers", "%",
    ),
    MetricDefinition(
        "unit_price", "客单价", "volume", "SUM(gmv) / SUM(completed_orders)",
        ("gmv", "completed_orders"), "derived_after_sum", "pct_change", "currency/order", "%",
    ),
    MetricDefinition(
        "avg_orders_per_driver", "人均完单量", "volume",
        "SUM(completed_orders) / SUM(completed_drivers)",
        ("completed_orders", "completed_drivers"), "derived_after_sum",
        "pct_change", "orders/driver", "%",
    ),
    MetricDefinition(
        "tph", "TPH/司机效率", "volume",
        "SUM(completed_orders) / SUM(online_duration_hours)",
        ("completed_orders", "online_duration_hours"), "derived_after_sum",
        "pct_change", "orders/hour", "%",
    ),
    MetricDefinition(
        "avg_online_hours_per_driver", "人均在线时长TSH", "volume",
        "SUM(online_duration_hours) / SUM(online_drivers)",
        ("online_duration_hours", "online_drivers"), "derived_after_sum",
        "pct_change", "hours/driver", "%",
    ),
    MetricDefinition(
        "merchant_b_subsidy_rate", "商家B补率", "rate",
        "SUM(merchant_b_subsidy) / SUM(gmv)",
        ("merchant_b_subsidy", "gmv"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "brand_commission_rate", "商家抽佣TR", "rate",
        "SUM(brand_commission) / SUM(gmv)",
        ("brand_commission", "gmv"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "total_commission_rate", "总TR", "rate",
        "SUM(total_commission) / SUM(gmv)",
        ("total_commission", "gmv"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "card_income_rate", "售卡收入率", "rate",
        "SUM(card_merchant_income) / SUM(gmv)",
        ("card_merchant_income", "gmv"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "online_gross_margin", "线上毛利率", "rate",
        "brand_commission_rate + card_income_rate - merchant_b_subsidy_rate - 0.01",
        ("brand_commission", "card_merchant_income", "merchant_b_subsidy", "gmv"),
        "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "response_rate", "发单应答率", "rate",
        "SUM(answered_orders) / SUM(placed_orders)",
        ("answered_orders", "placed_orders"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "completion_rate", "应答完单率", "rate",
        "SUM(completed_orders) / SUM(answered_orders)",
        ("completed_orders", "answered_orders"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "match_response_rate", "匹配应答率", "rate",
        "SUM(answered_orders) / SUM(matched_orders)",
        ("answered_orders", "matched_orders"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "driver_utilization", "完单司机占比", "rate",
        "SUM(completed_drivers) / SUM(online_drivers)",
        ("completed_drivers", "online_drivers"), "derived_after_sum", "pp_delta", "%", "pp",
    ),
    MetricDefinition(
        "driver_cancel_rate", "司机取消率", "rate",
        "SUM(cancelled_by_driver) / SUM(answered_orders)",
        ("cancelled_by_driver", "answered_orders"), "derived_after_sum",
        "pp_delta", "%", "pp", higher_is_better=False,
    ),
    MetricDefinition(
        "passenger_cancel_rate", "乘客取消率", "rate",
        "SUM(cancelled_by_passenger) / SUM(answered_orders)",
        ("cancelled_by_passenger", "answered_orders"), "derived_after_sum",
        "pp_delta", "%", "pp", higher_is_better=False,
    ),
    MetricDefinition(
        "total_cancel_rate", "总取消率", "rate",
        "SUM(cancelled_before_answer) / SUM(answered_orders)",
        ("cancelled_before_answer", "answered_orders"), "derived_after_sum",
        "pp_delta", "%", "pp", higher_is_better=False,
    ),
    MetricDefinition(
        "peak_valid_driver_rate", "峰期有效司机率", "rate",
        "SUM(peak_valid_drivers) / SUM(peak_online_drivers)",
        ("peak_valid_drivers", "peak_online_drivers"), "derived_after_sum",
        "pp_delta", "%", "pp",
    ),
)


DAILY_REPORT_METRIC_KEYS: tuple[str, ...] = (
    "completed_orders",
    "placed_orders",
    "online_gross_margin",
    "brand_commission_rate",
    "card_income_rate",
    "merchant_b_subsidy_rate",
    "online_drivers",
    "online_duration_hours",
    "tph",
    "first_completed_drivers",
    "avg_orders_per_driver",
    "gmv",
    "unit_price",
    "response_rate",
    "completion_rate",
    "driver_utilization",
    "driver_cancel_rate",
)


def metric_definitions_by_key() -> dict[str, MetricDefinition]:
    return {m.key: m for m in METRIC_DEFINITIONS}


def get_metric_definition(key: str) -> Optional[MetricDefinition]:
    return metric_definitions_by_key().get(key)


def daily_report_metric_definitions() -> list[MetricDefinition]:
    metrics = metric_definitions_by_key()
    return [metrics[key] for key in DAILY_REPORT_METRIC_KEYS]


def fields_for_table(table: str) -> list[FieldDefinition]:
    return [field for field in HH_FIELD_DEFINITIONS if field.table == table]


__all__ = [
    "DAILY_REPORT_METRIC_KEYS",
    "HH_FIELD_DEFINITIONS",
    "METRIC_DEFINITIONS",
    "FieldDefinition",
    "MetricDefinition",
    "daily_report_metric_definitions",
    "fields_for_table",
    "get_metric_definition",
    "metric_definitions_by_key",
]
