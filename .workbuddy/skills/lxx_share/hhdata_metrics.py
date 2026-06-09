"""
hhdata 共享指标计算模块

纯函数，不依赖数据库连接。所有基于 hhdata.fact_daily_metrics 单表的
指标计算逻辑集中在这里，供日报、指标计算、趋势分析、异动分析等技能复用。

计算规则：
- 量值指标环比/同比：变化率（比率）
- 率值指标环比/同比：百分点差值（pp）
"""

from typing import Optional


def is_missing(value) -> bool:
    """判断空值；兼容 None 和 NaN。"""
    if value is None:
        return True
    try:
        return bool(value != value)
    except Exception:
        return False


def safe_div(a: float, b: float) -> Optional[float]:
    """安全除法，分母为 0 或 None 返回 None"""
    if is_missing(a) or is_missing(b) or b == 0:
        return None
    return a / b


# ── 环比 / 同比 ──

def mom_volume(today: float, yesterday: float) -> Optional[float]:
    """量值日环比：(今日 - 昨日) / 昨日"""
    if is_missing(today) or is_missing(yesterday) or yesterday == 0:
        return None
    return (today - yesterday) / yesterday


def yoy_volume(today: float, last_week: float) -> Optional[float]:
    """量值周同比：(今日 - 上周同日) / 上周同日"""
    if is_missing(today) or is_missing(last_week) or last_week == 0:
        return None
    return (today - last_week) / last_week


def mom_rate(today_rate: float, yesterday_rate: float) -> Optional[float]:
    """率值日环比（pp 差值）：今日率值 - 昨日率值"""
    if is_missing(today_rate) or is_missing(yesterday_rate):
        return None
    return today_rate - yesterday_rate


def yoy_rate(today_rate: float, last_week_rate: float) -> Optional[float]:
    """率值周同比（pp 差值）：今日率值 - 上周率值"""
    if is_missing(today_rate) or is_missing(last_week_rate):
        return None
    return today_rate - last_week_rate


# ── 衍生指标计算 ──

def calc_merchant_b_subsidy_rate(merchant_b_subsidy: float, gmv: float) -> Optional[float]:
    """商家B补率 = 商家B补 / GMV"""
    return safe_div(merchant_b_subsidy, gmv)


def calc_brand_commission_rate(brand_commission: float, gmv: float) -> Optional[float]:
    """商家抽佣TR = 品牌抽佣 / GMV"""
    return safe_div(brand_commission, gmv)


def calc_total_commission_rate(total_commission: float, gmv: float) -> Optional[float]:
    """总TR = 总抽佣 / GMV"""
    return safe_div(total_commission, gmv)


def calc_card_income_rate(card_merchant_income: float, gmv: float) -> Optional[float]:
    """售卡收入率 = 售卡商家收入 / GMV"""
    return safe_div(card_merchant_income, gmv)


def calc_online_gross_margin(tr: Optional[float], card_rate: Optional[float],
                              b_rate: Optional[float]) -> Optional[float]:
    """线上毛利率 = 商家抽佣TR + 售卡收入率 - 商家B补率 - 1%"""
    if tr is None or card_rate is None or b_rate is None:
        return None
    return tr + card_rate - b_rate - 0.01


def calc_unit_price(gmv: float, completed_orders: float) -> Optional[float]:
    """客单价 = GMV / 完单数"""
    return safe_div(gmv, completed_orders)


def calc_avg_orders_per_driver(completed_orders: float, completed_drivers: float) -> Optional[float]:
    """人均完单量 = 完单数 / 完单司机数"""
    return safe_div(completed_orders, completed_drivers)


def calc_tph(completed_orders: float, online_duration_hours: float) -> Optional[float]:
    """TPH（司机效率）= 完单数 / 在线时长"""
    return safe_div(completed_orders, online_duration_hours)


def calc_avg_online_hours_per_driver(online_duration_hours: float, online_drivers: float) -> Optional[float]:
    """人均在线时长TSH = 司机在线时长 / 在线司机数"""
    return safe_div(online_duration_hours, online_drivers)


def calc_driver_cancel_rate(cancelled_by_driver: float, answered_orders: float) -> Optional[float]:
    """司机取消率 = 应答后司机取消量 / 应答量"""
    return safe_div(cancelled_by_driver, answered_orders)


def calc_passenger_cancel_rate(cancelled_by_passenger: float, answered_orders: float) -> Optional[float]:
    """乘客取消率 = 应答后乘客取消量 / 应答量"""
    return safe_div(cancelled_by_passenger, answered_orders)


