---
name: lxx_share
description: LX 共享基础模块，提供数据库连接、指标计算、公司库码表映射、阈值配置、Excel工具、腾讯文档API等通用能力，供所有 LX 业务 Skill（lx-zhutichaibiao、lx-dapanribao 等）共用。
trigger_keywords: []
location: project
---

# lxx_share — LX 共享基础模块

## 定位

本项目所有 LX 业务 Skill 的共享 Python 库，不面向用户直接触发，由其他 Skill 通过 `import` 加载使用。

## 模块清单

| 模块 | 职责 |
|------|------|
| `database.py` | PostgreSQL 连接管理（DatabaseConnector） |
| `hhdata_metrics.py` | 17 个日报指标计算公式、环比/同比函数 |
| `metric_definitions.py` | 业务指标定义（MetricDefinition、FieldDefinition） |
| `excel_utils.py` | 公司库码表映射加载、列检测、样式复制 |
| `tdocs_api.py` | 腾讯文档 Open API V3 封装（OAuth + batchUpdate + Drive V2） |
| `cache_utils.py` | 跨 Skill 缓存版本与结构校验 |
| `config.py` | 阈值配置管理（异动/趋势/数据质量） |
| `utils.py` | 日志记录器 + Config 配置读取 + 路径初始化辅助 |
| `formatters.py` | 文本报告格式化 |
| `query_builder.py` | SQL 查询构建器 |

## 使用方式

由其他 Skill 脚本通过 sys.path 引入（推荐使用内联路径查找函数）：

```python
def _find_skills_dir():
    from pathlib import Path
    for p in Path(__file__).resolve().parents:
        if (p / "lxx_share").is_dir():
            return p
    return Path(__file__).resolve().parents[2]

_skills_dir = _find_skills_dir()
import sys
if str(_skills_dir) not in sys.path:
    sys.path.insert(0, str(_skills_dir))

from lxx_share import DatabaseConnector
from lxx_share.hhdata_metrics import compute_derived_metrics
from lxx_share.metric_definitions import daily_report_metric_definitions
```

## 配置依赖

- 数据库配置：项目根目录 `config/fog_config.yaml` 的 `database` 段
- 腾讯文档 API 凭证：项目根目录 `config/fog_config.yaml` 的 `lx_txwendang.tdocs.openapi` 段
- 码表：通过 `lx_shujuku` 查询 dataReporting `operator_brand`，不读取本地 Excel
- 阈值配置：可选 `config/thresholds.yaml`，默认使用内置值

## 注意事项

- `metric_definitions.py` 已去除 lxx_ops 外部依赖，自包含
- 各模块内部使用 `from lxx_share.xxx import` 相对导入，需保证 lxx_share 目录在 sys.path 中
