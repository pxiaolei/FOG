"""
数据加载模块

从 hhdata.fact_daily_metrics 查询指定运营主体/对接人的原始数据，
结合码表过滤，返回三天（当日、昨日、上周同日）的原始 DataFrame。
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

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

from lxx_share.database import DatabaseConnector
from lxx_share.excel_utils import load_mabiao, filter_by_person
from lxx_share.utils import get_logger

logger = get_logger("lx-dapanribao.data_loader")

# ── 码表缓存（避免重复加载）──
_mabiao_cache: dict | None = None
_mabiao_path_warning_shown = False


def _yesterday(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt - timedelta(days=1)).strftime("%Y-%m-%d")


def _last_week_same_day(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt - timedelta(days=7)).strftime("%Y-%m-%d")


def _load_operator_brand_mapping(mabiao_path: str | None = None) -> Optional[dict]:
    """加载公司库 operator_brand 码表；旧 mabiao_path 参数仅保留兼容。"""
    global _mabiao_cache, _mabiao_path_warning_shown
    if mabiao_path and not _mabiao_path_warning_shown:
        logger.warning(
            "mabiao_path 已废弃并会被忽略；日报码表固定从 lx_shujuku.operator_brand 加载"
        )
        _mabiao_path_warning_shown = True
    if _mabiao_cache is None:
        _mabiao_cache = load_mabiao()
    return _mabiao_cache


def _build_sql(brand_city_pairs: list, dates: List[str]) -> tuple:
    """
    构建查询 hhdata 的 SQL。

    注意：使用精确的 (品牌, 城市) 配对过滤，不能用独立的 brand IN (...)
    和 city IN (...) ——那样会把不属于该运营主体的品牌×城市组合也查出来。
    """
    date_ph = ", ".join(["%s"] * len(dates))

    # 精确配对：(brand1, city1) OR (brand2, city2) ...
    pair_clauses = []
    for _ in brand_city_pairs:
        pair_clauses.append("(b.brand_name = %s AND c.city_name = %s)")

    sql = f"""
        SELECT f.date, f.city_id, c.city_name, f.brand_id, b.brand_name,
               f.placed_orders, f.completed_orders, f.online_drivers,
               f.online_duration_hours, f.first_completed_drivers, f.gmv,
               f.merchant_b_subsidy, f.brand_commission, f.card_merchant_income,
               f.completed_drivers, f.cancelled_by_driver, f.answered_orders
        FROM hhdata.fact_daily_metrics f
        JOIN mabiao.dim_cities c ON f.city_id = c.city_id
        JOIN mabiao.dim_brands b ON f.brand_id = b.brand_id
        WHERE f.date IN ({date_ph})
          AND ({" OR ".join(pair_clauses)})
        ORDER BY b.brand_name, c.city_name, f.date
    """
    # 参数顺序：dates, then (brand, city) pairs flattened
    params = list(dates)
    for brand, city in brand_city_pairs:
        params.extend([brand, city])
    return sql, params


def get_operators_for_person(person: str, mabiao_path: str = None) -> List[str]:
    """获取对接人负责的所有运营主体"""
    mapping = _load_operator_brand_mapping(mabiao_path)
    if mapping is None:
        return []
    filtered, _ = filter_by_person(mapping, [person])
    return sorted(filtered["all_zhuti"])


def get_brand_city_for_operator(operator: str, mabiao_path: str = None) -> tuple:
    """
    获取运营主体在码表中对应的 (品牌列表, 城市列表)。

    Returns:
        (brand_names, city_names, brand_city_pairs)
    """
    mapping = _load_operator_brand_mapping(mabiao_path)
    if mapping is None:
        return [], [], []

    brands, cities, pairs = set(), set(), set()
    for (brand, city), zhuti_list in mapping["brand_city_to_zhuti"].items():
        if operator in zhuti_list:
            if brand == "-":
                brand = "方舟行车主"
            brands.add(brand)
            cities.add(city)
            pairs.add((brand, city))

    return sorted(brands), sorted(cities), sorted(pairs)


def load_data_for_operator(
    operator: str,
    today: str,
    db: Optional[DatabaseConnector] = None,
    mabiao_path: str = None,
) -> pd.DataFrame:
    """
    加载指定运营主体的三天原始数据。

    Args:
        operator: 运营主体名称（如 "江豚出行"）
        today: 当日日期 "YYYY-MM-DD"
        db: 数据库连接（可选）
        mabiao_path: 兼容旧参数，已废弃并忽略

    Returns:
        DataFrame，含 operator_name 列。空 DataFrame 表示无数据。
    """
    if db is None:
        db = DatabaseConnector()

    yesterday = _yesterday(today)
    last_week = _last_week_same_day(today)
    dates = [today, yesterday, last_week]

    brands, cities, pairs = get_brand_city_for_operator(operator, mabiao_path)
    if not brands or not cities:
        logger.warning(f"[{operator}] 码表中无品牌/城市记录")
        return pd.DataFrame()

    logger.info(f"[{operator}] 品牌: {len(brands)}, 城市: {len(cities)}, "
                f"组合: {len(pairs)}, 日期: {dates}")

    sql, params = _build_sql(pairs, dates)
    df = db.execute(sql, params)

    if df.empty:
        logger.warning(f"[{operator}] hhdata 无数据")
        return df

    df["operator_name"] = operator
    logger.info(f"[{operator}] 加载 {len(df)} 行原始数据")
    return df


def load_city_benchmark_data(
    cities: List[str],
    today: str,
    db: Optional[DatabaseConnector] = None,
) -> pd.DataFrame:
    """
    加载指定城市所有品牌的三天原始数据（用于城市基准计算）。

    Args:
        cities: 城市名称列表
        today: 当日日期
        db: 数据库连接

    Returns:
        DataFrame，含所有品牌的三天数据
    """
    if db is None:
        db = DatabaseConnector()

    yesterday = _yesterday(today)
    last_week = _last_week_same_day(today)
    dates = [today, yesterday, last_week]

    placeholders = ", ".join(["%s"] * len(dates))
    city_placeholders = ", ".join(["%s"] * len(cities))

    sql = f"""
        SELECT f.date, c.city_name,
               f.placed_orders, f.completed_orders, f.online_drivers,
               f.online_duration_hours, f.first_completed_drivers, f.gmv,
               f.merchant_b_subsidy, f.brand_commission, f.card_merchant_income,
               f.completed_drivers, f.cancelled_by_driver, f.answered_orders
        FROM hhdata.fact_daily_metrics f
        JOIN mabiao.dim_cities c ON f.city_id = c.city_id
        WHERE f.date IN ({placeholders})
          AND c.city_name IN ({city_placeholders})
        ORDER BY c.city_name, f.date
    """
    params = dates + cities
    return db.execute(sql, params)


def load_data_for_person(
    person: str,
    today: str,
    db: Optional[DatabaseConnector] = None,
    mabiao_path: str = None,
) -> pd.DataFrame:
    """
    加载对接人负责的所有运营主体的三天原始数据。

    Args:
        person: 对接人名称（如 "雷维亮"）
        today: 当日日期
        db: 数据库连接
        mabiao_path: 兼容旧参数，已废弃并忽略

    Returns:
        DataFrame，含 operator_name 列
    """
    operators = get_operators_for_person(person, mabiao_path)
    if not operators:
        logger.warning(f"[{person}] 码表中无对应运营主体")
        return pd.DataFrame()

    logger.info(f"[{person}] 负责 {len(operators)} 个运营主体: {operators}")

    if db is None:
        db = DatabaseConnector()

    dfs = []
    for op in operators:
        df_op = load_data_for_operator(op, today, db, mabiao_path)
        if not df_op.empty:
            dfs.append(df_op)

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)