def calc_total_cancel_rate(cancelled_before_answer: float, answered_orders: float) -> Optional[float]:
    """总取消率 = 应答前取消订单量 / 应答量"""
    return safe_div(cancelled_before_answer, answered_orders)


def calc_response_rate(answered_orders: float, placed_orders: float) -> Optional[float]:
    """发单应答率 = 应答量 / 发单量"""
    return safe_div(answered_orders, placed_orders)


def calc_answer_completion_rate(completed_orders: float, answered_orders: float) -> Optional[float]:
    """应答完单率 = 完单数 / 应答量"""
    return safe_div(completed_orders, answered_orders)


def calc_match_response_rate(answered_orders: float, matched_orders: float) -> Optional[float]:
    """匹配应答率 = 应答量 / 匹配量"""
    return safe_div(answered_orders, matched_orders)


def calc_driver_utilization(completed_drivers: float, online_drivers: float) -> Optional[float]:
    """完单司机占比 = 完单司机数 / 在线司机数"""
    return safe_div(completed_drivers, online_drivers)


def calc_peak_valid_driver_rate(peak_valid_drivers: float, peak_online_drivers: float) -> Optional[float]:
    """峰期有效司机率 = 峰期有效司机数 / 峰期在线司机数"""
    return safe_div(peak_valid_drivers, peak_online_drivers)


def compute_derived_metrics(row: dict) -> dict:
    """
    从一行 hhdata 原始数据计算所有衍生指标。

    Args:
        row: 包含 hhdata 原始字段的字典，至少需含：
            gmv, completed_orders, placed_orders, online_drivers,
            completed_drivers, online_duration_hours, answered_orders,
            merchant_b_subsidy, brand_commission, card_merchant_income,
            cancelled_by_driver, first_completed_drivers

    Returns:
        dict，key 为指标 key，value 为计算值
    """
    gmv = row.get("gmv", 0) or 0
    completed = row.get("completed_orders", 0) or 0
    placed = row.get("placed_orders", 0) or 0
    answered = row.get("answered_orders", 0) or 0

    b_rate = calc_merchant_b_subsidy_rate(
        row.get("merchant_b_subsidy", 0) or 0, gmv)
    tr = calc_brand_commission_rate(
        row.get("brand_commission", 0) or 0, gmv)
    total_tr = calc_total_commission_rate(
        row.get("total_commission", 0) or 0, gmv)
    card_rate = calc_card_income_rate(
        row.get("card_merchant_income", 0) or 0, gmv)

    return {
        # 直接字段
        "completed_orders": completed,
        "placed_orders": placed,
        "gmv": gmv,
        "online_drivers": row.get("online_drivers", 0) or 0,
        "online_duration_hours": row.get("online_duration_hours", 0) or 0,
        "first_completed_drivers": row.get("first_completed_drivers", 0) or 0,
        # 衍生量值
        "unit_price": calc_unit_price(gmv, completed),
        "avg_orders_per_driver": calc_avg_orders_per_driver(
            completed, row.get("completed_drivers", 0) or 0),
        "tph": calc_tph(completed, row.get("online_duration_hours", 0) or 0),
        "avg_online_hours_per_driver": calc_avg_online_hours_per_driver(
            row.get("online_duration_hours", 0) or 0,
            row.get("online_drivers", 0) or 0),
        # 衍生率值
        "merchant_b_subsidy_rate": b_rate,
        "brand_commission_rate": tr,
        "total_commission_rate": total_tr,
        "card_income_rate": card_rate,
        "online_gross_margin": calc_online_gross_margin(tr, card_rate, b_rate),
        "response_rate": calc_response_rate(
            answered, placed),
        "completion_rate": calc_answer_completion_rate(completed, answered),
        "answer_completion_rate": calc_answer_completion_rate(completed, answered),
        "match_response_rate": calc_match_response_rate(
            answered, row.get("matched_orders", 0) or 0),
        "driver_cancel_rate": calc_driver_cancel_rate(
            row.get("cancelled_by_driver", 0) or 0, answered),
        "passenger_cancel_rate": calc_passenger_cancel_rate(
            row.get("cancelled_by_passenger", 0) or 0, answered),
        "total_cancel_rate": calc_total_cancel_rate(
            row.get("cancelled_before_answer", 0) or 0, answered),
        "driver_utilization": calc_driver_utilization(
            row.get("completed_drivers", 0) or 0,
            row.get("online_drivers", 0) or 0),
        "peak_valid_driver_rate": calc_peak_valid_driver_rate(
            row.get("peak_valid_drivers", 0) or 0,
            row.get("peak_online_drivers", 0) or 0),
    }
