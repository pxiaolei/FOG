"""
日报构建模块

将三天原始数据转换为日报宽表：每个 (品牌, 城市, 运营主体) 一行，
每行含 17 指标 × 5 子列 = 85 数据列，以及城市基准环比/同比。
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple, Dict

import pandas as pd

# 确保 lxx_share 可 import
def _find_skills_dir():
    from pathlib import Path
    for p in Path(__file__).resolve().parents:
        if (p / "lxx_share").is_dir():
            return p
    return Path(__file__).resolve().parents[2]

_skills_dir = _find_skills_dir()
if str(_skills_dir) not in sys.path:
    sys.path.insert(0, str(_skills_dir))

from lxx_share.hhdata_metrics import (
    compute_derived_metrics, mom_volume, yoy_volume, mom_rate, yoy_rate,
)

# dailyreport 内部模块
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from config import METRICS, SUB_COLUMNS


def _get_metric_value(derived: dict, key: str):
    """从 derived_metrics 字典取指标值，不存在的返回 None"""
    return derived.get(key)


def build_report(
    df_raw: pd.DataFrame,
    df_city: pd.DataFrame = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    将三天原始数据构建为日报宽表。

    Args:
        df_raw: 运营主体的原始数据（含 date, city_id, brand_id, ..., operator_name）
        df_city: 城市全品牌数据（可选，用于计算城市基准）
                 不传则用 df_raw 聚合作为城市基准（不准确）

    Returns:
        (report_df, city_benchmark_df)
        - report_df: 品牌×城市×运营主体 行，含全部指标子列
        - city_benchmark_df: 城市级聚合基准
    """
    if df_raw.empty:
        return pd.DataFrame(), pd.DataFrame()

    rows = []
    groups = df_raw.groupby(["operator_name", "brand_name", "city_name",
                              "brand_id", "city_id"])

    for (op, brand, city, brand_id, city_id), group in groups:
        group = group.sort_values("date")
        row_today = group[group["date"] == group["date"].max()]
        if row_today.empty:
            continue
        row_today = row_today.iloc[0]

        # 计算昨日和上周同日
        today_dt = group["date"].max()
        today_str = today_dt.strftime("%Y-%m-%d") if hasattr(today_dt, "strftime") else str(today_dt)[:10]
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        yesterday_str = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        last_week_str = (dt - timedelta(days=7)).strftime("%Y-%m-%d")

        row_yesterday = group[group["date"].apply(
            lambda d: str(d)[:10] == yesterday_str)]
        row_last_week = group[group["date"].apply(
            lambda d: str(d)[:10] == last_week_str)]

        # 计算当日衍生指标
        today_raw = row_today.to_dict()
        today_derived = compute_derived_metrics(today_raw)

        yesterday_derived = None
        if not row_yesterday.empty:
            yesterday_derived = compute_derived_metrics(row_yesterday.iloc[0].to_dict())

        last_week_derived = None
        if not row_last_week.empty:
            last_week_derived = compute_derived_metrics(row_last_week.iloc[0].to_dict())

        # 构建行
        row_result = {
            "运营主体": op,
            "品牌": brand,
            "城市": city,
            "brand_id": brand_id,
            "city_id": city_id,
        }

        for m in METRICS:
            today_val = _get_metric_value(today_derived, m.key)
            yesterday_val = _get_metric_value(yesterday_derived, m.key) if yesterday_derived else None
            last_week_val = _get_metric_value(last_week_derived, m.key) if last_week_derived else None

            # 当日值
            row_result[f"{m.key}_当日值"] = today_val

            # 环比 / 同比
            if m.type == "volume":
                mom_val = mom_volume(today_val, yesterday_val) if today_val is not None and yesterday_val is not None else None
                yoy_val = yoy_volume(today_val, last_week_val) if today_val is not None and last_week_val is not None else None
            else:
                mom_val = mom_rate(today_val, yesterday_val) if today_val is not None and yesterday_val is not None else None
                yoy_val = yoy_rate(today_val, last_week_val) if today_val is not None and last_week_val is not None else None

            row_result[f"{m.key}_环比"] = mom_val
            row_result[f"{m.key}_同比"] = yoy_val
            # 城市环比/同比先占位，后面填
            row_result[f"{m.key}_城市环比"] = None
            row_result[f"{m.key}_城市同比"] = None

        rows.append(row_result)

    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    report_df = pd.DataFrame(rows)

    # 计算城市基准：优先用全品牌数据，否则用运营主体自身数据
    city_source = df_city if df_city is not None and not df_city.empty else df_raw
    today_date = df_raw["date"].max()
    city_benchmark = _compute_city_benchmarks(city_source, today_date)

    # 填充城市环比/同比（用 .loc 修改原始 DataFrame）
    for idx, row in report_df.iterrows():
        city = row["城市"]
        if city in city_benchmark:
            cb = city_benchmark[city]
            for m in METRICS:
                report_df.at[idx, f"{m.key}_城市环比"] = cb.get(f"{m.key}_mom")
                report_df.at[idx, f"{m.key}_城市同比"] = cb.get(f"{m.key}_yoy")

    return report_df, city_benchmark


