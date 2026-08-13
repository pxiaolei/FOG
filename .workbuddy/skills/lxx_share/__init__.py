"""
LX Skill 共享基础模块。

只导出当前共享 Skill 使用的配置与 Excel 辅助能力，并采用懒加载，
避免仅导入轻量子模块时就要求 pandas/openpyxl 等运行时依赖存在。
"""

from __future__ import annotations

import os
import sys
from importlib import import_module
from typing import Any


def setup_path() -> None:
    """将 lxx_share 目录添加到 sys.path（如果尚未存在）。"""
    share_dir = os.path.dirname(os.path.abspath(__file__))
    if share_dir not in sys.path:
        sys.path.insert(0, share_dir)


_LAZY_EXPORTS = {
    "find_column": ("lxx_share.excel_utils", "find_column"),
    "find_all_columns": ("lxx_share.excel_utils", "find_all_columns"),
    "copy_cell_style": ("lxx_share.excel_utils", "copy_cell_style"),
    "detect_columns": ("lxx_share.excel_utils", "detect_columns"),
    "load_mabiao": ("lxx_share.excel_utils", "load_mabiao"),
    "load_city_operator_map": ("lxx_share.excel_utils", "load_city_operator_map"),
    "filter_by_person": ("lxx_share.excel_utils", "filter_by_person"),
    "get_split_mode_info": ("lxx_share.excel_utils", "get_split_mode_info"),
    "CITY_FIELDS": ("lxx_share.excel_utils", "CITY_FIELDS"),
    "BRAND_FIELDS": ("lxx_share.excel_utils", "BRAND_FIELDS"),
    "PERSON_FIELDS": ("lxx_share.excel_utils", "PERSON_FIELDS"),
    "OPERATOR_FIELDS": ("lxx_share.excel_utils", "OPERATOR_FIELDS"),
    "load_fog_config": ("lxx_share.fog_config", "load_fog_config"),
    "load_personal_config": ("lxx_share.fog_config", "load_personal_config"),
    "get_fog_section": ("lxx_share.fog_config", "get_section"),
    "get_personal_section": ("lxx_share.fog_config", "get_personal_section"),
    "resolve_project_path": ("lxx_share.fog_config", "resolve_project_path"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "setup_path",
    *_LAZY_EXPORTS.keys(),
]
