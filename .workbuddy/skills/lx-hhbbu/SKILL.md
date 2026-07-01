---
name: lx-hhbbu
description: 从公司 dataReporting 库按 date、city_name、brand_name 聚合导出 hhdata B补与售卡商家收入来源数据。用于查询或导出总b补金额、商家b补金额、售卡商家收入金额，不连接本地 RDS，不写数据库。触发关键词：hhdata补B补、总b补金额、商家b补金额、售卡商家收入、lx-hhbbu。
---

# lx-hhbbu — hhdata B补来源查询

## 定位

本 Skill 只查公司 `dataReporting`，按 `date + city_name + brand_name` 导出三项金额来源：

- `total_b_subsidy`：总b补金额
- `merchant_b_subsidy`：商家b补金额
- `card_merchant_income`：售卡商家收入金额

它不连接本地 RDS，不做写库回填，不依赖本地 `lxdata__fact_order_marketing` / `lxdata__fact_coupon_marketing` 是否已导入。

## 口径

按 `date_day + city_name + brand_name` 聚合公司库来源：

```text
总b补金额 = honghu_activity_marketing_data.total_reward_amount
          + honghu_coupon_marketing_data.total_subsidy_amount

商家b补金额 = honghu_activity_marketing_data.merchant_subsidy_amount
            + honghu_coupon_marketing_data.merchant_subsidy_amount

售卡商家收入金额 = honghu_coupon_marketing_data.merchant_coupon_sales_revenue
```

## 工作流

首次给同事配置时，先从 `config/fog_config.yaml.example` 复制 `lx_hhbbu` 配置块到自己的 `config/fog_config.yaml`，并确认本机 hhdata Excel 位置：

```yaml
lx_hhbbu:
  output_dir: "workspace/02数据导入/处理日志/lx-hhbbu"
  local_hhdata:
    source_type: "excel_dir"
    input_dir: "workspace/02数据导入/待处理/hhdata"
    file: ""
    required_before_run: false
```

如果同事把 hhdata 固定放在某个目录，填写 `local_hhdata.input_dir`；如果只有一个固定 Excel 文件，填写 `local_hhdata.file`。也可以不改配置，运行时临时传 `--hhdata-dir` 或 `--hhdata-file`。

只检查本地 hhdata 位置，不查询公司库：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --check-local-hhdata
```

导出 2026-06-18 到 2026-06-19：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19
```

如果本次要指定某个本地 hhdata 文件，并要求找不到时直接失败：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19 \
  --hhdata-file "/path/to/hhdata.xlsx" \
  --require-local-hhdata
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
- 本地 hhdata Excel 定位结果
- JSON 审计包
- Markdown 字段口径说明

## 安全边界

- 不连接本地 RDS。
- 不写任何数据库。
- 不直接读取或修改公司库，只通过 `lx_shujuku` 执行只读查询。
- `local_hhdata` 只用于定位同事本机 Excel 文件，不会自动导入或回写。
