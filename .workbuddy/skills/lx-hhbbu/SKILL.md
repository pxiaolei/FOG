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

导出 2026-06-18 到 2026-06-19：

```bash
python3 .workbuddy/skills/lx-hhbbu/scripts/hhbbu_source_export.py \
  --start-date 2026-06-18 \
  --end-date 2026-06-19
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
- JSON 审计包
- Markdown 字段口径说明

## 安全边界

- 不连接本地 RDS。
- 不写任何数据库。
- 不直接读取或修改公司库，只通过 `lx_shujuku` 执行只读查询。
