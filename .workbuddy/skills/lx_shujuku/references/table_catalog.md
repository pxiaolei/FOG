# dataReporting 数据库表结构目录

> 生成时间：2026-06-03T10:11:14.614718+08:00  |  数据库：dataReporting  |  共 13 张表

---

## 目录

1. [activity_data](#activity-data) — 活动信息主表
2. [answer_rate_data](#answer-rate-data) — 接起率数据表
3. [brand_city_tr_config](#brand-city-tr-config) — 品牌城市TR值配置表
4. [card_data](#card-data) — 免佣卡信息表
5. [driver_real_time_data](#driver-real-time-data) — 运力实时累计数据表
6. [honghu_activity_marketing_data](#honghu-activity-marketing-data) — 宏鹄活动营销数据表
7. [honghu_capacity_data](#honghu-capacity-data) — 宏鹄运力数据离线看板-运力数据表
8. [honghu_coupon_marketing_data](#honghu-coupon-marketing-data) — 宏鹄卡券营销数据表
9. [honghu_order_data](#honghu-order-data) — 宏鹄订单数据离线看板-订单数据表
10. [honghu_time_split_data](#honghu-time-split-data) — 宏鹄订单运力分时-供需分时明细数据表
11. [honghu_xf_driver_data](#honghu-xf-driver-data) — 
12. [operator_brand](#operator-brand) — 运营主体-品牌名称城市对照表
13. [order_real_time_data](#order-real-time-data) — 订单实时累计数据表

---

## activity_data

**活动信息主表**  |  28 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `varchar(32)` | 🔑 PRI | ✗ | 活动ID（唯一标识） |
| 2 | `operator_entity` | `varchar(100)` |  | ✓ | 运营主体 |
| 3 | `business_name` | `varchar(100)` | 🔑 PRI | ✗ | 商家名称 |
| 4 | `city` | `varchar(64)` | 🔑 PRI | ✗ | 城市 |
| 5 | `contact_person` | `varchar(64)` |  | ✓ | 对接人 |
| 6 | `title` | `varchar(255)` |  | ✓ | 活动标题 |
| 7 | `status` | `int(2)` |  | ✓ | 活动状态 |
| 8 | `channel_id` | `int(2)` |  | ✓ | 渠道ID |
| 9 | `brand_id` | `varchar(32)` |  | ✓ | 品牌ID |
| 10 | `is_join_subsidy` | `int(2)` |  | ✓ | 是否参与补贴 |
| 11 | `city_ids` | `varchar(255)` |  | ✓ | 活动覆盖城市ID列表 |
| 12 | `content` | `text` |  | ✓ | 活动内容详情JSON |
| 13 | `subsidy_type` | `int(2)` |  | ✓ | 补贴类型 |
| 14 | `tpl_id` | `varchar(32)` |  | ✓ | 模板ID |
| 15 | `creator` | `varchar(50)` |  | ✓ | 活动创建方 |
| 16 | `auditor` | `varchar(50)` |  | ✓ | 审核方 |
| 17 | `start_time` | `datetime` |  | ✓ | 活动开始时间 |
| 18 | `end_time` | `datetime` |  | ✓ | 活动结束时间 |
| 19 | `invest_end_time` | `datetime` |  | ✓ | 报名截止时间 |
| 20 | `project_no` | `varchar(64)` |  | ✓ | 项目编号 |
| 21 | `project_name` | `varchar(255)` |  | ✓ | 项目名称 |
| 22 | `create_time` | `datetime` |  | ✓ | 活动创建时间 |
| 23 | `create_source` | `varchar(50)` |  | ✓ | 创建来源 |
| 24 | `extra` | `text` |  | ✓ | 额外扩展信息 |
| 25 | `is_additional_join` | `tinyint(4)` |  | ✓ | 是否额外参与 |
| 26 | `create_source_desc` | `varchar(50)` |  | ✓ | 创建来源描述 |
| 27 | `gmt_create` | `datetime` |  | ✓ | 数据入库时间 |
| 28 | `gmt_update` | `datetime` |  | ✓ | 数据更新时间 |

---

## answer_rate_data

**接起率数据表**  |  10 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `tenant_id` | `varchar(64)` | 📇 MUL | ✗ | 租户ID |
| 3 | `tenant_name` | `varchar(128)` |  | ✗ | 租户名称 |
| 4 | `answer_rate` | `decimal(10,6)` |  | ✓ | 接起率（cal_f60f0b76d0940f7a89df24a5518c1279字段） |
| 5 | `incoming_count` | `int(11)` |  | ✓ | 进线量（datae_column_a48952bb8a_sum字段） |
| 6 | `answered_count` | `int(11)` |  | ✓ | 接起量（datae_column_045add6dce_sum字段） |
| 7 | `data_date` | `date` | 📇 MUL | ✓ | 数据日期 |
| 8 | `created_time` | `datetime` |  | ✓ | 创建时间 |
| 9 | `pull_time` | `datetime` |  | ✓ | 拉取时间 |
| 10 | `updated_time` | `datetime` |  | ✓ | 修改时间 |

---

## brand_city_tr_config

**品牌城市TR值配置表**  |  6 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `brand_name` | `varchar(100)` | 📇 MUL | ✓ | 品牌名称 |
| 3 | `city_name` | `varchar(100)` |  | ✓ | 城市名称 |
| 4 | `tr_value` | `decimal(10,2)` |  | ✓ | TR值（百分比，如：15.5 表示 15.5%） |
| 5 | `create_time` | `datetime` |  | ✓ | 创建时间 |
| 6 | `update_time` | `datetime` |  | ✓ | 更新时间 |

---

## card_data

**免佣卡信息表**  |  30 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `varchar(32)` | 🔑 PRI | ✗ | 免佣卡ID |
| 2 | `operator_entity` | `varchar(100)` |  | ✓ | 运营主体 |
| 3 | `business_name` | `varchar(100)` | 🔑 PRI | ✗ | 商家名称 |
| 4 | `city` | `varchar(64)` | 🔑 PRI | ✗ | 城市 |
| 5 | `contact_person` | `varchar(64)` |  | ✓ | 对接人 |
| 6 | `title` | `varchar(255)` |  | ✓ | 免佣卡标题 |
| 7 | `status` | `varchar(10)` |  | ✓ | 状态码 |
| 8 | `channel_id` | `varchar(32)` |  | ✓ | 渠道ID |
| 9 | `tpl_id` | `varchar(32)` |  | ✓ | 模板ID |
| 10 | `allocation_rules` | `text` |  | ✓ | 分配规则 |
| 11 | `content` | `text` |  | ✓ | 免佣卡详情JSON字符串 |
| 12 | `brand_id` | `varchar(32)` |  | ✓ | 品牌ID |
| 13 | `city_ids` | `varchar(255)` |  | ✓ | 适用城市ID列表 |
| 14 | `subsidy_type` | `varchar(10)` |  | ✓ | 补贴类型 |
| 15 | `creator` | `varchar(50)` |  | ✓ | 创建人 |
| 16 | `auditor` | `varchar(50)` |  | ✓ | 审核人 |
| 17 | `sale_start_time` | `datetime` |  | ✓ | 销售开始时间 |
| 18 | `sale_end_time` | `datetime` |  | ✓ | 销售结束时间 |
| 19 | `effect_start_time` | `datetime` |  | ✓ | 生效开始时间 |
| 20 | `effect_end_time` | `datetime` |  | ✓ | 生效结束时间 |
| 21 | `project_no` | `varchar(64)` |  | ✓ | 项目编号 |
| 22 | `project_name` | `varchar(255)` |  | ✓ | 项目名称 |
| 23 | `invest_end_time` | `datetime` |  | ✓ | 投资结束时间 |
| 24 | `is_join_subsidy` | `varchar(10)` |  | ✓ | 是否参与补贴 |
| 25 | `extra` | `text` |  | ✓ | 额外信息 |
| 26 | `get_type` | `varchar(32)` |  | ✓ | 获取方式 |
| 27 | `stock` | `int(11)` |  | ✓ | 库存数量 |
| 28 | `is_additional_join` | `tinyint(4)` |  | ✓ | 是否额外参与 |
| 29 | `gmt_create` | `datetime` |  | ✓ | 创建时间 |
| 30 | `gmt_update` | `datetime` |  | ✓ | 更新时间 |

---

## driver_real_time_data

**运力实时累计数据表**  |  23 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `tenant_name` | `varchar(20)` |  | ✓ | 租户名称 |
| 3 | `tenant_id` | `varchar(20)` |  | ✓ | 租户id |
| 4 | `datae_column_bc7a384cd7_day_real` | `date` |  | ✓ | 数据日期 |
| 5 | `cal_42b6ccdb9832a04000d13c0b00a8f365` | `bigint(20)` |  | ✓ | 匹配司机数(data_one_ident=3) |
| 6 | `cal_7050206267d5d6f983310c0fd15ebc9a` | `bigint(20)` |  | ✓ | 完单司机数(data_one_ident=7) |
| 7 | `cal_f26aa9c3cef567bbf2f68eb01a671790` | `bigint(20)` |  | ✓ | 在线司机数(data_one_ident=101) |
| 8 | `cal_2bf40e137f207dce4e82d799ad25b0ac` | `bigint(20)` |  | ✓ | 服务中司机数(data_one_ident=102) |
| 9 | `cal_ebfde248b6edb7171b6b34ef0deff019` | `decimal(16,6)` |  | ✓ | 负载率(服务中司机数/在线司机数) |
| 10 | `relative_2b4be74799e3f5a18efbfd7fc014cae4` | `decimal(16,8)` |  | ✓ | 匹配司机数日环比 |
| 11 | `relative_c4269c08cfecae12e494e58ade692f07` | `decimal(16,8)` |  | ✓ | 匹配司机数周同比 |
| 12 | `relative_3c49d0448125ade5c282985aad816a74` | `decimal(16,8)` |  | ✓ | 完单司机数日环比 |
| 13 | `relative_15da124c19ecf81f9c10a5e8bbfe3fa3` | `decimal(16,8)` |  | ✓ | 完单司机数周同比 |
| 14 | `relative_6efbe152ef498f644de1cd92f17d6240` | `decimal(16,8)` |  | ✓ | 在线司机数日环比 |
| 15 | `relative_63b6e1459f39fceb47cd0637c9242c57` | `decimal(16,8)` |  | ✓ | 在线司机数周同比 |
| 16 | `relative_d8c1ebfee6e6c021aab2e04fa39688f7` | `decimal(16,8)` |  | ✓ | 服务中司机数日环比 |
| 17 | `relative_fd7ecc482b21fc3c61b3ee0b1acbcf16` | `decimal(16,8)` |  | ✓ | 服务中司机数周同比 |
| 18 | `relative_6ee128f766d78334d53820d319510f3b` | `decimal(16,8)` |  | ✓ | 负载率日环比差值 |
| 19 | `relative_b6b92d0590924d95285b2c73b2d33c5f` | `decimal(16,8)` |  | ✓ | 负载率周同比差值 |
| 20 | `pull_time` | `varchar(60)` |  | ✓ | 拉取数据时间 |
| 21 | `time_period` | `int(2)` |  | ✓ | 数据时间段（到时） |
| 22 | `created_time` | `datetime` |  | ✓ | 创建时间 |
| 23 | `updated_time` | `datetime` |  | ✓ | 更新时间 |

---

## honghu_activity_marketing_data

**宏鹄活动营销数据表**  |  30 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `date_day` | `varchar(20)` |  | ✗ | 统计日期（天） |
| 3 | `brand_name` | `varchar(20)` | 📇 MUL | ✓ | 品牌名称 |
| 4 | `city_name` | `varchar(20)` |  | ✓ | 城市名称 |
| 5 | `activity_id` | `bigint(20) unsigned` |  | ✓ | 活动ID（唯一标识） |
| 6 | `activity_name` | `varchar(50)` |  | ✓ | 活动名称 |
| 7 | `activity_start_date` | `date` |  | ✓ | 活动开始日期 |
| 8 | `activity_end_date` | `date` |  | ✓ | 活动结束日期 |
| 9 | `reward_template` | `varchar(20)` |  | ✓ | 奖励模板类型 |
| 10 | `subsidy_type` | `varchar(20)` |  | ✓ | 补贴类型 |
| 11 | `creator` | `varchar(20)` |  | ✓ | 活动创建人 |
| 12 | `reviewer` | `varchar(20)` |  | ✓ | 活动审核人 |
| 13 | `merchant_share_ratio` | `decimal(8,6)` |  | ✓ | 商家承担比例（0-1） |
| 14 | `agent_id` | `int(10) unsigned` |  | ✓ | 代理商ID（当前均为0） |
| 15 | `agent_name` | `varchar(50)` |  | ✓ | 代理商名称（当前无数据） |
| 16 | `agent_share_ratio` | `decimal(8,6)` |  | ✓ | 代理商承担比例（当前均为0） |
| 17 | `pred_rate` | `decimal(10,4)` |  | ✓ | 预测b补率 |
| 18 | `completed_order_count` | `int(10) unsigned` |  | ✓ | 活动完成订单数 |
| 19 | `completed_user_count` | `int(10) unsigned` |  | ✓ | 活动完单人数 |
| 20 | `awarded_user_count` | `int(10) unsigned` |  | ✓ | 活动获奖人数 |
| 21 | `completed_order_amount` | `varchar(255)` |  | ✓ | 总订单GMV |
| 22 | `award_rate` | `decimal(10,6)` |  | ✓ | 活动获奖率（获奖人数/完单人数） |
| 23 | `total_reward_amount` | `decimal(10,4)` |  | ✓ | 活动总奖励金额（元） |
| 24 | `platform_subsidy_amount` | `decimal(10,4)` |  | ✓ | 平台补贴金额（元） |
| 25 | `honghu_subsidy_amount` | `decimal(10,4)` |  | ✓ | 宏鹄补贴金额（元） |
| 26 | `merchant_subsidy_amount` | `decimal(10,4)` |  | ✓ | 商家补贴金额（元） |
| 27 | `agent_bear_amount` | `decimal(10,4)` |  | ✓ | 代理商承担金额（元，当前均为0） |
| 28 | `cooperator_bear_amount` | `decimal(10,4)` |  | ✓ | 合作运营方承担金额（元） |
| 29 | `created_time` | `datetime` |  | ✓ | 数据创建时间 |
| 30 | `updated_time` | `datetime` |  | ✓ | 数据更新时间 |

---

## honghu_capacity_data

**宏鹄运力数据离线看板-运力数据表**  |  26 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `brand_name` | `varchar(20)` |  | ✗ | 品牌名称 |
| 3 | `date_day` | `varchar(20)` |  | ✗ | 日期（天） |
| 4 | `city_name` | `varchar(20)` |  | ✗ | 城市名称 |
| 5 | `supplier` | `varchar(50)` |  | ✓ | 供应商名称 |
| 6 | `agent` | `varchar(50)` |  | ✓ | 代理商名称 |
| 7 | `peak_online_driver_count` | `int(10) unsigned` |  | ✗ | 峰期在线司机数 |
| 8 | `peak_valid_driver_count` | `int(10) unsigned` |  | ✗ | 峰期有效司机数 |
| 9 | `peak_valid_driver_conversion_rate` | `decimal(10,4)` |  | ✓ | 峰期有效司机转化率 |
| 10 | `online_driver_count` | `int(10) unsigned` |  | ✗ | 在线司机数 |
| 11 | `first_completion_driver_count` | `int(10) unsigned` |  | ✗ | 首次完单司机数 |
| 12 | `valid_driver_count` | `int(10) unsigned` |  | ✗ | 有效司机数 |
| 13 | `valid_driver_conversion_rate` | `decimal(10,4)` |  | ✓ | 有效司机转化率 |
| 14 | `response_driver_count` | `int(10) unsigned` |  | ✗ | 应答司机数 |
| 15 | `completion_driver_count` | `int(10) unsigned` |  | ✗ | 完单司机数 |
| 16 | `online_duration_hour` | `decimal(10,2)` |  | ✗ | 在线时长（小时） |
| 17 | `online_duration_old_hour` | `decimal(10,2)` |  | ✗ | 在线时长(旧)（小时） |
| 18 | `service_duration_hour` | `decimal(10,2)` |  | ✗ | 服务时长（小时） |
| 19 | `driver_completion_rate` | `decimal(10,4)` |  | ✓ | 司机完单率 |
| 20 | `per_capita_online_duration_hour` | `decimal(10,2)` |  | ✗ | 人均在线时长（小时） |
| 21 | `service_duration_ratio` | `decimal(10,2)` |  | ✓ | 服务时长占比 |
| 22 | `per_capita_completion_count` | `decimal(10,2)` |  | ✓ | 人均完单量 |
| 23 | `completion_per_hour` | `decimal(10,2)` |  | ✓ | 每小时完单量 |
| 24 | `revenue_per_hour` | `decimal(10,2)` |  | ✓ | 每小时收入（元） |
| 25 | `created_time` | `datetime` |  | ✗ | 创建时间 |
| 26 | `updated_time` | `datetime` |  | ✗ | 更新时间 |

---

## honghu_coupon_marketing_data

**宏鹄卡券营销数据表**  |  35 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `date_day` | `varchar(20)` |  | ✗ | 统计日期（天） |
| 3 | `city_name` | `varchar(20)` |  | ✗ | 城市名称 |
| 4 | `brand_name` | `varchar(20)` | 📇 MUL | ✗ | 品牌名称（当前为飞嘀尊驾） |
| 5 | `agent_id` | `int(10) unsigned` |  | ✗ | 代理商ID（当前均为0） |
| 6 | `agent_name` | `varchar(50)` |  | ✓ | 代理商名称（当前无数据） |
| 7 | `product_id` | `int(10) unsigned` |  | ✗ | 卡券商品ID（唯一标识） |
| 8 | `product_name` | `varchar(50)` |  | ✗ | 卡券商品名称 |
| 9 | `effective_start_time` | `datetime` |  | ✗ | 卡券生效开始时间（含时分秒） |
| 10 | `effective_end_time` | `datetime` |  | ✗ | 卡券生效结束时间（含时分秒） |
| 11 | `coupon_template` | `varchar(20)` |  | ✗ | 卡券模板类型（免佣卡/飞涨卡） |
| 12 | `subsidy_type` | `varchar(20)` |  | ✗ | 补贴类型（商家独补/强制共补） |
| 13 | `coupon_type` | `varchar(64)` |  | ✓ | 卡类型 |
| 14 | `coupon_tag` | `varchar(60)` |  | ✓ | 卡标签 |
| 15 | `creator` | `varchar(40)` |  | ✓ | 卡券创建人 |
| 16 | `reviewer` | `varchar(40)` |  | ✓ | 卡券审核人 |
| 17 | `merchant_share_ratio` | `decimal(8,6)` |  | ✗ | 商家承担比例（0-1） |
| 18 | `agent_share_ratio` | `decimal(8,6)` |  | ✗ | 代理商承担比例（当前均为0） |
| 19 | `total_coupon_sales_revenue` | `decimal(10,2)` |  | ✗ | 总券后售卡收入（元） |
| 20 | `platform_coupon_sales_revenue` | `decimal(10,2)` |  | ✗ | 平台券后售卡收入（元） |
| 21 | `merchant_coupon_sales_revenue` | `decimal(10,2)` |  | ✗ | 商家券后售卡收入（元） |
| 22 | `agent_coupon_sales_revenue` | `decimal(10,2)` |  | ✗ | 代理商券后售卡收入（元，当前均为0） |
| 23 | `cooperator_coupon_sales_revenue` | `decimal(10,2)` |  | ✗ | 合作运营商券后售卡收入（元，当前均为0） |
| 24 | `daily_card_purchase_count` | `int(10) unsigned` |  | ✗ | 当日购卡人数 |
| 25 | `daily_verification_count` | `int(10) unsigned` |  | ✗ | 当日核销人数 |
| 26 | `verification_order_count` | `int(10) unsigned` |  | ✗ | 核销订单数 |
| 27 | `verification_order_gmv` | `decimal(12,2)` |  | ✗ | 核销订单GMV（元） |
| 28 | `total_subsidy_amount` | `decimal(10,2)` |  | ✗ | 总补贴金额（元） |
| 29 | `platform_subsidy_amount` | `decimal(10,2)` |  | ✗ | 平台补贴金额（元） |
| 30 | `channel_subsidy_amount` | `decimal(10,2)` |  | ✗ | 渠道补贴金额（元） |
| 31 | `merchant_subsidy_amount` | `decimal(10,2)` |  | ✗ | 商家补贴金额（元） |
| 32 | `agent_subsidy_amount` | `decimal(10,2)` |  | ✗ | 代理商补贴金额（元，当前均为0） |
| 33 | `cooperator_subsidy_amount` | `decimal(10,2)` |  | ✗ | 合作运营商补贴金额（元，当前均为0） |
| 34 | `created_time` | `datetime` |  | ✗ | 数据创建时间 |
| 35 | `updated_time` | `datetime` |  | ✗ | 数据更新时间 |

---

## honghu_order_data

**宏鹄订单数据离线看板-订单数据表**  |  25 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `brand_name` | `varchar(20)` | 📇 MUL | ✗ | 品牌名称 |
| 3 | `date_day` | `varchar(20)` |  | ✗ | 日期（天） |
| 4 | `city_name` | `varchar(20)` |  | ✗ | 城市名称 |
| 5 | `traffic_channel` | `varchar(20)` |  | ✗ | 流量渠道 |
| 6 | `order_type` | `varchar(10)` |  | ✓ | 订单类型 |
| 7 | `passenger_order_count` | `bigint(10)` |  | ✓ | 乘客发单量 |
| 8 | `no_capacity_fold_rate` | `decimal(10,4)` |  | ✓ | 无运力折叠率 |
| 9 | `non_compliance_fold_rate` | `decimal(8,4)` |  | ✓ | 执规考核不达标折叠率 |
| 10 | `match_count` | `bigint(10)` |  | ✓ | 匹配量 |
| 11 | `response_count` | `bigint(10)` |  | ✓ | 应答量 |
| 12 | `response_rate` | `decimal(10,4)` |  | ✓ | 应答率 |
| 13 | `driver_cancel_count_after_response` | `bigint(10)` |  | ✓ | 应答后司机取消量 |
| 14 | `driver_cancel_rate_after_response` | `decimal(10,4)` |  | ✓ | 应答后司机取消率 |
| 15 | `passenger_cancel_count_after_response` | `bigint(10)` |  | ✓ | 应答后乘客取消量 |
| 16 | `passenger_cancel_rate_after_response` | `decimal(10,4)` |  | ✓ | 应答后乘客取消率 |
| 17 | `customer_service_close_count_after_response` | `bigint(10)` |  | ✓ | 应答后客服关闭订单数 |
| 18 | `pk_success_rate` | `decimal(10,4)` |  | ✓ | PK成功率 |
| 19 | `transaction_rate` | `decimal(10,4)` |  | ✓ | 成交率 |
| 20 | `completed_order_count` | `bigint(10)` |  | ✗ | 完单量 |
| 21 | `completion_rate_after_response` | `decimal(10,4)` |  | ✓ | 应答后完单率 |
| 22 | `gmv` | `decimal(15,4)` |  | ✓ | GMV（成交总额） |
| 23 | `average_order_price` | `decimal(10,4)` |  | ✓ | 单均价 |
| 24 | `created_time` | `datetime` |  | ✗ | 创建时间 |
| 25 | `updated_time` | `datetime` |  | ✗ | 更新时间 |

---

## honghu_time_split_data

**宏鹄订单运力分时-供需分时明细数据表**  |  24 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `brand_name` | `varchar(20)` |  | ✓ | 品牌名称 |
| 3 | `date_day` | `varchar(20)` |  | ✗ | 日期（天） |
| 4 | `city_name` | `varchar(20)` |  | ✗ | 城市名称 |
| 5 | `hour` | `tinyint(3) unsigned` |  | ✗ | 小时（0-23） |
| 6 | `passenger_order_count` | `int(10) unsigned` |  | ✗ | 乘客发单量 |
| 7 | `fold_rate` | `decimal(10,6)` |  | ✓ | 折叠率 |
| 8 | `match_count` | `int(10) unsigned` |  | ✗ | 匹配量 |
| 9 | `match_rate` | `decimal(10,6)` |  | ✓ | 匹配率 |
| 10 | `response_count` | `int(10) unsigned` |  | ✗ | 应答量 |
| 11 | `response_rate` | `decimal(10,6)` |  | ✓ | 应答率 |
| 12 | `completed_order_count` | `int(10) unsigned` |  | ✗ | 完单量 |
| 13 | `cancel_count_after_response` | `int(10) unsigned` |  | ✗ | 应答后取消量 |
| 14 | `cancel_rate_after_response` | `decimal(10,6)` |  | ✓ | 应答后取消率 |
| 15 | `transaction_rate` | `decimal(10,6)` |  | ✓ | 成交率 |
| 16 | `completed_driver_count` | `int(10) unsigned` |  | ✗ | 完单司机数 |
| 17 | `online_driver_count` | `int(10) unsigned` |  | ✗ | 在线司机数 |
| 18 | `serving_driver_count` | `int(10) unsigned` |  | ✗ | 服务中司机数 |
| 19 | `load_rate` | `decimal(10,6)` |  | ✓ | 负载率 |
| 20 | `gmv` | `decimal(15,2)` |  | ✗ | GMV（成交总额） |
| 21 | `online_duration_hour` | `decimal(10,2)` |  | ✗ | 在线时长（小时） |
| 22 | `online_duration_old_hour` | `decimal(10,2)` |  | ✗ | 在线时长(旧)（小时） |
| 23 | `created_time` | `datetime` |  | ✗ | 创建时间 |
| 24 | `updated_time` | `datetime` |  | ✗ | 更新时间 |

---

## honghu_xf_driver_data

****  |  8 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ | id |
| 2 | `brand_name` | `varchar(64)` |  | ✗ | 品牌名称 |
| 3 | `date_day` | `varchar(32)` |  | ✗ | 日期 |
| 4 | `city_name` | `varchar(64)` |  | ✗ | 日期 |
| 5 | `xf_driver_count` | `int(11)` |  | ✓ | 先锋司机数 |
| 6 | `xf_driver_out_rate` | `decimal(10,2)` |  | ✓ | 先锋司机出车率 |
| 7 | `created_time` | `datetime` |  | ✗ | 创建时间 |
| 8 | `updated_time` | `datetime` |  | ✗ | 更新时间 |

---

## operator_brand

**运营主体-品牌名称城市对照表**  |  10 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | 🔑 PRI | ✗ |  |
| 2 | `operator_entity` | `varchar(24)` |  | ✗ | 运营主体 |
| 3 | `brand_name` | `varchar(24)` | 📇 MUL | ✗ | 品牌名称 |
| 4 | `city_name` | `varchar(24)` |  | ✗ | 运营城市 |
| 5 | `contact_person` | `varchar(24)` |  | ✓ | 对接人 |
| 6 | `open_city_date` | `datetime` |  | ✓ | 开城日期 |
| 7 | `create_time` | `datetime` |  | ✓ | 创建时间 |
| 8 | `update_time` | `datetime` |  | ✓ | 更新时间 |
| 9 | `update_by` | `varchar(24)` |  | ✓ | 更新人 |
| 10 | `create_by` | `varchar(24)` |  | ✓ | 创建人 |

---

## order_real_time_data

**订单实时累计数据表**  |  44 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | 🔑 PRI | ✗ | 主键ID |
| 2 | `tenant_name` | `varchar(20)` |  | ✓ | 租户名称 |
| 3 | `tenant_id` | `varchar(20)` |  | ✓ | 租户id |
| 4 | `datae_column_b4276e28f8_day_real` | `date` |  | ✓ | 数据日期 |
| 5 | `cal_7202039077` | `bigint(20)` |  | ✓ | 匹配数 |
| 6 | `cal_eee801eeed` | `bigint(20)` |  | ✓ | 应答数 |
| 7 | `cal_6bb0fc3c10` | `bigint(20)` |  | ✓ | 完单数 |
| 8 | `cal_d2b0e03aea` | `bigint(20)` |  | ✓ | 应答后司机取消数 |
| 9 | `cal_43d414f91f` | `bigint(20)` |  | ✓ | 应答后乘客取消数 |
| 10 | `cal_7adff81b3c` | `bigint(20)` |  | ✓ | 乘客发单数 |
| 11 | `cal_8c37dbc1e0` | `decimal(10,6)` |  | ✓ | 匹配率 |
| 12 | `cal_897d7954b0` | `decimal(10,6)` |  | ✓ | 应答后司机取消率 |
| 13 | `cal_9354d51f74` | `decimal(10,6)` |  | ✓ | 应答后乘客取消率 |
| 14 | `cal_794655f35b` | `decimal(10,6)` |  | ✓ | 应答率 |
| 15 | `cal_7eee019f5d` | `decimal(10,6)` |  | ✓ | 成交率 |
| 16 | `cal_b6c66a2567` | `decimal(16,6)` |  | ✓ | 应答后司乘取消率 |
| 17 | `relative_12d05a9353fea1f154b3571ba67fcb86` | `decimal(16,8)` |  | ✓ | 匹配数日环比 |
| 18 | `relative_00136b3ddd118e09d4221f1917ceb240` | `decimal(16,8)` |  | ✓ | 匹配数周同比 |
| 19 | `relative_ff86147813ac885aeb148f22fceaf666` | `decimal(16,8)` |  | ✓ | 应答数日环比 |
| 20 | `relative_70b60918b3b7bb5b880d1d2b18ead645` | `decimal(16,8)` |  | ✓ | 应答数周同比 |
| 21 | `relative_3fa7711ecda0d122fd7e6c650b5cc534` | `decimal(16,8)` |  | ✓ | 完单数日环比 |
| 22 | `relative_d29f19ca16f3618a2c3d558d78b73446` | `decimal(16,8)` |  | ✓ | 完单数周同比 |
| 23 | `relative_9d47de064151c8e5e064e39f87cfe9c3` | `decimal(16,8)` |  | ✓ | 应答后司机取消数日环比 |
| 24 | `relative_00aaff3a627d6b034b6a033bf1543e45` | `decimal(16,8)` |  | ✓ | 应答后司机取消数周同比 |
| 25 | `relative_25e01068e35ee696d874d83155648baa` | `decimal(16,8)` |  | ✓ | 应答后乘客取消数日环比 |
| 26 | `relative_cec74b3ff1b7dad04138fac942c6d620` | `decimal(16,8)` |  | ✓ | 应答后乘客取消数周同比 |
| 27 | `relative_754575dcc0a19a6a2f02378a1dd48dca` | `decimal(16,8)` |  | ✓ | 乘客发单数日环比 |
| 28 | `relative_a89886fde4d3a1c830bbb8184a816b18` | `decimal(16,8)` |  | ✓ | 乘客发单数周同比 |
| 29 | `relative_14b81b2ae191687498f221a3632ce48b` | `decimal(16,8)` |  | ✓ | 匹配率日环比差值 |
| 30 | `relative_86b9193b8afaad1bac24dc32875ace99` | `decimal(16,8)` |  | ✓ | 匹配率周同比差值 |
| 31 | `relative_fc7f4f4407ca991955377a501e0348f9` | `decimal(16,8)` |  | ✓ | 应答后司机取消率日环比差值 |
| 32 | `relative_ac6a8a707588b655a6f61b5e33d618bf` | `decimal(16,8)` |  | ✓ | 应答后司机取消率周同比差值 |
| 33 | `relative_c16e340a5722b13d3b510d40f7841c9b` | `decimal(16,8)` |  | ✓ | 应答后乘客取消率日环比差值 |
| 34 | `relative_8a7e92d3b42eb185d66d475334e017b7` | `decimal(16,8)` |  | ✓ | 应答后乘客取消率周同比差值 |
| 35 | `relative_e9d89cdd755a64e5b78d9455c9feea13` | `decimal(16,8)` |  | ✓ | 应答率日环比差值 |
| 36 | `relative_c8d6e2ed6cdb1f0abab2a39e0cc126a9` | `decimal(16,8)` |  | ✓ | 应答率周同比差值 |
| 37 | `relative_dc7092755aaae6539c794f91d1d7946f` | `decimal(16,8)` |  | ✓ | 成交率日环比差值 |
| 38 | `relative_0bde2cb112bca4a2cdabfb27451fbe39` | `decimal(16,8)` |  | ✓ | 成交率周同比差值 |
| 39 | `relative_634dd09ded5b61afe46b9939cc80ebff` | `decimal(16,8)` |  | ✓ | 应答后司乘取消率日环比差值 |
| 40 | `relative_f45640343d9deea599a3d205bea72f93` | `decimal(16,8)` |  | ✓ | 应答后司乘取消率周同比差值 |
| 41 | `pull_time` | `varchar(60)` |  | ✓ | 拉取数据时间 |
| 42 | `time_period` | `int(10)` |  | ✓ | 数据时间段（到时） |
| 43 | `created_time` | `datetime` |  | ✓ | 创建时间 |
| 44 | `updated_time` | `datetime` |  | ✓ | 更新时间 |
