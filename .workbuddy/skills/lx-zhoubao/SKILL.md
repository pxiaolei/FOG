---
name: lx-zhoubao
description: hhdata 周报生成工具。基于 RDS MySQL 的 hhdata__fact_daily_metrics 和公司库 operator_brand 码表，按大盘、主体、品牌、品牌城市、城市五个维度生成本地 Excel 周报。支持默认最近完整自然周，也支持指定非 7 天周期。触发关键词：周报、hhdata周报、lx-zhoubao。
agent_created: true
---

# lx-zhoubao — hhdata 周报生成

## 功能

默认从聚合表读取数据，生成本地 Excel 周报。完整自然周优先用 `hhdata__agg_weekly_metrics`；非完整周期优先用 `hhdata__agg_daily_brand_city_metrics` 按日期范围汇总。聚合数据由 `hhdata__fact_daily_metrics` 刷新得到。

输出维度：

- 大盘维度：所有 hhdata 数据汇总，对接人和运营主体为 `/`。
- 主体维度：按运营主体汇总，填写对接人和运营主体。
- 品牌维度：单品牌所有城市汇总，对接人和运营主体为 `/`。
- 品牌城市维度：具体品牌具体城市；能从 `operator_brand` 匹配则填写对接人和运营主体，不能匹配则填 `/` 并写入缺口说明。
- 城市维度：单城市所有品牌汇总，对接人和运营主体为 `/`。

维度整体排序固定为：大盘维度、主体维度、品牌维度、品牌城市维度、城市维度。每个维度内部按本期完单倒序。

## CLI 用法

```bash
# 默认：取最近完整自然周，本期对比前一周
python .workbuddy/skills/lx-zhoubao/scripts/run_weekly_report.py

# 刷新自然周聚合表；week-start 必须是周一
python .workbuddy/skills/lx-zhoubao/scripts/refresh_weekly_agg.py \
  --week-start 2026-06-08 \
  --weeks 2 \
  --force

# 刷新日粒度品牌城市聚合表；用于 3 天、活动周期等非完整自然周
python .workbuddy/skills/lx-zhoubao/scripts/refresh_daily_brand_city_agg.py \
  --start 2026-06-08 \
  --end 2026-06-21 \
  --force

# 指定本期；支持非 7 天周期，上期自动前移 7 天
python .workbuddy/skills/lx-zhoubao/scripts/run_weekly_report.py \
  --start 2026-06-15 \
  --end 2026-06-21

# 只预览行数、周期和缺口，不写 Excel
python .workbuddy/skills/lx-zhoubao/scripts/run_weekly_report.py \
  --start 2026-06-15 \
  --end 2026-06-21 \
  --dry-run
```

`run_weekly_report.py` 的默认 `--source auto` 规则：

- 完整自然周：优先读取 `hhdata__agg_weekly_metrics`；缺本周或上周聚合时回退 `hhdata__agg_daily_brand_city_metrics`；再缺才回退原始事实表。
- 非完整自然周，例如 3 天周期：优先读取 `hhdata__agg_daily_brand_city_metrics`；缺日期才回退原始事实表。
- `--source weekly`：强制周聚合表，只支持完整自然周。
- `--source daily`：强制日粒度品牌城市聚合表。
- `--source fact`：强制原始事实表。

Excel 默认写计算后的值，不写公式；只有显式传 `--formula-mode` 才写公式并需要 LibreOffice 重算。

默认模板：

```text
workspace/03数据报表/周报/hhdata周报模版.xlsx
```

默认输出：

```text
workspace/03数据报表/周报/hhdata周报_{本期起止}.xlsx
workspace/03数据报表/周报/hhdata周报_{本期起止}_summary.json
workspace/03数据报表/周报/hhdata周报_{本期起止}_gaps.csv
```

## 字段口径

- 量值字段填周期日均：`SUM(字段) / 周期天数`。
- `周期总gmv` 填周期总额：`SUM(gmv)`。
- 量值变化用百分比，率值变化用 pp。
- `TR` = `SUM(brand_commission) / SUM(gmv)`。
- `线上毛利` = `TR + 售卡收入率 - B补率 - 1%`。
- `卡劵收入` 按售卡收入率：`SUM(card_merchant_income) / SUM(gmv)`。
- `B补率` = `SUM(merchant_b_subsidy) / SUM(gmv)`。
- `成交率` = `SUM(completed_order_count) / SUM(passenger_order_count)`。
- `完单/应答（成交率）` = `SUM(completed_order_count) / SUM(response_count)`。
- `司乘取消率` = `(SUM(cancelled_by_driver) + SUM(cancelled_by_passenger)) / SUM(response_count)`。
- 分母为 0 或缺数据时，Excel 展示 ` / `。

## 数据来源

- `hhdata__agg_weekly_metrics`：周报默认读取的周聚合表。
- `hhdata__agg_weekly_refresh_runs`：周聚合刷新日志。
- `hhdata__agg_weekly_gaps`：周聚合缺口明细。
- `hhdata__agg_daily_brand_city_metrics`：非完整周期默认读取的日粒度品牌城市聚合表。
- `hhdata__fact_daily_metrics`：聚合刷新和缓存缺失兜底的指标事实源。
- `mabiao__dim_cities` / `mabiao__dim_brands`：事实表维度名称。
- `lx_shujuku.operator_brand`：运营主体和对接人映射真源。

## 验收

```bash
python .workbuddy/skills/lx-zhoubao/scripts/refresh_weekly_agg.py --week-start 2026-06-08 --weeks 2 --force
python .workbuddy/skills/lx-zhoubao/scripts/refresh_daily_brand_city_agg.py --start 2026-06-08 --end 2026-06-21 --force
python .workbuddy/skills/lx-zhoubao/scripts/run_weekly_report.py --start 2026-06-15 --end 2026-06-21 --dry-run
python .workbuddy/skills/lx-zhoubao/scripts/run_weekly_report.py --start 2026-06-15 --end 2026-06-17 --dry-run
python .workbuddy/skills/lx-zhoubao/scripts/run_weekly_report.py --start 2026-06-15 --end 2026-06-21
python -m unittest .workbuddy/skills/lx-zhoubao/tests/test_run_weekly_report.py
```

说明：默认不需要重算公式缓存。只有使用 `--formula-mode` 时，才需要用本机 Excel 或 LibreOffice 打开并保存一次 workbook；Windows 同事应使用自己电脑上的 Excel/LibreOffice 路径，不要照搬维护者本机路径。
