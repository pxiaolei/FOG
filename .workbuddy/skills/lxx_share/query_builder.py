"""
统一 SQL 查询构建模块

提供类型安全的 SQL 查询构建器，确保：
1. 字段列表一致
2. 过滤条件安全（参数化查询）
3. 查询片段可复用
4. 自动处理维度表 JOIN（品牌/城市名称）
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

from lxx_share.utils import get_logger

logger = get_logger("lxx_share.query_builder")


@dataclass
class FieldSpec:
    """字段规格定义"""
    db_name: str          # 数据库字段名（如 "f.completed_orders"）
    display_name: str     # 显示名称（中文）
    data_type: str = "numeric"  # numeric, string, date


# 标准字段定义（所有分析类 skill 共享）
STANDARD_FIELDS: Dict[str, FieldSpec] = {
    # 基础维度
    "date":              FieldSpec("f.date", "日期", "date"),
    "city_id":           FieldSpec("f.city_id", "城市ID", "numeric"),
    "city_name":         FieldSpec("c.city_name", "城市名称", "string"),
    "brand_id":          FieldSpec("f.brand_id", "品牌ID", "numeric"),
    "brand_name":        FieldSpec("b.brand_name", "品牌名称", "string"),

    # 订单指标
    "placed_orders":      FieldSpec("f.placed_orders", "乘客发单量", "numeric"),
    "broadcast_orders":  FieldSpec("f.broadcast_orders", "播单量", "numeric"),
    "matched_orders":    FieldSpec("f.matched_orders", "匹配量", "numeric"),
    "answered_orders":   FieldSpec("f.answered_orders", "应答量", "numeric"),
    "completed_orders":  FieldSpec("f.completed_orders", "完单数", "numeric"),

    # 取消指标
    "cancelled_before_answer":  FieldSpec("f.cancelled_before_answer", "应答前取消订单量", "numeric"),
    "cancelled_by_passenger":   FieldSpec("f.cancelled_by_passenger", "应答后乘客取消量", "numeric"),
    "cancelled_by_driver":      FieldSpec("f.cancelled_by_driver", "应答后司机取消量", "numeric"),

    # 司机指标
    "online_drivers":     FieldSpec("f.online_drivers", "在线司机数", "numeric"),
    "completed_drivers": FieldSpec("f.completed_drivers", "完单司机数", "numeric"),
    "online_duration_hours": FieldSpec("f.online_duration_hours", "司机在线时长h", "numeric"),
    "peak_online_drivers": FieldSpec("f.peak_online_drivers", "峰期在线司机数", "numeric"),
    "peak_valid_drivers": FieldSpec("f.peak_valid_drivers", "峰期有效司机数", "numeric"),
    "valid_drivers":      FieldSpec("f.valid_drivers", "有效司机数", "numeric"),
    "approved_drivers":   FieldSpec("f.approved_drivers", "审核通过司机数", "numeric"),
    "first_online_drivers": FieldSpec("f.first_online_drivers", "首次在线司机数", "numeric"),
    "first_completed_drivers": FieldSpec("f.first_completed_drivers", "首次完单司机数", "numeric"),

    # 财务指标
    "gmv":                FieldSpec("f.gmv", "GMV", "numeric"),
    "total_b_subsidy":    FieldSpec("f.total_b_subsidy", "总b补金额", "numeric"),
    "merchant_b_subsidy": FieldSpec("f.merchant_b_subsidy", "商家b补金额", "numeric"),
    "total_commission":   FieldSpec("f.total_commission", "总抽佣", "numeric"),
    "brand_commission":   FieldSpec("f.brand_commission", "品牌抽佣", "numeric"),
    "card_merchant_income": FieldSpec("f.card_merchant_income", "售卡商家收入", "numeric"),
}


class QueryBuilder:
    """
    SQL 查询构建器

    使用方式:
        builder = QueryBuilder()
        sql, params = (builder
            .select(["date", "city_name", "completed_orders"])
            .where_date(start="2026-01-01", end="2026-01-14")
            .where_city(city_id=1)
            .order_by("date", ascending=False)
            .build())
    """

    # 默认表名（直接查事实表）
    DEFAULT_TABLE = "hhdata.fact_daily_metrics"

    def __init__(self, table_name: str = None):
        self.table_name = table_name or self.DEFAULT_TABLE
        self._selected_fields: List[str] = []
        self._filters: List[Tuple[str, Any]] = []
        self._order_field: Optional[str] = None
        self._order_ascending: bool = False
        self._limit: Optional[int] = None

    def select(self, fields: List[str]) -> "QueryBuilder":
        """
        选择要查询的字段

        Args:
            fields: 字段名列表，如 ["date", "city_name", "completed_orders"]

        Returns:
            self

        Raises:
            ValueError: 字段不在标准字段列表中
        """
        for f in fields:
            if f not in STANDARD_FIELDS:
                raise ValueError(f"Unknown field: {f}. Available: {list(STANDARD_FIELDS.keys())}")

        self._selected_fields = fields
        return self

    def select_all(self) -> "QueryBuilder":
        """选择所有标准字段"""
        self._selected_fields = list(STANDARD_FIELDS.keys())
        return self

    def where_date(self, start: Optional[str] = None,
                   end: Optional[str] = None,
                   field: str = "date") -> "QueryBuilder":
        """
        添加日期过滤条件

        Args:
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            field: 日期字段名，默认 date

        Returns:
            self
        """
        if start:
            self._filters.append((f"f.{field} >= %s", start))
        if end:
            self._filters.append((f"f.{field} <= %s", end))
        return self

    def where_city(self, city_id: Optional[int] = None,
                   city_name: Optional[str] = None) -> "QueryBuilder":
        """添加城市过滤条件"""
        if city_id is not None:
            self._filters.append(("f.city_id = %s", city_id))
        if city_name:
            self._filters.append(("c.city_name = %s", city_name))
        return self

    def where_brand(self, brand_id: Optional[int] = None,
                    brand_name: Optional[str] = None) -> "QueryBuilder":
        """添加品牌过滤条件"""
        if brand_id is not None:
            self._filters.append(("f.brand_id = %s", brand_id))
        if brand_name:
            self._filters.append(("b.brand_name = %s", brand_name))
        return self

    def where_custom(self, condition: str, value: Any) -> "QueryBuilder":
        """
        添加自定义过滤条件

        Args:
            condition: SQL 条件表达式（包含 %s 占位符）
            value: 参数值

        Returns:
            self
        """
        self._filters.append((condition, value))
        return self

    def order_by(self, field: str, ascending: bool = False) -> "QueryBuilder":
        """
        设置排序

        Args:
            field: 排序字段
            ascending: 是否升序，默认降序

        Returns:
            self
        """
        self._order_field = field
        self._order_ascending = ascending
        return self

    def limit(self, n: int) -> "QueryBuilder":
        """限制返回行数"""
        self._limit = n
        return self

    def build(self) -> Tuple[str, List[Any]]:
        """
        构建 SQL 查询

        Returns:
            (sql_string, params_list)
        """
        if not self._selected_fields:
            self._selected_fields = list(STANDARD_FIELDS.keys())

        # 构建 SELECT 子句
        field_exprs = []
        for f in self._selected_fields:
            spec = STANDARD_FIELDS[f]
            field_exprs.append(f"{spec.db_name} as {f}")

        # 判断是否需要 JOIN 维度表
        needs_city = any(
            STANDARD_FIELDS[f].db_name.startswith("c.") for f in self._selected_fields
        ) or any(cond.startswith("c.") for cond, _ in self._filters)

        needs_brand = any(
            STANDARD_FIELDS[f].db_name.startswith("b.") for f in self._selected_fields
        ) or any(cond.startswith("b.") for cond, _ in self._filters)

        # 组装 SQL
        sql = f"SELECT {', '.join(field_exprs)} FROM {self.table_name} f"
        if needs_city:
            sql += " JOIN mabiao.dim_cities c ON f.city_id = c.city_id"
        if needs_brand:
            sql += " JOIN mabiao.dim_brands b ON f.brand_id = b.brand_id"

        sql += " WHERE 1=1"
        params = []

        for condition, value in self._filters:
            sql += f" AND {condition}"
            params.append(value)

        if self._order_field:
            direction = "ASC" if self._order_ascending else "DESC"
            order_spec = STANDARD_FIELDS.get(self._order_field)
            order_expr = order_spec.db_name if order_spec else f"f.{self._order_field}"
            sql += f" ORDER BY {order_expr} {direction}"

        if self._limit:
            sql += f" LIMIT {self._limit}"

        return sql, params

    def build_count(self) -> Tuple[str, List[Any]]:
        """
        构建计数查询（用于分页）

        Returns:
            (count_sql, params)
        """
        sql, params = self.build()
        count_sql = f"SELECT COUNT(*) FROM ({sql}) as subquery"
        return count_sql, params


# 便捷函数
def build_simple_query(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    city_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    fields: Optional[List[str]] = None,
    order: str = "date",
    ascending: bool = False,
) -> Tuple[str, List[Any]]:
    """
    构建简单查询的便捷函数

    Args:
        start_date: 开始日期
        end_date: 结束日期
        city_id: 城市ID
        brand_id: 品牌ID
        fields: 要查询的字段列表
        order: 排序字段
        ascending: 是否升序

    Returns:
        (sql, params)
    """
    builder = QueryBuilder()

    if fields:
        builder.select(fields)
    else:
        builder.select_all()

    builder.where_date(start=start_date, end=end_date)

    if city_id is not None:
        builder.where_city(city_id=city_id)

    if brand_id is not None:
        builder.where_brand(brand_id=brand_id)

    builder.order_by(order, ascending=ascending)

    return builder.build()
