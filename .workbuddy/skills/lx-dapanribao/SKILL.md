---
name: lx-dapanribao
description: 运营日报生成工具，按对接人为其负责的运营主体生成每日数据看板，含 17 个核心指标（订单/司机/财务/率值）的环比同比与城市大盘对比，自动异动检测并调用异动分析深挖根因，生成腾讯文档企业版发布计划，并依赖全局 tencent-saas-docs 写入在线表格。
trigger_keywords:
  - 生成日报
  - 今日日报
  - 日报
  - 运营日报
  - 大盘日报
  - dapanribao
  - dailyreport
location: project
---

# lx-dapanribao — 运营大盘日报生成

## 功能

1. 从 hhdata 数据库加载三天数据（当日/昨日/上周同日）
2. 按运营主体 × 品牌 × 城市计算 17 个核心指标
3. 计算环比/同比/城市大盘对比
4. 检测完单同比异动（偏离城市大盘 ≥ 5pp）
5. 调用 lx-yidongfenxi 做异动归因分析（可选）
6. 生成腾讯文档企业版发布计划，由全局 `tencent-saas-docs` 写入在线表格

## 三步工作流

| 阶段 | 说明 |
|------|------|
| 预览 | `python3 main.py --dry-run` 查看数据摘要，不发布 |
| 生成 | `python3 main.py` 自动加载数据、构建日报、生成企业版发布计划 |
| 指定主体 | `python3 main.py --operator 江豚出行` 只处理指定主体 |

## 腾讯文档企业版发布机制

- 发布依赖全局 WorkBuddy Skill：`tencent-saas-docs`
- 企业版根文件夹：`https://efe3f9566e.docs.qq.com/desktop/mydoc/folder/TlznihwNLTGuzisgAg`
- 根文件夹下按运营主体查找子文件夹：默认 `{运营主体}`
- 每个运营主体一个独立表格：默认 `{运营主体}-大盘数据对比`
- 每天新增或替换一个 Sheet（日期标签如 "0601"）
- Python 脚本只生成发布计划 JSON，不直接调用旧版 `lxx_share.tdocs_api`
- 发布计划默认输出到 `workspace/03数据报表/日报/dapanribao_publish_plan_{MMDD}.json`

## CLI 用法

```bash
# 为配置中的默认对接人生成今日日报；未配置时需传 --person 或 --operator
python3 main.py

# 指定对接人
python3 main.py --person 雷维亮

# 指定日期
python3 main.py --person 雷维亮 --date 2026-06-01

# 指定运营主体
python3 main.py --operator 江豚出行

# 预览不发布
python3 main.py --person 雷维亮 --dry-run

# 指定本地输出目录
python3 main.py --output-dir workspace/03数据报表/日报
```

## 指标清单

17 类指标 × 5 子列（当日值/环比/同比/城市环比/城市同比）：

| 类别 | 指标 |
|------|------|
| 订单类 | 完单、发单 |
| 司机类 | 在线司机、TSH/在线时长、TPH/司机效率、首次完单司机数、人均完单量 |
| 财务类 | GMV、客单价 |
| 率值类 | 线上毛利率、商家抽佣TR、售卡收入率、商家B补率、发单应答率、应答完单率、完单司机占比、司机取消率 |

## 数据来源

- `hhdata.fact_daily_metrics` — 主数据表
- `mabiao.dim_cities` / `mabiao.dim_brands` — 维度表
- `lx_shujuku.operator_brand` — 品牌/城市 → 运营主体 → 对接人映射

## 依赖

- `lxx_share` — 共享基础模块（数据库、指标计算、码表、腾讯文档 API）
- `lx_shujuku` — 公司库 `operator_brand` 码表来源
- 全局 `tencent-saas-docs` — 腾讯文档企业版 MCP/Skill 发布能力
- `config/fog_config.yaml` — 数据库、企业版根文件夹、目标表格命名、默认对接人等配置

## 跨 Skill 发布依赖

日报发布时需使用全局 `tencent-saas-docs` 操作腾讯文档企业版。

**发布目标配置**：`config/fog_config.yaml` → `lx_dapanribao`

**约束**：
- 根文件夹 URL / ID 必须写入配置，不能硬编码散落在脚本或提示词中
- 运营主体文件夹默认按 `{operator}` 命名；如企业版目录命名变化，修改 `operator_folder_name_template`
- 目标表格默认按 `{operator}-大盘数据对比` 命名；如表格命名变化，修改 `report_title_template`
- `dailyreport_cache.json` 仅可缓存企业版 `file_id` / `sheet_id`，不进入模板分发
- 执行实际写入前，应先读取发布计划并用 `tencent-saas-docs` 查询确认目标文件夹和表格

## 发布计划执行步骤

1. 运行 `main.py --dry-run` 预览日报数据和发布计划。
2. 确认无误后运行 `main.py` 生成完整发布计划 JSON。
3. 使用全局 `tencent-saas-docs`：
   - 在企业版根文件夹下查找 `{运营主体}` 文件夹；
   - 在运营主体文件夹中查找或创建 `{运营主体}-大盘数据对比` 表格；
   - 创建或替换日期 Sheet；
   - 用 `sheet.batch_update` 写入发布计划中的 `data_rows`。

旧 `post_format.py` 属于旧版个人 OpenAPI 路径，企业版发布不再使用。
