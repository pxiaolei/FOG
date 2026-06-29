"""
异动检测模块

双层机制：
1. 阈值偏离检测：只看完单同比，品牌变化 vs 城市大盘，偏离达到 5pp 标色
2. 异动分析：对完单同比异常调用 lx-yidongfenxi 做方向一致的根因分析
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import pandas as pd

from config import (
    METRICS, ANOMALY_THRESHOLD_VOLUME, ANOMALY_THRESHOLD_RATE,
    DEEP_ANALYSIS_TOP_K, MIN_ABSOLUTE_FOR_ANOMALY,
)


@dataclass
class AnomalyResult:
    """单个异动记录"""
    operator: str
    brand: str
    city: str
    brand_id: Optional[int]
    city_id: Optional[int]
    metric_key: str
    metric_name: str
    metric_type: str      # "volume" or "rate"
    direction: Literal["positive", "negative"]
    dimension: Literal["mom", "yoy"]
    brand_change: float
    city_change: float
    signed_deviation: float
    deviation: float

    def _fmt(self, val: float) -> str:
        """格式化变化值：量值用 %，率值用 pp"""
        if self.metric_type == "rate":
            sign = "+" if val > 0 else ""
            return f"{sign}{val * 100:.1f}pp"
        else:
            sign = "+" if val > 0 else ""
            return f"{sign}{val * 100:.1f}%"

    def summary(self) -> str:
        arrow = "↑" if self.brand_change > 0 else "↓" if self.brand_change < 0 else "→"
        dim_name = "环比" if self.dimension == "mom" else "同比"
        relative = "优于大盘" if self.direction == "positive" else "劣于大盘"
        return (f"{self.brand}-{self.city} {self.metric_name} {dim_name} {arrow}"
                f" 品牌{self._fmt(self.brand_change)}"
                f" 城市{self._fmt(self.city_change)}"
                f" 偏离{self._fmt(self.signed_deviation)}"
                f"（{relative}）")


def detect_anomalies(report_df: pd.DataFrame) -> List[AnomalyResult]:
    """
    阈值偏离检测。

    日报只检测完单同比异动：
    |品牌完单同比 - 城市大盘完单同比| >= 5pp。

    Returns:
        异动列表，按偏离度降序排列
    """
    if report_df.empty:
        return []

    anomalies: List[AnomalyResult] = []

    for _, row in report_df.iterrows():
        op = row.get("运营主体", "")
        brand = row.get("品牌", "")
        city = row.get("城市", "")
        brand_id = _safe_int(row.get("brand_id"))
        city_id = _safe_int(row.get("city_id"))

        for m in METRICS:
            if m.key != "completed_order_count":
                continue

            threshold = ANOMALY_THRESHOLD_VOLUME

            for dim, dim_label in [("yoy", "同比")]:
                brand_col = f"{m.key}_{dim_label}"
                city_col = f"{m.key}_城市{dim_label}"

                brand_val = row.get(brand_col)
                city_val = row.get(city_col)

                if brand_val is None or city_val is None:
                    continue
                if pd.isna(brand_val) or pd.isna(city_val):
                    continue

                # 小基数过滤：量值指标的当日值低于门槛，跳过
                min_abs = MIN_ABSOLUTE_FOR_ANOMALY.get(m.key, 0)
                if m.type == "volume" and min_abs > 0:
                    today_val = row.get(f"{m.key}_当日值")
                    if today_val is None or pd.isna(today_val) or today_val < min_abs:
                        continue

                signed_deviation = brand_val - city_val
                deviation = abs(signed_deviation)
                if deviation >= threshold:
                    is_better = signed_deviation > 0
                    direction = "positive" if is_better else "negative"
                    anomalies.append(AnomalyResult(
                        operator=op,
                        brand=brand,
                        city=city,
                        brand_id=brand_id,
                        city_id=city_id,
                        metric_key=m.key,
                        metric_name=m.name,
                        metric_type=m.type,
                        direction=direction,
                        dimension=dim,
                        brand_change=brand_val,
                        city_change=city_val,
                        signed_deviation=signed_deviation,
                        deviation=deviation,
                    ))

    anomalies.sort(key=lambda a: a.deviation, reverse=True)
    return anomalies


def format_anomaly_summary(anomalies: List[AnomalyResult], top_k: int = 10) -> str:
    """
    生成异动摘要文案（阈值检测层）。

    Args:
        anomalies: 异动列表
        top_k: 正/负各取 Top K

    Returns:
        格式化的 Markdown 文本
    """
    if not anomalies:
        return "✅ 未检测到显著异动"

    negative = [a for a in anomalies if a.direction == "negative"][:top_k]
    positive = [a for a in anomalies if a.direction == "positive"][:top_k]

    lines = ["📊 **异动分析**\n"]

    if negative:
        lines.append("⚠️ **劣于大盘（需关注）**：")
        for a in negative:
            lines.append(f"  - {a.summary()}")
        lines.append("")

    if positive:
        lines.append("✅ **优于大盘（正面表现）**：")
        for a in positive:
            lines.append(f"  - {a.summary()}")

    return "\n".join(lines)


def get_anomaly_cell_map(
    anomalies: List[AnomalyResult],
    report_df: pd.DataFrame,
) -> dict:
    """
    生成异动单元格标色映射。

    Returns:
        {(row_idx, col_name): "positive"|"negative"}
        用于 feishu_publisher 发布计划标记
    """
    cell_map = {}

    for a in anomalies:
        # 找到对应行
        mask = ((report_df["品牌"] == a.brand) &
                (report_df["城市"] == a.city) &
                (report_df["运营主体"] == a.operator))
        matches = report_df[mask]
        if matches.empty:
            continue
        row_idx = matches.index[0]

        dim_label = "环比" if a.dimension == "mom" else "同比"
        col_name = f"{a.metric_key}_{dim_label}"
        city_col_name = f"{a.metric_key}_城市{dim_label}"

        # 标品牌列和城市列
        if col_name in report_df.columns:
            cell_map[(row_idx, col_name)] = a.direction
        if city_col_name in report_df.columns:
            cell_map[(row_idx, city_col_name)] = a.direction

    return cell_map


def deep_analyze_top_anomalies(
    anomalies: List[AnomalyResult],
    today: str,
    top_k: int = DEEP_ANALYSIS_TOP_K,
) -> str:
    """
    对 Top K 异常调用 lx-yidongfenxi 做异动分析。

    日报归因只聚焦完单同比异动。完单归因逻辑由 lx-yidongfenxi 基于
    hhdata__fact_daily_metrics 和 hhdata__fact_gongbu_strategy 计算，避免
    日报侧复制业务规则。

    Returns:
        深度分析文案，失败时返回空字符串
    """
    if not anomalies:
        return ""

    analyzable = [a for a in anomalies if a.metric_key == "completed_order_count" and a.dimension == "yoy"]

    if not analyzable:
        return ""

    try:
        funcs = _load_yidongfenxi_functions()
    except Exception as exc:
        return ""  # lx-yidongfenxi 不可用，静默跳过

    lines = ["异动分析"]

    groups = [
        ("劣于大盘", [a for a in analyzable if a.direction == "negative"][:top_k]),
        ("优于大盘", [a for a in analyzable if a.direction == "positive"][:top_k]),
    ]

    for title, group in groups:
        if not group:
            continue
        lines.append(f"{title}：")
        for a in group:
            lines.append(_format_completed_anomaly_line(a))

            if a.city_id is None or a.brand_id is None:
                lines.append("  无法归因：缺少 city_id/brand_id")
                continue

            try:
                result = _run_deep_analysis(funcs, a, "yoy_sameday", today)
                lines.extend(_format_dailyreport_completed_result(result))
            except Exception as e:
                lines.append(f"  分析失败: {e}")
        lines.append("")

    return "\n".join(lines)


def _format_completed_anomaly_line(anomaly: AnomalyResult) -> str:
    return (
        f"- {anomaly.brand}-{anomaly.city}：完单同比"
        f"品牌{_fmt_pct(anomaly.brand_change)}，"
        f"城市大盘{_fmt_pct(anomaly.city_change)}，"
        f"偏离{_fmt_pp(anomaly.signed_deviation)}"
    )


def _format_dailyreport_completed_result(result: Dict[str, Any]) -> List[str]:
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else result

    if result.get("errors"):
        return ["  " + "；".join(str(e) for e in result["errors"])]
    if analysis.get("错误"):
        return [f"  {analysis['错误']}"]

    reasons = analysis.get("可能原因") or []
    if isinstance(reasons, list) and reasons:
        return ["  原因：" + "；".join(str(item) for item in reasons)]
    if isinstance(reasons, str) and reasons:
        return [f"  原因：{reasons}"]

    conclusion = analysis.get("结论")
    if conclusion:
        return [f"  结论：{conclusion}"]
    return ["  未返回可展示结论"]


def _deep_analysis_kind(metric_key: str) -> Optional[str]:
    mapping = {
        "completed_order_count": "completed",
        "gmv": "completed",
        "passenger_order_count": "order",
        "online_driver_count": "driver",
        "response_rate": "funnel",
        "completion_rate": "funnel",
        "merchant_b_subsidy_rate": "subsidy",
    }
    return mapping.get(metric_key)


def _run_deep_analysis(
    funcs: Dict[str, Any],
    anomaly: AnomalyResult,
    comparison: str,
    today: str,
) -> Dict[str, Any]:
    kind = _deep_analysis_kind(anomaly.metric_key)
    common = {
        "level": "brand_city",
        "comparison_type": comparison,
        "current_end_date": today,
        "city_id": anomaly.city_id,
        "brand_id": anomaly.brand_id,
    }

    if kind == "completed":
        return funcs["completed"](metric=anomaly.metric_key, **common)
    if kind == "order":
        return funcs["order"](**common)
    if kind == "driver":
        return funcs["driver"](**common)

    period = funcs["build_period"](comparison, today)
    if kind == "funnel":
        return funcs["funnel"](
            anomaly.city_id,
            anomaly.brand_id,
            period.current_start,
            period.current_end,
            period.baseline_start,
            period.baseline_end,
        )
    if kind == "subsidy":
        return funcs["subsidy"](
            anomaly.city_id,
            anomaly.brand_id,
            period.current_start,
            period.current_end,
            period.baseline_start,
            period.baseline_end,
        )

    return {"conclusion": "该指标暂无深度分析器"}


def _load_yidongfenxi_functions() -> Dict[str, Any]:
    scripts_dir = _resolve_sibling_skill_scripts("lx-yidongfenxi")
    skills_dir = scripts_dir.parent.parent
    zhibiao_dir = skills_dir / "lx-zhibiaojisuan" / "scripts"

    for path in (zhibiao_dir, scripts_dir, skills_dir):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    existing_core = sys.modules.get("core_analyzer")
    if existing_core is not None and not _module_under(existing_core, scripts_dir):
        sys.modules.pop("core_analyzer", None)

    existing_loader = sys.modules.get("data_loader")
    restore_loader = None
    if existing_loader is not None and not _module_under(existing_loader, zhibiao_dir):
        restore_loader = existing_loader
        sys.modules.pop("data_loader", None)

    try:
        from core_analyzer import (
            analyze_completed_order_anomaly,
            analyze_order_fluctuation,
            analyze_driver_churn,
            analyze_funnel,
            analyze_subsidy_rate,
            build_period,
        )
    finally:
        if restore_loader is not None:
            sys.modules["data_loader"] = restore_loader

    return {
        "completed": analyze_completed_order_anomaly,
        "order": analyze_order_fluctuation,
        "driver": analyze_driver_churn,
        "funnel": analyze_funnel,
        "subsidy": analyze_subsidy_rate,
        "build_period": build_period,
    }


def _resolve_sibling_skill_scripts(skill_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / skill_name / "scripts"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未找到 {skill_name}/scripts")


def _module_under(module: Any, directory: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        Path(module_file).resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _safe_int(value) -> Optional[int]:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt_number(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f}%"


def _fmt_pp(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f}pp"
