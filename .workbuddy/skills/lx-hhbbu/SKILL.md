---
name: lx-hhbbu
description: 从公司 dataReporting 库按 date、city_name、brand_name 聚合 hhdata B补与售卡商家收入来源数据，并按配置的 hhdata 目标写回总b补金额、商家b补金额、售卡商家收入金额三列。目标只能是单个 Excel 文件或一张数据库事实表。触发关键词：hhdata补B补、总b补金额、商家b补金额、售卡商家收入、lx-hhbbu。
---

# lx-hhbbu — hhdata B补来源写回

## 定位

本 Skill 查询公司 `dataReporting`，按 `date + city_name + brand_name` 取得三项金额来源，并可写回配置的 hhdata 目标：

- `excel_file`：写回一个明确的 hhdata Excel 文件。
- `database_table`：写回一张明确的 hhdata 数据库事实表。

两种目标使用同一个匹配 key、同一组来源字段、同一套 dry-run/confirmed 安全门。不要按使用人区分逻辑，只按配置里的 `lx_hhbbu.local_hhdata.target` 分发。

## 口径

按 `date_day + city_name + brand_name` 聚合公司库来源：

```text
总b补金额 = honghu_activity_marketing_data.total_reward_amount
          + honghu_coupon_marketing_data.total_subsidy_amount

商家b补金额 = honghu_activity_marketing_data.merchant_subsidy_amount
            + honghu_coupon_marketing_data.merchant_subsidy_amount

售卡商家收入金额 = honghu_coupon_marketing_data.merchant_coupon_sales_revenue
```

## 配置

首次配置时，先从 `config/fog_config.yaml.example` 复制 `lx_hhbbu` 配置块到自己的 `config/fog_config.yaml`，再选择目标类型：

```yaml
lx_hhbbu:
  output_dir: "workspace/02数据导入/处理日志/lx-hhbbu"
  local_hhdata:
    target: "excel_file"
    required_before_run: true
    excel_file:
      file: ""
      sheet_name: ""
      backup_dir: "workspace/02数据导入/处理日志/lx-hhbbu/backups"
    database_table:
      table: "hhdata__fact_daily_metrics"
      city_dim_table: "mabiao__dim_cities"
      brand_dim_table: "mabiao__dim_brands"
```

规则：

- `target` 只能是 `excel_file` 或 `database_table`。
- `target: excel_file` 时，`excel_file.file` 必须指向唯一的 hhdata Excel 文件；不要填写目录，也不要让脚本猜“最新文件”。
- `target: database_table` 时，必须配置 `database_table.table`、`city_dim_table`、`brand_dim_table`，并在 `database` 配置块填写数据库连接信息。
- 数据库表写回时，fact 表只用 `brand_id` / `city_id` join 维表取得名称，不依赖 fact 表里的冗余名称列。

## 工作流

只检查 hhdata 写回目标，不查询公司库：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --check-local-hhdata
```

只查询公司源并导出审计文件，不写回 hhdata：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19
```

生成 Excel 写回计划，不保存：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19 \
  --hhdata-target excel_file \
  --hhdata-file "/path/to/hhdata.xlsx" \
  --update-hhdata
```

确认写回 Excel，写入前会自动备份：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19 \
  --hhdata-target excel_file \
  --hhdata-file "/path/to/hhdata.xlsx" \
  --update-hhdata \
  --confirmed
```

生成数据库表写回计划，不提交：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19 \
  --hhdata-target database_table \
  --update-hhdata
```

确认写回数据库表：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19 \
  --hhdata-target database_table \
  --update-hhdata \
  --confirmed
```

输出 CSV / JSON / Markdown，CSV 字段包括：

- `date`、`city_name`、`brand_name`
- `total_b_subsidy`
- `merchant_b_subsidy`
- `card_merchant_income`
- 活动和卡券来源拆分金额

## 输出

每次运行都会写审计文件到：

```text
workspace/02数据导入/处理日志/lx-hhbbu/
```

包含：

- 按 `date + city_name + brand_name` 聚合的 CSV
- 来源表按日期汇总
- hhdata 写回目标定位结果
- Excel 或数据库表写回计划、变更行数和跳过原因
- JSON 审计包
- Markdown 字段口径说明

## 安全边界

- 只通过 `lx_shujuku` 对公司 `dataReporting` 执行只读查询。
- 默认 `--update-hhdata` 只生成 dry-run 写回计划；只有追加 `--confirmed` 才会保存 Excel 或提交数据库更新。
- Excel 写回前会备份原文件。
- Excel 或数据库表如果出现重复 `date + city_name + brand_name`，对应行会跳过，避免重复写入同一个公司源金额。
- 数据库表写回只更新已存在的唯一匹配行，不自动新增 fact 行。
