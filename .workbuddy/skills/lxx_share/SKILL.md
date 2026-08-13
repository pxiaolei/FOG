---
name: lxx_share
description: LX 共享基础模块，提供统一配置读取、公司库码表映射、Excel 工具和缓存工具，供 lx-zhutichaibiao、lx-haibao 等共享 Skill 通过 import 复用。仅作为代码依赖使用，不面向用户任务直接触发。
---

# lxx_share — LX 共享基础模块

## 定位

FOG 共享 Skill 的轻量 Python 公共库，不面向用户直接触发，由其他 Skill 通过 `import` 加载使用。

## 模块清单

| 模块 | 职责 |
|------|------|
| `excel_utils.py` | 公司库码表映射加载、列检测、样式复制 |
| `cache_utils.py` | 跨 Skill 缓存版本与结构校验 |
| `fog_config.py` | 根配置与本地个人配置的读取、缺省合并和路径解析 |
| `utils.py` | 日志记录器与路径初始化辅助 |

## 使用方式

由其他 Skill 脚本通过 sys.path 引入：

```python
from lxx_share import get_fog_section, resolve_project_path
from lxx_share.excel_utils import filter_by_person
```

## 配置依赖

- 共享配置：项目根目录 `config/fog_config.yaml`
- 码表：通过 `lx_shujuku` 查询 dataReporting `operator_brand`，不读取本地 Excel

## 注意事项

- 各模块内部使用 `from lxx_share.xxx import` 相对导入，需保证 lxx_share 目录在 `sys.path` 中。
- 维护者 RDS 连接、私有报表指标和写库能力不属于共享模块；公司数据只由 `lx_shujuku` 只读访问 dataReporting。

## 执行契约

### 输入

- 由上层共享 Skill 传入的配置段、码表映射或 Excel 对象。
- 仅接受库级调用，不作为用户任务的独立执行入口。

### 输出

- 稳定的 Python 返回值、明确异常和可供上层验收的统计；不直接发布业务产物。
- 配置读取、Excel 与缓存能力保持各模块既有接口。

### 验收

- 对应单元测试通过，上层调用方导入与关键返回结构不回归。
- 不输出密钥，也不在无上层确认时改变外部状态。
- 边界测试证明共享目录不包含维护者 RDS 连接或私有报表模块。
