"""operator_brand 业务接口与码表兼容结构。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def normalize_operator_brand_row(row: dict[str, Any]) -> dict[str, str]:
    """把公司库字段统一成稳定的中英文键。"""
    operator = _clean(row.get("operator_entity") or row.get("operator") or row.get("运营主体"))
    brand = _clean(row.get("brand_name") or row.get("brand") or row.get("品牌"))
    city = _clean(row.get("city_name") or row.get("city") or row.get("城市"))
    contact_person = _clean(
        row.get("contact_person") or row.get("person") or row.get("对接人")
    )
    return {
        "operator": operator,
        "brand": brand,
        "city": city,
        "contact_person": contact_person,
        "运营主体": operator,
        "品牌": brand,
        "城市": city,
        "对接人": contact_person,
    }


def normalize_operator_brand_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """批量规范化 operator_brand 查询结果。"""
    result = []
    for row in rows:
        normalized = normalize_operator_brand_row(row)
        if normalized["operator"] and normalized["city"]:
            result.append(normalized)
    return result


def build_mabiao_mapping(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """构建兼容 lxx_share.excel_utils.load_mabiao 返回值的映射。"""
    city_to_zhuti: dict[str, set[str]] = defaultdict(set)
    brand_to_zhuti: dict[str, set[str]] = defaultdict(set)
    brand_city_to_zhuti: dict[tuple[str, str], set[str]] = defaultdict(set)
    zhuti_to_person: dict[str, set[str]] = defaultdict(set)

    all_zhuti: set[str] = set()
    all_cities: set[str] = set()
    all_brands: set[str] = set()
    all_persons: set[str] = set()

    for row in normalize_operator_brand_rows(rows):
        operator = row["operator"]
        brand = row["brand"]
        city = row["city"]
        person = row["contact_person"]

        city_to_zhuti[city].add(operator)
        all_cities.add(city)
        all_zhuti.add(operator)

        if brand:
            brand_to_zhuti[brand].add(operator)
            brand_city_to_zhuti[(brand, city)].add(operator)
            all_brands.add(brand)
        if person:
            zhuti_to_person[operator].add(person)
            all_persons.add(person)

    return {
        "city_to_zhuti": {k: sorted(v) for k, v in city_to_zhuti.items()},
        "brand_to_zhuti": {k: sorted(v) for k, v in brand_to_zhuti.items()},
        "brand_city_to_zhuti": {
            k: sorted(v) for k, v in brand_city_to_zhuti.items()
        },
        "zhuti_to_person": {k: sorted(v) for k, v in zhuti_to_person.items()},
        "all_zhuti": sorted(all_zhuti),
        "all_cities": sorted(all_cities),
        "all_brands": sorted(all_brands),
        "all_persons": sorted(all_persons),
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
