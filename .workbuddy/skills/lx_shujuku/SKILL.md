---
name: lx_shujuku
description: 出行数据报表平台（dataReporting）公司数据库只读访问工具，提供登录鉴权、只读 SQL 查询、表结构浏览、operator_brand 码表加载和常用业务查询模板。
trigger_keywords:
  - lx_shujuku
  - 数据库
  - 数据报表
  - dataReporting
  - 活动数据
  - 宏鹄
  - 运力数据
  - 订单数据
  - 卡券
  - 先锋司机
  - 接起率
  - TR值
location: project
---

# lx_shujuku — 出行数据报表平台只读访问

## 功能

提供对 `datareporting.sfczhushou.com` 当前白名单业务表的只读查询能力：

1. **自动登录鉴权**：通过 `/dataReporting/user/login` 获取 Token，缓存复用
2. **当前 13 张业务表覆盖**：活动、免佣卡、运力、订单、卡券、分时明细、接起率、TR配置等
3. **表结构浏览**：`describe <table>` 查看任意表的字段、类型、注释
4. **只读 SQL 查询**：代码层强制只允许 `SELECT` / `SHOW` / `DESCRIBE` / `EXPLAIN`
5. **operator_brand 码表接口**：提供品牌、城市、运营主体、对接人的稳定映射
6. **业务查询模板**：预置常用查询（按品牌/城市/日期筛选、多表关联等）

## 数据库信息

| 项目 | 值 |
|------|-----|
| 地址 | `http://datareporting.sfczhushou.com` |
| 登录接口 | `POST /dataReporting/user/login` |
| 查询接口 | `POST /dataReporting/sql-query/execute` |
| 鉴权方式 | Header: `token: {token}` |

## 13 张业务表

| 表名 | 说明 | 字段数 |
|------|------|--------|
| `activity_data` | 活动信息主表 | 28 |
| `answer_rate_data` | 接起率数据表 | 10 |
| `brand_city_tr_config` | 品牌城市TR值配置表 | 6 |
| `card_data` | 免佣卡信息表 | 30 |
| `driver_real_time_data` | 运力实时累计数据表 | 23 |
| `honghu_activity_marketing_data` | 宏鹄活动营销数据表 | 30 |
| `honghu_capacity_data` | 宏鹄运力数据表 | 26 |
| `honghu_coupon_marketing_data` | 宏鹄卡券营销数据表 | 35 |
| `honghu_order_data` | 宏鹄订单数据表 | 25 |
| `honghu_time_split_data` | 宏鹄分时明细数据表 | 24 |
| `honghu_xf_driver_data` | 先锋司机数据表 | 8 |
| `operator_brand` | 运营主体-品牌-城市对照表 | 10 |
| `order_real_time_data` | 订单实时累计数据表 | 44 |

完整表结构定义见 `assets/schema.json`。

## CLI 用法

运行前设置 Python 入口：

```bash
WB_PYTHON="${WORKBUDDY_PYTHON:-$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3}"
```

```bash
# 列出所有表
"$WB_PYTHON" scripts/db_tools.py list-tables

# 查看指定表结构
"$WB_PYTHON" scripts/db_tools.py describe card_data

# 查看全部表结构概览
"$WB_PYTHON" scripts/db_tools.py catalog

# 执行 SQL 查询
"$WB_PYTHON" scripts/db_tools.py query "SELECT * FROM activity_data LIMIT 5"

# 执行 SQL 并保存结构化证据包
"$WB_PYTHON" scripts/db_tools.py query "SELECT * FROM activity_data LIMIT 5" --audit --question "查询活动样例"

# 查询 operator_brand 码表
"$WB_PYTHON" scripts/db_tools.py operator-brands --operator "方舟行（上海）"

# 浏览指标口径目录
"$WB_PYTHON" scripts/db_tools.py metrics
"$WB_PYTHON" scripts/db_tools.py metrics brand_city_daily_completed_orders

# 输出兼容本地 Excel 码表的映射统计
"$WB_PYTHON" scripts/db_tools.py mabiao

# 按品牌和日期查询（业务模板）
"$WB_PYTHON" scripts/db_tools.py template activity-by-brand --brand "方舟行申程司机端" --date "2025-05-12"

# 查询某张表的记录数
"$WB_PYTHON" scripts/db_tools.py count activity_data

# 对比线上表结构和本地 schema
"$WB_PYTHON" scripts/db_tools.py schema-diff

# 预览并确认刷新 schema.json 与 table_catalog.md
"$WB_PYTHON" scripts/db_tools.py refresh-schema
"$WB_PYTHON" scripts/db_tools.py refresh-schema --yes
```

