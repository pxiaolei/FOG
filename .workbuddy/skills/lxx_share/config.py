"""
统一阈值配置模块

支持：
1. YAML 配置文件
2. 代码默认值
3. 运行时动态调整
4. 按 skill 类型分组
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from lxx_share.utils import get_logger

logger = get_logger("lxx_share.config")



class ThresholdConfig:
    """
    统一阈值配置管理器

    使用方式:
        # 默认配置
        config = ThresholdConfig()
        threshold = config.get('anomaly', 'change_threshold', 0.05)

        # 自定义配置文件
        config = ThresholdConfig('/path/to/thresholds.yaml')

        # 运行时调整
        config.set('anomaly', 'change_threshold', 0.10)

        # 导出配置
        config.save('/path/to/thresholds.yaml')
    """

    DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = {
        "data_quality": {
            "zero_value_percent": 50.0,       # 零值比例阈值
            "gmv_outlier_multiplier": 10.0,    # GMV 异常倍数
            "missing_value_percent": 5.0,      # 缺失值比例阈值
        },
        "anomaly": {
            "change_threshold": 0.05,          # 5% 涨跌幅阈值
            "benchmark_threshold": 0.02,       # 2% 大盘差异阈值
            "drop_threshold": 0.30,             # 30% 大幅下降阈值
            "rise_threshold": 0.50,              # 50% 大幅上升阈值
            "zero_threshold": 0.50,             # 50% 归零阈值
        },
        "trend": {
            "min_data_points": 7,              # 最少数据点
            "moving_average_window": 7,         # 移动平均窗口
            "forecast_periods": 7,              # 预测天数
        },
        "visualization": {
            "max_categories": 20,              # 最大分类数
            "default_figsize_x": 14,
            "default_figsize_y": 6,
        }
    }

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化阈值配置

        Args:
            config_file: YAML 配置文件路径
        """
        self._thresholds: Dict[str, Dict[str, Any]] = {}
        self._config_file = config_file
        self._load_defaults()

        if config_file:
            self._load_from_file(config_file)
        else:
            # 尝试从默认位置加载
            project_root = Path(__file__).parent.parent.parent.parent
            default_path = project_root / "config" / "thresholds.yaml"
            if default_path.exists():
                self._load_from_file(str(default_path))

    def _load_defaults(self):
        """加载默认阈值"""
        self._thresholds = {
            category: values.copy()
            for category, values in self.DEFAULT_THRESHOLDS.items()
        }

    def _load_from_file(self, config_file: str):
        """从 YAML 文件加载阈值"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            for category, values in data.items():
                if category in self._thresholds and isinstance(values, dict):
                    self._thresholds[category].update(values)
                else:
                    self._thresholds[category] = values

            logger.info(f"✅ 从 {config_file} 加载阈值配置")
        except Exception as e:
            logger.warning(f"⚠️ 加载阈值配置失败: {e}，使用默认值")

    def get(self, category: str, key: str, default: Optional[Any] = None) -> Any:
        """
        获取阈值

        Args:
            category: 阈值分类（如 'anomaly', 'data_quality'）
            key: 阈值键名
            default: 默认值

        Returns:
            阈值值
        """
        return self._thresholds.get(category, {}).get(key, default)

    def set(self, category: str, key: str, value: Any):
        """
        设置阈值（运行时修改）

        Args:
            category: 阈值分类
            key: 阈值键名
            value: 阈值值
        """
        if category not in self._thresholds:
            self._thresholds[category] = {}
        self._thresholds[category][key] = value

    def get_category(self, category: str) -> Dict[str, Any]:
        """获取整个分类的阈值"""
        return self._thresholds.get(category, {}).copy()

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """导出所有阈值为字典"""
        return {k: v.copy() for k, v in self._thresholds.items()}

    def save(self, config_file: Optional[str] = None):
        """
        保存当前阈值到文件

        Args:
            config_file: 配置文件路径，默认使用加载时的路径
        """
        save_path = config_file or self._config_file
        if not save_path:
            raise ValueError("No config file path specified")

        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(
                self.to_dict(),
                f,
                allow_unicode=True,
                default_flow_style=False
            )
        logger.info(f"✅ 阈值配置已保存到 {save_path}")

    def reset(self):
        """重置为默认阈值"""
        self._load_defaults()
