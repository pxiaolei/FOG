"""
日报配置：对接人、指标定义、阈值、字段列表、飞书普通表格发布
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

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

from lxx_share.metric_definitions import daily_report_metric_definitions
from lxx_share.cache_utils import (
    load_dailyreport_cache as _load_dailyreport_cache_file,
    save_dailyreport_cache as _save_dailyreport_cache_file,
)


def _find_project_root() -> Path:
    """查找 p-fog 项目根目录（含 .workbuddy/ 和 config/）。"""
    for candidate in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
        if (candidate / ".workbuddy").exists() and (candidate / "config").exists():
            return candidate
    return Path(__file__).resolve().parents[4]


_PROJECT_ROOT = _find_project_root()


def _load_fog_config() -> dict:
    """读取项目统一配置。"""
    path = _PROJECT_ROOT / "config" / "fog_config.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


_FOG_CONFIG = _load_fog_config()


def _config_section(name: str) -> dict:
    config = _FOG_CONFIG.get(name, {})
    return config if isinstance(config, dict) else {}


def _dailyreport_config() -> dict:
    return _config_section("lx_dapanribao")


def _resolve_project_path(value: str, default: str) -> str:
    raw = value or default
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path)
    return str(_PROJECT_ROOT / path)


_DAILYREPORT_CONFIG = _dailyreport_config()


def _dailyreport_value(key: str, default):
    if key in _DAILYREPORT_CONFIG:
        return _DAILYREPORT_CONFIG[key]
    return default


def _string_value(value) -> str:
    return str(value or "").strip()


def _extract_folder_token(url_or_token: str) -> str:
    value = _string_value(url_or_token)
    match = re.search(r"/drive/folder/([^/?#]+)", value)
    return match.group(1) if match else value


def _root_folder_from_nongfu(contact_person: str) -> str:
    nongfu = _config_section("lx_nongfu")
    operator_doc = nongfu.get("operator_doc", {})
    if not isinstance(operator_doc, dict):
        return ""

    mapping = operator_doc.get("contact_person_root_folders")
    if contact_person and isinstance(mapping, dict):
        configured = mapping.get(contact_person)
        if isinstance(configured, str):
            return configured.strip()
        if isinstance(configured, dict):
            return _string_value(configured.get("url") or configured.get("token"))

    return _string_value(
        operator_doc.get("operator_root_folder_url")
        or operator_doc.get("operator_root_folder_token")
    )


def resolve_feishu_root_folder(contact_person: str = "") -> tuple[str, str, str]:
    """解析日报发布根目录，优先日报配置，其次继承 lx_nongfu 运营主体根目录。"""
    explicit_url = _string_value(_dailyreport_value("feishu_root_folder_url", ""))
    explicit_token = _string_value(_dailyreport_value("feishu_root_folder_token", ""))
    if explicit_url or explicit_token:
        return explicit_url, explicit_token or _extract_folder_token(explicit_url), "lx_dapanribao"

    inherited = _root_folder_from_nongfu(contact_person or DEFAULT_PERSON)
    if inherited:
        inherited_url = inherited if inherited.startswith("http") else ""
        return inherited_url, _extract_folder_token(inherited), "lx_nongfu.operator_doc"

    return "", "", ""

# ── 对接人配置（同事改为自己的对接人名字）──
DEFAULT_PERSON = _dailyreport_value("default_person", "")

# ── 飞书普通表格发布配置 ──
DEFAULT_REPORT_TITLE_SUFFIX = (
    _dailyreport_value("title_suffix", "大盘数据日报") or "大盘数据日报"
)

PUBLISH_BACKEND = _dailyreport_value("publish_backend", "lx-feishudocs") or "lx-feishudocs"
FEISHU_ROOT_FOLDER_URL, FEISHU_ROOT_FOLDER_TOKEN, FEISHU_ROOT_FOLDER_SOURCE = (
    resolve_feishu_root_folder(DEFAULT_PERSON)
)
OPERATOR_FOLDER_NAME_TEMPLATE = (
    _dailyreport_value("operator_folder_name_template", "{operator}-运营主体") or "{operator}-运营主体"
)
REPORT_TITLE_TEMPLATE = (
    _dailyreport_value("report_title_template", "")
    or "{operator}-大盘数据日报"
)
OPERATOR_FOLDER_OVERRIDES = _DAILYREPORT_CONFIG.get("operator_folder_overrides", {})
if not isinstance(OPERATOR_FOLDER_OVERRIDES, dict):
    OPERATOR_FOLDER_OVERRIDES = {}
REPORT_TITLE_OVERRIDES = _DAILYREPORT_CONFIG.get("report_title_overrides", {})
if not isinstance(REPORT_TITLE_OVERRIDES, dict):
    REPORT_TITLE_OVERRIDES = {}

# 日报表格的 spreadsheet token / sheet_id 可独立存储在 dailyreport_cache.json 中
DAILYREPORT_CACHE_PATH = (
    _skills_dir / "lx-dapanribao" / "assets" / "dailyreport_cache.json"
)

# 本地输出目录
DEFAULT_OUTPUT_DIR = _resolve_project_path(
    _DAILYREPORT_CONFIG.get("output_dir", ""),
    "workspace/03数据报表/日报",
)

MISSING_DISPLAY_VALUE = "-"

# ── 指标类型 ──
MetricType = Literal["volume", "rate"]


@dataclass
class MetricDef:
    key: str
    name: str
    type: MetricType
    higher_is_better: bool = True


# ── 17 个日报指标 ──
METRICS: list[MetricDef] = [
    MetricDef(m.key, m.name, m.metric_type, m.higher_is_better)
    for m in daily_report_metric_definitions()
]

# ── 5 个子列 ──
SUB_COLUMNS = ["当日值", "环比", "同比", "城市环比", "城市同比"]

# ── 异动阈值 ──
ANOMALY_THRESHOLD_VOLUME = float(
    _DAILYREPORT_CONFIG.get("anomaly_threshold_volume", 0.05)
)
ANOMALY_THRESHOLD_RATE = float(
    _DAILYREPORT_CONFIG.get("anomaly_threshold_rate", 0.02)
)

# ── 最小绝对值门槛（小基数指标波动大，低于门槛不检测异动）──
MIN_ABSOLUTE_FOR_ANOMALY = {
    "completed_orders": 10,
    "placed_orders": 10,
    "gmv": 1000,
    "online_drivers": 5,
    "online_duration_hours": 10,
    "first_completed_drivers": 3,
    "avg_orders_per_driver": 0,
    "tph": 0,
    "unit_price": 0,
}

# ── yidongfenxi 深挖 ──
DEEP_ANALYSIS_TOP_K = int(_DAILYREPORT_CONFIG.get("deep_analysis_top_k", 5))

# ── 从 hhdata 查询的原始字段 ──
RAW_FIELDS = [
    "date", "city_id", "city_name", "brand_id", "brand_name",
    "placed_orders", "completed_orders", "online_drivers",
    "online_duration_hours", "first_completed_drivers", "gmv",
    "merchant_b_subsidy", "brand_commission", "card_merchant_income",
    "completed_drivers", "cancelled_by_driver", "answered_orders",
]


def load_dailyreport_cache() -> dict:
    """加载日报表格缓存。"""
    return _load_dailyreport_cache_file(DAILYREPORT_CACHE_PATH)


def save_dailyreport_cache(cache: dict):
    """保存日报表格缓存。"""
    _save_dailyreport_cache_file(DAILYREPORT_CACHE_PATH, cache)