## 配置

在项目根目录配置文件中填入**你自己的账号**：

```bash
config/fog_config.yaml
```

`lx_shujuku` 段需包含：

```yaml
lx_shujuku:
  api:
    base_url: "http://datareporting.sfczhushou.com"
    username: "你的用户名"
    password: "你的密码"
  query:
    default_limit: 100
    max_limit: 1000
```

⚠️ `config/fog_config.yaml` 已加入 `.gitignore`，凭证不会提交到版本控制。每位同事使用自己的账号。

## 快速上手（给同事）

```bash
# 1. 编辑 config/fog_config.yaml，填入你的用户名和密码

# 2. 验证连接
"$WB_PYTHON" scripts/db_tools.py health

# 3. 浏览数据库
"$WB_PYTHON" scripts/db_tools.py list-tables
"$WB_PYTHON" scripts/db_tools.py describe card_data

# 4. 查询数据
"$WB_PYTHON" scripts/db_tools.py query "SELECT * FROM operator_brand LIMIT 10"

# 5. 查询公司库码表
"$WB_PYTHON" scripts/db_tools.py operator-brands --limit 10

# 6. 查看指标口径目录
"$WB_PYTHON" scripts/db_tools.py metrics
```

## 给其他 Skill 的 import 入口

其他 Skill 应优先复用 `lx_shujuku` 包，不要直接拼接 `operator_brand` SQL：

```python
from lx_shujuku import create_client

client = create_client()
rows = client.get_operator_brands(operator="方舟行（上海）")
mapping = client.load_mabiao_mapping()
```

`load_mabiao_mapping()` 返回兼容 `lxx_share.excel_utils.load_mabiao()` 的结构，后续可用于替换本地 Excel 码表。

## 给 AI 写文档的证据包流程

当查询结果会被 AI 用于写报告、说明文档或对外同步时，不要只复制终端输出。应使用 `--audit`、`--json` 或 `--output` 生成结构化证据包：

```bash
"$WB_PYTHON" scripts/db_tools.py query "SELECT city_name, SUM(completed_order_count) AS completed_order_count FROM honghu_order_data WHERE brand_name = '拼哒出行' AND date_day = '2026-06-02' GROUP BY city_name ORDER BY completed_order_count DESC LIMIT 100" \
  --audit \
  --question "拼哒出行 2026-06-02 每个城市的完单数" \
  --metric brand_city_daily_completed_orders
```

证据包会记录原始问题、指标口径 ID、原始 SQL、安全改写后的 SQL、执行时间、返回行数、结果行和风险提示。默认保存到 `assets/query_runs/`，该目录已加入 `.gitignore`，不要直接分享含敏感明细的数据包。

指标口径目录在：

```bash
references/metrics_catalog.json
```

AI 写文档前应先读取该目录，确认使用的表、日期字段、聚合方式、适用/不适用场景和交叉验证 SQL。

## 数据来源

- API 网关: `http://datareporting.sfczhushou.com`
- 数据库: `dataReporting`（MySQL 兼容）
- Token 有效期: 服务端控制，脚本自动监测 401 后重新登录

## 依赖

- Python 3.9+，纯标准库（`urllib.request`），无需安装第三方包
- 无跨 Skill 依赖

## 限制

- 仅支持只读 SQL（代码层拦截写库/DDL/多语句）
- 普通 SQL 查询的表名必须存在于 `assets/schema.json` 白名单
- `describe` / `count` 的表名必须存在于 `assets/schema.json` 白名单
- `SELECT` 未写 `LIMIT` 时会自动追加默认限制
- `SHOW` 仅允许表和字段元数据查询
- Token 过期时有自动刷新机制
- 建议使用 `--limit` 控制返回行数，避免大数据量查询阻塞
- 刷新 schema 前先运行 `schema-diff`；`refresh-schema` 默认只预览，只有追加 `--yes` 才会写入并自动备份旧文件