def _compute_city_benchmarks(df_raw: pd.DataFrame, today_date) -> Dict[str, Dict[str, float]]:
    """计算每个城市所有品牌汇总后的环比/同比"""
    today_str = str(today_date)[:10] if hasattr(today_date, "strftime") else str(today_date)
    dt = datetime.strptime(today_str, "%Y-%m-%d")
    yesterday_str = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    last_week_str = (dt - timedelta(days=7)).strftime("%Y-%m-%d")

    benchmarks = {}

    for city in df_raw["city_name"].unique():
        city_data = df_raw[df_raw["city_name"] == city]

        # 当日城市汇总
        today_mask = city_data["date"].apply(lambda d: str(d)[:10] == today_str)
        yesterday_mask = city_data["date"].apply(lambda d: str(d)[:10] == yesterday_str)
        last_week_mask = city_data["date"].apply(lambda d: str(d)[:10] == last_week_str)

        today_sum = city_data[today_mask].sum(numeric_only=True).to_dict()
        yesterday_sum = city_data[yesterday_mask].sum(numeric_only=True).to_dict()
        last_week_sum = city_data[last_week_mask].sum(numeric_only=True).to_dict()

        if not today_sum or not yesterday_sum or not last_week_sum:
            benchmarks[city] = {}
            continue

        today_derived = compute_derived_metrics(today_sum)
        yesterday_derived = compute_derived_metrics(yesterday_sum)
        last_week_derived = compute_derived_metrics(last_week_sum)

        cb = {}
        for m in METRICS:
            today_val = today_derived.get(m.key)
            yesterday_val = yesterday_derived.get(m.key)
            last_week_val = last_week_derived.get(m.key)

            if m.type == "volume":
                cb[f"{m.key}_mom"] = mom_volume(today_val, yesterday_val)
                cb[f"{m.key}_yoy"] = yoy_volume(today_val, last_week_val)
            else:
                cb[f"{m.key}_mom"] = mom_rate(today_val, yesterday_val)
                cb[f"{m.key}_yoy"] = yoy_rate(today_val, last_week_val)

        benchmarks[city] = cb

    return benchmarks


def format_report_df(report_df: pd.DataFrame) -> pd.DataFrame:
    """
    格式化 report DataFrame，只保留展示列（去掉内部 ID 列），
    并按当天完单倒序排序。
    """
    if report_df.empty:
        return report_df

    show_cols = ["运营主体", "品牌", "城市"]
    for m in METRICS:
        for sub in SUB_COLUMNS:
            show_cols.append(f"{m.key}_{sub}")

    df = report_df[show_cols].copy()
    df = df.sort_values(
        ["运营主体", "completed_orders_当日值", "品牌", "城市"],
        ascending=[True, False, True, True],
        na_position="last",
    ).reset_index(drop=True)
    return df
