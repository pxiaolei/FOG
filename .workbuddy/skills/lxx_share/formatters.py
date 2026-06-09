"""
统一报告格式化模块

提供一致的报告格式，确保：
1. 统一的边框样式（60 字符）
2. 统一的 emoji 使用
3. 统一的数据呈现方式
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ReportSection:
    """报告区块定义"""
    title: str
    emoji: str
    content: List[str]
    indent: int = 2


class BaseFormatter(ABC):
    """
    报告格式化器基类

    子类需实现:
    - get_sections(): 返回报告区块列表
    - get_title(): 返回报告标题
    - get_title_emoji(): 返回标题 emoji
    """

    BORDER_CHAR = "="
    BORDER_LENGTH = 60

    def format(self, data: Dict[str, Any]) -> str:
        """
        格式化数据为报告字符串

        Args:
            data: 分析结果字典

        Returns:
            格式化的报告字符串
        """
        lines = []

        lines.append(self.BORDER_CHAR * self.BORDER_LENGTH)
        lines.append(f"{self.get_title_emoji()} {self.get_title()}")
        lines.append(self.BORDER_CHAR * self.BORDER_LENGTH)
        lines.append("")

        for section in self.get_sections(data):
            lines.append(f"{section.emoji} {section.title}")
            for line in section.content:
                lines.append(" " * section.indent + line)
            lines.append("")

        lines.append(self.BORDER_CHAR * self.BORDER_LENGTH)

        return "\n".join(lines)

    @abstractmethod
    def get_title(self) -> str:
        """获取报告标题"""
        pass

    @abstractmethod
    def get_title_emoji(self) -> str:
        """获取标题 emoji"""
        pass

    @abstractmethod
    def get_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        """获取报告区块"""
        pass


class MetricsFormatter(BaseFormatter):
    """指标报告格式化器"""

    def get_title(self) -> str:
        return "LX 平台核心指标报告"

    def get_title_emoji(self) -> str:
        return "📊"

    def get_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        sections = []

        # 数据概况
        if "overview" in data:
            info = data["overview"]
            sections.append(ReportSection(
                title="数据概况",
                emoji="📋",
                content=[
                    f"总记录数: {info.get('total_rows', 0):,}",
                    f"日期范围: {info.get('date_range', 'N/A')}",
                ]
            ))

        # 订单漏斗
        if "funnel" in data:
            funnel = data["funnel"]
            content = []
            if "total" in funnel:
                total = funnel["total"]
                content.extend([
                    f"发单量: {total.get('placed_orders', 0):,}",
                    f"→ 播单量: {total.get('broadcast_orders', 0):,}",
                    f"→ 匹配量: {total.get('matched_orders', 0):,}",
                    f"→ 应答量: {total.get('answered_orders', 0):,}",
                    f"→ 完单数: {total.get('completed_orders', 0):,}",
                ])
            if "rates" in funnel:
                content.append("")
                content.append("转化率:")
                for key, value in funnel["rates"].items():
                    content.append(f"  {key}: {value:.2%}")
            sections.append(ReportSection(
                title="订单漏斗",
                emoji="🔻",
                content=content
            ))

        # 财务指标
        if "financial" in data:
            finance = data["financial"]
            content = []
            for key, value in finance.items():
                content.append(f"{key}: {value:,.2f}" if isinstance(value, float) else f"{key}: {value}")
            sections.append(ReportSection(
                title="财务指标",
                emoji="💰",
                content=content
            ))

        # 司机效率
        if "driver" in data:
            driver = data["driver"]
            content = []
            for key, value in driver.items():
                if isinstance(value, float):
                    if "率" in key:
                        content.append(f"{key}: {value:.2%}")
                    elif "TPH" in key or "TSH" in key:
                        content.append(f"{key}: {value:.2f}")
                    else:
                        content.append(f"{key}: {value:,.2f}")
                else:
                    content.append(f"{key}: {value}")
            sections.append(ReportSection(
                title="司机效率",
                emoji="🚗",
                content=content
            ))

        return sections


class TrendFormatter(BaseFormatter):
    """趋势分析报告格式化器"""

    def get_title(self) -> str:
        return "趋势分析报告"

    def get_title_emoji(self) -> str:
        return "📈"

    def get_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        sections = []

        # 数据概况
        if "overview" in data:
            info = data["overview"]
            sections.append(ReportSection(
                title="数据概况",
                emoji="📋",
                content=[
                    f"总记录数: {info.get('total_rows', 0):,}",
                    f"日期范围: {info.get('date_range', 'N/A')}",
                    f"天数: {info.get('days', 0)}",
                ]
            ))

        # 趋势方向
        if "trend" in data:
            trend = data["trend"]
            if "message" not in trend:
                sections.append(ReportSection(
                    title="趋势方向",
                    emoji="🔍",
                    content=[
                        f"趋势: {trend.get('trend_name', 'unknown')}",
                        f"当前值: {trend.get('current_value', 0):,}",
                        f"起始值: {trend.get('start_value', 0):,}",
                        f"变化: {trend.get('change', 0):+,}",
                        f"平均变化率: {trend.get('avg_change_rate', 0):.2f}%",
                    ]
                ))

        # 环比分析
        if "mom" in data:
            mom = data["mom"]
            if "message" not in mom:
                sections.append(ReportSection(
                    title="环比分析",
                    emoji="📊",
                    content=[
                        f"平均增长率: {mom.get('avg_growth_rate', 0):.2f}%",
                        f"最高增长率: {mom.get('max_growth_rate', 0):.2f}%",
                        f"最低增长率: {mom.get('min_growth_rate', 0):.2f}%",
                        f"增长天数: {mom.get('growth_days', 0)} 天",
                        f"下降天数: {mom.get('decline_days', 0)} 天",
                    ]
                ))

        return sections


class QualityFormatter(BaseFormatter):
    """数据质量报告格式化器"""

    def get_title(self) -> str:
        return "数据质量报告"

    def get_title_emoji(self) -> str:
        return "🔍"

    def get_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        sections = []

        # 检查结果汇总
        checks = data.get("checks", {})
        for check_name, check_result in checks.items():
            status = "✅" if check_result.get("pass", False) else "⚠️"
            sections.append(ReportSection(
                title=check_name.capitalize(),
                emoji=status,
                content=[check_result.get("message", "")]
            ))

        # 错误和警告
        if data.get("errors"):
            sections.append(ReportSection(
                title="错误",
                emoji="❌",
                content=data["errors"]
            ))

        if data.get("warnings"):
            sections.append(ReportSection(
                title="警告",
                emoji="⚠️",
                content=data["warnings"]
            ))

        return sections


class AnomalyFormatter(BaseFormatter):
    """异动分析报告格式化器"""

    def get_title(self) -> str:
        return "数据异动分析报告"

    def get_title_emoji(self) -> str:
        return "🚨"

    def get_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        sections = []

        # 基本信息
        if "info" in data:
            info = data["info"]
            sections.append(ReportSection(
                title="基本信息",
                emoji="📋",
                content=[
                    f"分析对象: {info.get('target', 'N/A')}",
                    f"时间周期: {info.get('period', 'N/A')}",
                ]
            ))

        # 涨跌幅检测
        if "change" in data:
            change = data["change"]
            content = [
                f"当前值: {change.get('current', 0):,}",
                f"基准值: {change.get('baseline', 0):,}",
                f"涨跌幅: {change.get('change_rate', 0):.2%}",
                f"是否异动: {'是' if change.get('is_anomaly', False) else '否'}",
            ]
            sections.append(ReportSection(
                title="涨跌幅检测",
                emoji="📈",
                content=content
            ))

        # 大盘对比
        if "benchmark" in data:
            bench = data["benchmark"]
            content = [
                f"大盘涨跌幅: {bench.get('benchmark_rate', 0):.2%}",
                f"与大盘差异: {bench.get('diff_rate', 0):.2%}",
            ]
            sections.append(ReportSection(
                title="大盘对比",
                emoji="🌐",
                content=content
            ))

        # 分析结论
        if "conclusion" in data:
            sections.append(ReportSection(
                title="分析结论",
                emoji="🔎",
                content=[data["conclusion"]]
            ))

        # 可能原因
        if data.get("reasons"):
            sections.append(ReportSection(
                title="可能原因",
                emoji="💡",
                content=data["reasons"]
            ))

        return sections
