# dataReporting 数据库表结构目录

> 生成时间：2026-06-30T16:37:07.273265+08:00  |  数据库：dataReporting  |  共 19 张表

---

## 目录

1. [activity_data](#activity-data) — 活动信息主表
2. [answer_rate_data](#answer-rate-data) — 接起率数据表
3. [brand_city_tr_data](#brand-city-tr-data) — 品牌城市TR值配置表
4. [card_data](#card-data) — 免佣卡信息表
5. [driver_real_time_data](#driver-real-time-data) — 运力实时累计数据表
6. [honghu_activity_marketing_data](#honghu-activity-marketing-data) — 宏鹄活动营销数据表
7. [honghu_capacity_data](#honghu-capacity-data) — 宏鹄运力数据离线看板-运力数据表
8. [honghu_check_data](#honghu-check-data) — 宏鹄数据校验表
9. [honghu_coupon_marketing_data](#honghu-coupon-marketing-data) — 宏鹄卡券营销数据表
10. [honghu_data_connect](#honghu-data-connect) — 鸿鹄数据对接列表
11. [honghu_driver_evaluation_data](#honghu-driver-evaluation-data) — 宏鹄司机考核数据表
12. [honghu_order_data](#honghu-order-data) — 宏鹄订单数据离线看板-订单数据表
13. [honghu_profit_data](#honghu-profit-data) — 宏鹄毛利数据表
14. [honghu_recon_data](#honghu-recon-data) — 账单对账数据表
15. [honghu_time_split_data](#honghu-time-split-data) — 宏鹄订单运力分时-供需分时明细数据表
16. [honghu_xf_driver_data](#honghu-xf-driver-data) — 先锋司机数据
17. [operator_brand](#operator-brand) — 运营主体-品牌名称城市对照表
18. [order_real_time_data](#order-real-time-data) — 订单实时累计数据表
19. [transport_data_report](#transport-data-report) — 鸿鹄传输数据统计明细

---

## activity_data

**活动信息主表**  |  28 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `varchar(32)` | `PRI` | 否 | 活动ID（唯一标识） |
| 2 | `operator_entity` | `varchar(100)` |  | 是 | 运营主体 |
| 3 | `business_name` | `varchar(100)` | `PRI` | 否 | 商家名称 |
| 4 | `city` | `varchar(64)` | `PRI` | 否 | 城市 |
| 5 | `contact_person` | `varchar(64)` |  | 是 | 对接人 |
| 6 | `title` | `varchar(255)` |  | 是 | 活动标题 |
| 7 | `status` | `int(2)` |  | 是 | 活动状态 |
| 8 | `channel_id` | `int(2)` |  | 是 | 渠道ID |
| 9 | `brand_id` | `varchar(32)` |  | 是 | 品牌ID |
| 10 | `is_join_subsidy` | `int(2)` |  | 是 | 是否参与补贴 |
| 11 | `city_ids` | `varchar(255)` |  | 是 | 活动覆盖城市ID列表 |
| 12 | `content` | `text` |  | 是 | 活动内容详情JSON |
| 13 | `subsidy_type` | `int(2)` |  | 是 | 补贴类型 |
| 14 | `tpl_id` | `varchar(32)` |  | 是 | 模板ID |
| 15 | `creator` | `varchar(50)` |  | 是 | 活动创建方 |
| 16 | `auditor` | `varchar(50)` |  | 是 | 审核方 |
| 17 | `start_time` | `datetime` |  | 是 | 活动开始时间 |
| 18 | `end_time` | `datetime` |  | 是 | 活动结束时间 |
| 19 | `invest_end_time` | `datetime` |  | 是 | 报名截止时间 |
| 20 | `project_no` | `varchar(64)` |  | 是 | 项目编号 |
| 21 | `project_name` | `varchar(255)` |  | 是 | 项目名称 |
| 22 | `create_time` | `datetime` |  | 是 | 活动创建时间 |
| 23 | `create_source` | `varchar(50)` |  | 是 | 创建来源 |
| 24 | `extra` | `text` |  | 是 | 额外扩展信息 |
| 25 | `is_additional_join` | `tinyint(4)` |  | 是 | 是否额外参与 |
| 26 | `create_source_desc` | `varchar(50)` |  | 是 | 创建来源描述 |
| 27 | `gmt_create` | `datetime` |  | 是 | 数据入库时间 |
| 28 | `gmt_update` | `datetime` |  | 是 | 数据更新时间 |

## answer_rate_data

**接起率数据表**  |  10 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 主键ID |
| 2 | `tenant_id` | `varchar(64)` | `MUL` | 否 | 租户ID |
| 3 | `tenant_name` | `varchar(128)` |  | 否 | 租户名称 |
| 4 | `answer_rate` | `decimal(10,6)` |  | 是 | 接起率（cal_f60f0b76d0940f7a89df24a5518c1279字段） |
| 5 | `incoming_count` | `int(11)` |  | 是 | 进线量（datae_column_a48952bb8a_sum字段） |
| 6 | `answered_count` | `int(11)` |  | 是 | 接起量（datae_column_045add6dce_sum字段） |
| 7 | `data_date` | `date` | `MUL` | 是 | 数据日期 |
| 8 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 9 | `pull_time` | `datetime` |  | 是 | 拉取时间 |
| 10 | `updated_time` | `datetime` |  | 是 | 修改时间 |

## brand_city_tr_data

**品牌城市TR值配置表**  |  7 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | `PRI` | 否 | 主键ID |
| 2 | `date_day` | `varchar(50)` | `MUL` | 是 | 日期 |
| 3 | `brand_name` | `varchar(100)` |  | 是 | 品牌名称 |
| 4 | `city_name` | `varchar(100)` |  | 是 | 城市名称 |
| 5 | `tr_value` | `decimal(10,2)` |  | 是 | TR值（百分比，如：15.5 表示 15.5%） |
| 6 | `create_time` | `datetime` |  | 是 | 创建时间 |
| 7 | `update_time` | `datetime` |  | 是 | 更新时间 |

## card_data

**免佣卡信息表**  |  30 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `varchar(32)` | `PRI` | 否 | 免佣卡ID |
| 2 | `operator_entity` | `varchar(100)` |  | 是 | 运营主体 |
| 3 | `business_name` | `varchar(100)` | `PRI` | 否 | 商家名称 |
| 4 | `city` | `varchar(64)` | `PRI` | 否 | 城市 |
| 5 | `contact_person` | `varchar(64)` |  | 是 | 对接人 |
| 6 | `title` | `varchar(255)` |  | 是 | 免佣卡标题 |
| 7 | `status` | `varchar(10)` |  | 是 | 状态码 |
| 8 | `channel_id` | `varchar(32)` |  | 是 | 渠道ID |
| 9 | `tpl_id` | `varchar(32)` |  | 是 | 模板ID |
| 10 | `allocation_rules` | `text` |  | 是 | 分配规则 |
| 11 | `content` | `text` |  | 是 | 免佣卡详情JSON字符串 |
| 12 | `brand_id` | `varchar(32)` |  | 是 | 品牌ID |
| 13 | `city_ids` | `varchar(255)` |  | 是 | 适用城市ID列表 |
| 14 | `subsidy_type` | `varchar(10)` |  | 是 | 补贴类型 |
| 15 | `creator` | `varchar(50)` |  | 是 | 创建人 |
| 16 | `auditor` | `varchar(50)` |  | 是 | 审核人 |
| 17 | `sale_start_time` | `datetime` |  | 是 | 销售开始时间 |
| 18 | `sale_end_time` | `datetime` |  | 是 | 销售结束时间 |
| 19 | `effect_start_time` | `datetime` |  | 是 | 生效开始时间 |
| 20 | `effect_end_time` | `datetime` |  | 是 | 生效结束时间 |
| 21 | `project_no` | `varchar(64)` |  | 是 | 项目编号 |
| 22 | `project_name` | `varchar(255)` |  | 是 | 项目名称 |
| 23 | `invest_end_time` | `datetime` |  | 是 | 投资结束时间 |
| 24 | `is_join_subsidy` | `varchar(10)` |  | 是 | 是否参与补贴 |
| 25 | `extra` | `text` |  | 是 | 额外信息 |
| 26 | `get_type` | `varchar(32)` |  | 是 | 获取方式 |
| 27 | `stock` | `int(11)` |  | 是 | 库存数量 |
| 28 | `is_additional_join` | `tinyint(4)` |  | 是 | 是否额外参与 |
| 29 | `gmt_create` | `datetime` |  | 是 | 创建时间 |
| 30 | `gmt_update` | `datetime` |  | 是 | 更新时间 |

## driver_real_time_data

**运力实时累计数据表**  |  23 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 主键ID |
| 2 | `tenant_name` | `varchar(20)` |  | 是 | 租户名称 |
| 3 | `tenant_id` | `varchar(20)` |  | 是 | 租户id |
| 4 | `datae_column_bc7a384cd7_day_real` | `date` |  | 是 | 数据日期 |
| 5 | `cal_42b6ccdb9832a04000d13c0b00a8f365` | `bigint(20)` |  | 是 | 匹配司机数(data_one_ident=3) |
| 6 | `cal_7050206267d5d6f983310c0fd15ebc9a` | `bigint(20)` |  | 是 | 完单司机数(data_one_ident=7) |
| 7 | `cal_f26aa9c3cef567bbf2f68eb01a671790` | `bigint(20)` |  | 是 | 在线司机数(data_one_ident=101) |
| 8 | `cal_2bf40e137f207dce4e82d799ad25b0ac` | `bigint(20)` |  | 是 | 服务中司机数(data_one_ident=102) |
| 9 | `cal_ebfde248b6edb7171b6b34ef0deff019` | `decimal(16,6)` |  | 是 | 负载率(服务中司机数/在线司机数) |
| 10 | `relative_2b4be74799e3f5a18efbfd7fc014cae4` | `decimal(16,8)` |  | 是 | 匹配司机数日环比 |
| 11 | `relative_c4269c08cfecae12e494e58ade692f07` | `decimal(16,8)` |  | 是 | 匹配司机数周同比 |
| 12 | `relative_3c49d0448125ade5c282985aad816a74` | `decimal(16,8)` |  | 是 | 完单司机数日环比 |
| 13 | `relative_15da124c19ecf81f9c10a5e8bbfe3fa3` | `decimal(16,8)` |  | 是 | 完单司机数周同比 |
| 14 | `relative_6efbe152ef498f644de1cd92f17d6240` | `decimal(16,8)` |  | 是 | 在线司机数日环比 |
| 15 | `relative_63b6e1459f39fceb47cd0637c9242c57` | `decimal(16,8)` |  | 是 | 在线司机数周同比 |
| 16 | `relative_d8c1ebfee6e6c021aab2e04fa39688f7` | `decimal(16,8)` |  | 是 | 服务中司机数日环比 |
| 17 | `relative_fd7ecc482b21fc3c61b3ee0b1acbcf16` | `decimal(16,8)` |  | 是 | 服务中司机数周同比 |
| 18 | `relative_6ee128f766d78334d53820d319510f3b` | `decimal(16,8)` |  | 是 | 负载率日环比差值 |
| 19 | `relative_b6b92d0590924d95285b2c73b2d33c5f` | `decimal(16,8)` |  | 是 | 负载率周同比差值 |
| 20 | `pull_time` | `varchar(60)` |  | 是 | 拉取数据时间 |
| 21 | `time_period` | `int(2)` |  | 是 | 数据时间段（到时） |
| 22 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 23 | `updated_time` | `datetime` |  | 是 | 更新时间 |

## honghu_activity_marketing_data

**宏鹄活动营销数据表**  |  30 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(11)` | `PRI` | 否 | 主键ID |
| 2 | `date_day` | `varchar(20)` |  | 否 | 统计日期（天） |
| 3 | `brand_name` | `varchar(20)` | `MUL` | 是 | 品牌名称 |
| 4 | `city_name` | `varchar(20)` |  | 是 | 城市名称 |
| 5 | `activity_id` | `bigint(20) unsigned` |  | 是 | 活动ID（唯一标识） |
| 6 | `activity_name` | `varchar(50)` |  | 是 | 活动名称 |
| 7 | `activity_start_date` | `date` |  | 是 | 活动开始日期 |
| 8 | `activity_end_date` | `date` |  | 是 | 活动结束日期 |
| 9 | `reward_template` | `varchar(20)` |  | 是 | 奖励模板类型 |
| 10 | `subsidy_type` | `varchar(20)` |  | 是 | 补贴类型 |
| 11 | `creator` | `varchar(20)` |  | 是 | 活动创建人 |
| 12 | `reviewer` | `varchar(20)` |  | 是 | 活动审核人 |
| 13 | `merchant_share_ratio` | `decimal(8,6)` |  | 是 | 商家承担比例（0-1） |
| 14 | `agent_id` | `int(10) unsigned` |  | 是 | 代理商ID（当前均为0） |
| 15 | `agent_name` | `varchar(50)` |  | 是 | 代理商名称（当前无数据） |
| 16 | `agent_share_ratio` | `decimal(8,6)` |  | 是 | 代理商承担比例（当前均为0） |
| 17 | `pred_rate` | `decimal(10,4)` |  | 是 | 预测b补率 |
| 18 | `completed_order_count` | `int(10) unsigned` |  | 是 | 活动完成订单数 |
| 19 | `completed_user_count` | `int(10) unsigned` |  | 是 | 活动完单人数 |
| 20 | `awarded_user_count` | `int(10) unsigned` |  | 是 | 活动获奖人数 |
| 21 | `completed_order_amount` | `varchar(255)` |  | 是 | 总订单GMV |
| 22 | `award_rate` | `decimal(10,6)` |  | 是 | 活动获奖率（获奖人数/完单人数） |
| 23 | `total_reward_amount` | `decimal(10,4)` |  | 是 | 活动总奖励金额（元） |
| 24 | `platform_subsidy_amount` | `decimal(10,4)` |  | 是 | 平台补贴金额（元） |
| 25 | `honghu_subsidy_amount` | `decimal(10,4)` |  | 是 | 宏鹄补贴金额（元） |
| 26 | `merchant_subsidy_amount` | `decimal(10,4)` |  | 是 | 商家补贴金额（元） |
| 27 | `agent_bear_amount` | `decimal(10,4)` |  | 是 | 代理商承担金额（元，当前均为0） |
| 28 | `cooperator_bear_amount` | `decimal(10,4)` |  | 是 | 合作运营方承担金额（元） |
| 29 | `created_time` | `datetime` |  | 是 | 数据创建时间 |
| 30 | `updated_time` | `datetime` |  | 是 | 数据更新时间 |

## honghu_capacity_data

**宏鹄运力数据离线看板-运力数据表**  |  26 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(16)` | `PRI` | 否 | 主键ID |
| 2 | `brand_name` | `varchar(20)` |  | 否 | 品牌名称 |
| 3 | `date_day` | `varchar(20)` |  | 否 | 日期（天） |
| 4 | `city_name` | `varchar(20)` |  | 否 | 城市名称 |
| 5 | `supplier` | `varchar(50)` |  | 是 | 供应商名称 |
| 6 | `agent` | `varchar(50)` |  | 是 | 代理商名称 |
| 7 | `peak_online_driver_count` | `int(10) unsigned` |  | 否 | 峰期在线司机数 |
| 8 | `peak_valid_driver_count` | `int(10) unsigned` |  | 否 | 峰期有效司机数 |
| 9 | `peak_valid_driver_conversion_rate` | `decimal(10,4)` |  | 是 | 峰期有效司机转化率 |
| 10 | `online_driver_count` | `int(10) unsigned` |  | 否 | 在线司机数 |
| 11 | `first_completion_driver_count` | `int(10) unsigned` |  | 否 | 首次完单司机数 |
| 12 | `valid_driver_count` | `int(10) unsigned` |  | 否 | 有效司机数 |
| 13 | `valid_driver_conversion_rate` | `decimal(10,4)` |  | 是 | 有效司机转化率 |
| 14 | `response_driver_count` | `int(10) unsigned` |  | 否 | 应答司机数 |
| 15 | `completion_driver_count` | `int(10) unsigned` |  | 否 | 完单司机数 |
| 16 | `online_duration_hour` | `decimal(10,2)` |  | 否 | 在线时长（小时） |
| 17 | `online_duration_old_hour` | `decimal(10,2)` |  | 否 | 在线时长(旧)（小时） |
| 18 | `service_duration_hour` | `decimal(10,2)` |  | 否 | 服务时长（小时） |
| 19 | `driver_completion_rate` | `decimal(10,4)` |  | 是 | 司机完单率 |
| 20 | `per_capita_online_duration_hour` | `decimal(10,2)` |  | 否 | 人均在线时长（小时） |
| 21 | `service_duration_ratio` | `decimal(10,2)` |  | 是 | 服务时长占比 |
| 22 | `per_capita_completion_count` | `decimal(10,2)` |  | 是 | 人均完单量 |
| 23 | `completion_per_hour` | `decimal(10,2)` |  | 是 | 每小时完单量 |
| 24 | `revenue_per_hour` | `decimal(10,2)` |  | 是 | 每小时收入（元） |
| 25 | `created_time` | `datetime` |  | 否 | 创建时间 |
| 26 | `updated_time` | `datetime` |  | 否 | 更新时间 |

## honghu_check_data

**宏鹄数据校验表**  |  31 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 主键ID |
| 2 | `date_day` | `varchar(50)` | `MUL` | 是 | 日期 |
| 3 | `city_id` | `bigint(20)` | `MUL` | 是 | 城市ID |
| 4 | `city_name` | `varchar(100)` |  | 是 | 城市名称 |
| 5 | `brand_id` | `bigint(20)` | `MUL` | 是 | 品牌ID |
| 6 | `brand_name` | `varchar(100)` |  | 是 | 品牌名称 |
| 7 | `passenger_order_count` | `bigint(20)` |  | 是 | 乘客发单量 |
| 8 | `dispatch_count` | `bigint(20)` |  | 是 | 播单量 |
| 9 | `match_count` | `bigint(20)` |  | 是 | 匹配量 |
| 10 | `response_count` | `bigint(20)` |  | 是 | 应答量 |
| 11 | `completed_order_count` | `bigint(20)` |  | 是 | 完单数 |
| 12 | `pre_response_cancel_count` | `bigint(20)` |  | 是 | 应答前取消订单量 |
| 13 | `post_response_passenger_cancel_count` | `bigint(20)` |  | 是 | 应答后乘客取消量 |
| 14 | `post_response_driver_cancel_count` | `bigint(20)` |  | 是 | 应答后司机取消量 |
| 15 | `driver_online_hours` | `decimal(10,2)` |  | 是 | 司机在线时长h |
| 16 | `online_driver_count` | `bigint(20)` |  | 是 | 在线司机数 |
| 17 | `completed_driver_count` | `bigint(20)` |  | 是 | 完单司机数 |
| 18 | `peak_online_driver_count` | `bigint(20)` |  | 是 | 峰期在线司机数 |
| 19 | `peak_active_driver_count` | `bigint(20)` |  | 是 | 峰期有效司机数 |
| 20 | `active_driver_count` | `bigint(20)` |  | 是 | 有效司机数 |
| 21 | `approved_driver_count` | `bigint(20)` |  | 是 | 审核通过司机数 |
| 22 | `first_online_driver_count` | `bigint(20)` |  | 是 | 首次在线司机数 |
| 23 | `first_completed_driver_count` | `bigint(20)` |  | 是 | 首次完单司机数 |
| 24 | `gmv` | `decimal(15,2)` |  | 是 | gmv |
| 25 | `total_b_subsidy_amount` | `decimal(15,2)` |  | 是 | 总b补金额 |
| 26 | `merchant_b_subsidy_amount` | `decimal(15,2)` |  | 是 | 商家b补金额 |
| 27 | `total_commission` | `decimal(15,2)` |  | 是 | 总抽佣 |
| 28 | `brand_commission` | `decimal(15,2)` |  | 是 | 品牌抽佣 |
| 29 | `card_merchant_income_amount` | `decimal(15,2)` |  | 是 | 售卡商家收入金额 |
| 30 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 31 | `updated_time` | `datetime` |  | 是 | 更新时间 |

## honghu_coupon_marketing_data

**宏鹄卡券营销数据表**  |  35 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(11)` | `PRI` | 否 | 主键ID |
| 2 | `date_day` | `varchar(20)` |  | 否 | 统计日期（天） |
| 3 | `city_name` | `varchar(20)` |  | 否 | 城市名称 |
| 4 | `brand_name` | `varchar(20)` | `MUL` | 否 | 品牌名称（当前为飞嘀尊驾） |
| 5 | `agent_id` | `int(10) unsigned` |  | 否 | 代理商ID（当前均为0） |
| 6 | `agent_name` | `varchar(50)` |  | 是 | 代理商名称（当前无数据） |
| 7 | `product_id` | `int(10) unsigned` |  | 否 | 卡券商品ID（唯一标识） |
| 8 | `product_name` | `varchar(50)` |  | 否 | 卡券商品名称 |
| 9 | `effective_start_time` | `datetime` |  | 否 | 卡券生效开始时间（含时分秒） |
| 10 | `effective_end_time` | `datetime` |  | 否 | 卡券生效结束时间（含时分秒） |
| 11 | `coupon_template` | `varchar(20)` |  | 否 | 卡券模板类型（免佣卡/飞涨卡） |
| 12 | `subsidy_type` | `varchar(20)` |  | 否 | 补贴类型（商家独补/强制共补） |
| 13 | `coupon_type` | `varchar(64)` |  | 是 | 卡类型 |
| 14 | `coupon_tag` | `varchar(60)` |  | 是 | 卡标签 |
| 15 | `creator` | `varchar(40)` |  | 是 | 卡券创建人 |
| 16 | `reviewer` | `varchar(40)` |  | 是 | 卡券审核人 |
| 17 | `merchant_share_ratio` | `decimal(8,6)` |  | 否 | 商家承担比例（0-1） |
| 18 | `agent_share_ratio` | `decimal(8,6)` |  | 否 | 代理商承担比例（当前均为0） |
| 19 | `total_coupon_sales_revenue` | `decimal(10,2)` |  | 否 | 总券后售卡收入（元） |
| 20 | `platform_coupon_sales_revenue` | `decimal(10,2)` |  | 否 | 平台券后售卡收入（元） |
| 21 | `merchant_coupon_sales_revenue` | `decimal(10,2)` |  | 否 | 商家券后售卡收入（元） |
| 22 | `agent_coupon_sales_revenue` | `decimal(10,2)` |  | 否 | 代理商券后售卡收入（元，当前均为0） |
| 23 | `cooperator_coupon_sales_revenue` | `decimal(10,2)` |  | 否 | 合作运营商券后售卡收入（元，当前均为0） |
| 24 | `daily_card_purchase_count` | `int(10) unsigned` |  | 否 | 当日购卡人数 |
| 25 | `daily_verification_count` | `int(10) unsigned` |  | 否 | 当日核销人数 |
| 26 | `verification_order_count` | `int(10) unsigned` |  | 否 | 核销订单数 |
| 27 | `verification_order_gmv` | `decimal(12,2)` |  | 否 | 核销订单GMV（元） |
| 28 | `total_subsidy_amount` | `decimal(10,2)` |  | 否 | 总补贴金额（元） |
| 29 | `platform_subsidy_amount` | `decimal(10,2)` |  | 否 | 平台补贴金额（元） |
| 30 | `channel_subsidy_amount` | `decimal(10,2)` |  | 否 | 渠道补贴金额（元） |
| 31 | `merchant_subsidy_amount` | `decimal(10,2)` |  | 否 | 商家补贴金额（元） |
| 32 | `agent_subsidy_amount` | `decimal(10,2)` |  | 否 | 代理商补贴金额（元，当前均为0） |
| 33 | `cooperator_subsidy_amount` | `decimal(10,2)` |  | 否 | 合作运营商补贴金额（元，当前均为0） |
| 34 | `created_time` | `datetime` |  | 否 | 数据创建时间 |
| 35 | `updated_time` | `datetime` |  | 否 | 数据更新时间 |

## honghu_data_connect

**鸿鹄数据对接列表**  |  21 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 鸿鹄对接记录ID（接口返回的 id 字段，唯一） |
| 2 | `company_id` | `bigint(20)` | `MUL` | 是 | 公司ID |
| 3 | `city_id` | `int(11)` | `MUL` | 是 | 城市ID |
| 4 | `apply_time` | `varchar(50)` | `MUL` | 是 | 申请时间 |
| 5 | `license_type` | `int(11)` |  | 是 | 牌照类型 |
| 6 | `report_standard` | `varchar(50)` |  | 是 | 上报标准（jtb/bd） |
| 7 | `biz_status` | `int(11)` | `MUL` | 是 | 业务状态 |
| 8 | `status_fill_parameters` | `int(11)` |  | 是 | 填充参数状态（0否1是） |
| 9 | `status_fill_company_info` | `int(11)` |  | 是 | 填充公司信息状态（0否1是） |
| 10 | `status_fill_extend_data` | `int(11)` |  | 是 | 填充扩展数据状态（0否1是） |
| 11 | `status_fill_driver_tag` | `int(11)` |  | 是 | 填充司机标签状态（0否1是） |
| 12 | `finished_time` | `varchar(50)` |  | 是 | 完成时间 |
| 13 | `remarks` | `varchar(500)` |  | 是 | 备注 |
| 14 | `is_sync_immediately` | `int(11)` |  | 是 | 是否立即同步（0否1是） |
| 15 | `status` | `int(11)` |  | 是 | 状态 |
| 16 | `create_time` | `varchar(50)` |  | 是 | 创建时间 |
| 17 | `update_time` | `varchar(50)` |  | 是 | 更新时间 |
| 18 | `apply_status` | `int(11)` |  | 是 | 申请状态 |
| 19 | `progress` | `int(11)` |  | 是 | 进度 |
| 20 | `pull_time` | `varchar(50)` |  | 是 | 拉取时间（数据入库时间） |
| 21 | `brand_name` | `varchar(100)` | `MUL` | 是 | 品牌名称（通过租户映射关联） |

## honghu_driver_evaluation_data

**宏鹄司机考核数据表**  |  41 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(11)` | `PRI` | 否 | 主键ID |
| 2 | `brand_name` | `varchar(64)` | `MUL` | 是 | 品牌名称 |
| 3 | `date_day` | `varchar(32)` | `MUL` | 是 | 日期 |
| 4 | `driver_id` | `varchar(64)` | `MUL` | 是 | 司机ID |
| 5 | `driver_name` | `varchar(64)` |  | 是 | 司机姓名 |
| 6 | `driver_lifecycle` | `varchar(32)` |  | 是 | 司机生命周期 |
| 7 | `activation_time` | `varchar(64)` |  | 是 | 激活时间 |
| 8 | `driver_status` | `varchar(32)` |  | 是 | 司机运营状态 |
| 9 | `register_city` | `varchar(64)` |  | 是 | 注册运营城市 |
| 10 | `first_completed_order_time` | `varchar(64)` |  | 是 | 首次完单时间 |
| 11 | `last_completed_order_time` | `varchar(64)` |  | 是 | 最后完单时间 |
| 12 | `supplier` | `varchar(128)` |  | 是 | 所属供应商 |
| 13 | `agent` | `varchar(128)` |  | 是 | 所属代理商 |
| 14 | `fleet_name` | `varchar(128)` |  | 是 | 自营车队名称 |
| 15 | `is_xf_driver` | `int(11)` |  | 是 | 是否先锋司机(0:否,1:是) |
| 16 | `is_king_xf_driver` | `int(11)` |  | 是 | 是否王者先锋司机(0:否,1:是) |
| 17 | `online_hours` | `decimal(12,4)` |  | 是 | 在线时长(小时) |
| 18 | `service_duration_rate` | `decimal(10,6)` |  | 是 | 服务时长占比 |
| 19 | `peak_online_rate` | `decimal(10,6)` |  | 是 | 高峰期在线时长占比 |
| 20 | `peak_service_rate` | `decimal(10,6)` |  | 是 | 高峰期服务时长占比 |
| 21 | `response_count` | `int(11)` |  | 是 | 应答量 |
| 22 | `completed_order_count` | `int(11)` |  | 是 | 完单量 |
| 23 | `driver_cancel_count` | `int(11)` |  | 是 | 应答后司机取消订单数 |
| 24 | `passenger_cancel_count` | `int(11)` |  | 是 | 应答后乘客取消订单数 |
| 25 | `cs_cancel_count` | `int(11)` |  | 是 | 应答后客服取消订单数 |
| 26 | `completion_rate` | `decimal(10,6)` |  | 是 | 完单率 |
| 27 | `paid_order_count` | `int(11)` |  | 是 | 完成支付订单量 |
| 28 | `passenger_amount` | `decimal(14,4)` |  | 是 | 乘客应付金额 |
| 29 | `driver_amount` | `decimal(14,4)` |  | 是 | 司机应收金额 |
| 30 | `zero_commission_amount` | `decimal(14,4)` |  | 是 | 应付0tr免佣奖金金额 |
| 31 | `b_subsidy_amount` | `decimal(14,4)` |  | 是 | B补金额 |
| 32 | `zero_commiss_amount` | `decimal(14,4)` |  | 是 | 0tr免佣奖金金额 |
| 33 | `other_reward_amount` | `decimal(14,4)` |  | 是 | 其他奖励金额 |
| 34 | `work_days` | `int(11)` |  | 是 | 出车天数 |
| 35 | `completed_days` | `int(11)` |  | 是 | 完单天数 |
| 36 | `peak_online_hours` | `decimal(12,4)` |  | 是 | 活动高峰期在线时长(小时) |
| 37 | `last7_days_completion_rate` | `decimal(10,6)` |  | 是 | 近7日完单率 |
| 38 | `fulfillment_score` | `decimal(10,4)` |  | 是 | 履约分 |
| 39 | `last30_days_online_hours` | `decimal(12,4)` |  | 是 | 近30天在线时长(小时) |
| 40 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 41 | `updated_time` | `datetime` |  | 是 | 更新时间 |

## honghu_order_data

**宏鹄订单数据离线看板-订单数据表**  |  25 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(11)` | `PRI` | 否 | 主键ID |
| 2 | `brand_name` | `varchar(20)` | `MUL` | 否 | 品牌名称 |
| 3 | `date_day` | `varchar(20)` |  | 否 | 日期（天） |
| 4 | `city_name` | `varchar(20)` |  | 否 | 城市名称 |
| 5 | `traffic_channel` | `varchar(20)` |  | 否 | 流量渠道 |
| 6 | `order_type` | `varchar(10)` |  | 是 | 订单类型 |
| 7 | `passenger_order_count` | `bigint(10)` |  | 是 | 乘客发单量 |
| 8 | `no_capacity_fold_rate` | `decimal(10,4)` |  | 是 | 无运力折叠率 |
| 9 | `non_compliance_fold_rate` | `decimal(8,4)` |  | 是 | 执规考核不达标折叠率 |
| 10 | `match_count` | `bigint(10)` |  | 是 | 匹配量 |
| 11 | `response_count` | `bigint(10)` |  | 是 | 应答量 |
| 12 | `response_rate` | `decimal(10,4)` |  | 是 | 应答率 |
| 13 | `driver_cancel_count_after_response` | `bigint(10)` |  | 是 | 应答后司机取消量 |
| 14 | `driver_cancel_rate_after_response` | `decimal(10,4)` |  | 是 | 应答后司机取消率 |
| 15 | `passenger_cancel_count_after_response` | `bigint(10)` |  | 是 | 应答后乘客取消量 |
| 16 | `passenger_cancel_rate_after_response` | `decimal(10,4)` |  | 是 | 应答后乘客取消率 |
| 17 | `customer_service_close_count_after_response` | `bigint(10)` |  | 是 | 应答后客服关闭订单数 |
| 18 | `pk_success_rate` | `decimal(10,4)` |  | 是 | PK成功率 |
| 19 | `transaction_rate` | `decimal(10,4)` |  | 是 | 成交率 |
| 20 | `completed_order_count` | `bigint(10)` |  | 否 | 完单量 |
| 21 | `completion_rate_after_response` | `decimal(10,4)` |  | 是 | 应答后完单率 |
| 22 | `gmv` | `decimal(15,4)` |  | 是 | GMV（成交总额） |
| 23 | `average_order_price` | `decimal(10,4)` |  | 是 | 单均价 |
| 24 | `created_time` | `datetime` |  | 否 | 创建时间 |
| 25 | `updated_time` | `datetime` |  | 否 | 更新时间 |

## honghu_profit_data

**宏鹄毛利数据表**  |  22 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 主键ID |
| 2 | `brand_name` | `varchar(64)` | `MUL` | 是 | 品牌名称 |
| 3 | `date_day` | `varchar(32)` | `MUL` | 是 | 日期 |
| 4 | `city_name` | `varchar(64)` | `MUL` | 是 | 城市名称 |
| 5 | `completed_order_count` | `int(11)` |  | 是 | 完单数 |
| 6 | `merchant_gmv` | `decimal(18,2)` |  | 是 | 商家口径gmv |
| 7 | `merchant_profit_excl_commission` | `decimal(18,2)` |  | 是 | 商家口径毛利(不含返佣) |
| 8 | `merchant_profit_rate_excl_commission` | `decimal(18,6)` |  | 是 | 商家口径毛利率(不含返佣) |
| 9 | `merchant_profit_incl_commission` | `decimal(18,2)` |  | 是 | 商家口径毛利(含返佣) |
| 10 | `merchant_profit_rate_incl_commission` | `decimal(18,6)` |  | 是 | 商家口径毛利率(含返佣) |
| 11 | `merchant_tr_amount` | `decimal(18,2)` |  | 是 | 商家口径商家TR金额 |
| 12 | `merchant_tr` | `decimal(18,6)` |  | 是 | 商家口径商家TR |
| 13 | `merchant_b_subsidy` | `decimal(18,2)` |  | 是 | 商家B补 |
| 14 | `merchant_b_subsidy_rate` | `decimal(18,6)` |  | 是 | 商家口径B补率 |
| 15 | `merchant_c_subsidy` | `decimal(18,2)` |  | 是 | 商家C补 |
| 16 | `merchant_c_subsidy_rate` | `decimal(18,6)` |  | 是 | 商家口径C补率 |
| 17 | `merchant_b_card_income` | `decimal(18,2)` |  | 是 | 商家B端卡收入 |
| 18 | `merchant_b_card_income_rate` | `decimal(18,6)` |  | 是 | 商家口径B端卡收入率 |
| 19 | `commission_amount` | `decimal(18,2)` |  | 是 | 返佣金额 |
| 20 | `comprehensive_service_fee` | `decimal(18,2)` |  | 是 | 综合服务费 |
| 21 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 22 | `updated_time` | `datetime` |  | 是 | 更新时间 |

## honghu_recon_data

**账单对账数据表**  |  69 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 主键ID |
| 2 | `partition_date` | `varchar(32)` | `MUL` | 是 | 分区日期 |
| 3 | `order_id` | `varchar(128)` | `MUL` | 是 | 订单ID |
| 4 | `order_type` | `varchar(64)` |  | 是 | 订单类型 |
| 5 | `brand_model` | `varchar(64)` |  | 是 | 品牌模式 |
| 6 | `driver_id` | `varchar(64)` | `MUL` | 是 | 司机ID |
| 7 | `driver_name` | `varchar(128)` |  | 是 | 司机姓名 |
| 8 | `plate_number` | `varchar(64)` |  | 是 | 车牌号 |
| 9 | `passenger_id` | `varchar(64)` |  | 是 | 乘客id |
| 10 | `external_passenger_id` | `varchar(64)` |  | 是 | 外部乘客ID |
| 11 | `city_name` | `varchar(128)` | `MUL` | 是 | 城市名称 |
| 12 | `city_area_code` | `varchar(64)` |  | 是 | 城市区号 |
| 13 | `traffic_channel` | `varchar(128)` |  | 是 | 流量渠道 |
| 14 | `traffic_platform_order_id` | `varchar(128)` |  | 是 | 流量端订单ID |
| 15 | `departure_location` | `varchar(512)` |  | 是 | 出发地点 |
| 16 | `destination_location` | `varchar(512)` |  | 是 | 目的地点 |
| 17 | `agent_name` | `varchar(256)` |  | 是 | 代理商名称 |
| 18 | `supplier_name` | `varchar(256)` |  | 是 | 供应商名称 |
| 19 | `trip_start_time` | `datetime` |  | 是 | 行程开始时间 |
| 20 | `trip_end_time` | `datetime` |  | 是 | 行程结束时间 |
| 21 | `order_create_time` | `datetime` |  | 是 | 订单创建时间 |
| 22 | `order_complete_time` | `datetime` |  | 是 | 订单完成时间 |
| 23 | `order_pay_time` | `datetime` |  | 是 | 订单支付时间 |
| 24 | `tr_type` | `varchar(64)` |  | 是 | tr类型 |
| 25 | `driver_subsidy_b_type` | `varchar(64)` |  | 否 | 司机补贴_b补类型 |
| 26 | `driver_subsidy_merchant_account` | `decimal(18,2)` |  | 是 | 司机补贴_商家账户 |
| 27 | `real_time_split_type` | `varchar(64)` |  | 是 | 实时分账_分账类型 |
| 28 | `real_time_split_is_refund_split` | `varchar(4)` |  | 是 | 实时分账_是否取消费分账 |
| 29 | `invoice_issue_status` | `varchar(64)` |  | 是 | 发票开具状态 |
| 30 | `related_invoice_number` | `varchar(128)` |  | 是 | 关联发票号码 |
| 31 | `invoice_apply_amount` | `decimal(18,2)` |  | 是 | 申请开票金额 |
| 32 | `tax_amount` | `decimal(18,2)` |  | 是 | 税额 |
| 33 | `passenger_receivable_amount` | `decimal(18,2)` |  | 是 | 乘客应收_金额 |
| 34 | `passenger_receivable_advance` | `decimal(18,2)` |  | 是 | 乘客应收_代垫费 |
| 35 | `passenger_receivable_spring_service_fee` | `decimal(18,2)` |  | 是 | 乘客应收_春节服务费 |
| 36 | `passenger_receivable_adjustment_fee` | `decimal(18,2)` |  | 是 | 乘客应收_动调费 |
| 37 | `passenger_receivable_new_adjustment_fee` | `decimal(18,2)` |  | 是 | 乘客应收_新动调费(旺季供需)(单位:元) |
| 38 | `passenger_actual_received_amount` | `decimal(18,2)` |  | 是 | 乘客实收_金额 |
| 39 | `passenger_actual_received_fund` | `decimal(18,2)` |  | 是 | 乘客实收_资金 |
| 40 | `passenger_actual_received_advance` | `decimal(18,2)` |  | 是 | 乘客实收_代垫费 |
| 41 | `passenger_actual_received_spring_red_packet` | `decimal(18,2)` |  | 是 | 乘客实收_春节红包 |
| 42 | `passenger_actual_received_c_subsidy_hxp` | `decimal(18,2)` |  | 是 | 乘客实收_花小猪c补 |
| 43 | `passenger_actual_received_c_subsidy_brand` | `decimal(18,2)` |  | 是 | 乘客实收_品牌方c补 |
| 44 | `passenger_actual_received_c_subsidy_partner` | `decimal(18,2)` |  | 是 | 乘客实收_合作商c补 |
| 45 | `passenger_actual_received_adjustment_fee` | `decimal(18,2)` |  | 是 | 乘客实收_动调费 |
| 46 | `driver_subsidy_b_total` | `decimal(18,2)` |  | 是 | 司机补贴_b补总额 |
| 47 | `driver_subsidy_hxp_amount` | `decimal(18,2)` |  | 是 | 司机补贴_花小猪承担金额 |
| 48 | `driver_subsidy_traffic_platform_amount` | `decimal(18,2)` |  | 是 | 司机补贴流量平台承担金额 |
| 49 | `driver_subsidy_brand_amount` | `decimal(18,2)` |  | 是 | 司机补贴_品牌承担金额 |
| 50 | `driver_subsidy_partner_amount` | `decimal(18,2)` |  | 是 | 司机补贴_合作运营平台承担金额(元) |
| 51 | `driver_subsidy_unsplit_b_amount` | `decimal(18,2)` |  | 是 | 司机补贴_未成功拆分b补金额 |
| 52 | `driver_payable_online_share_amount` | `decimal(18,2)` |  | 是 | 司机应付_在线司机分成金额（不包含0tr） |
| 53 | `driver_payable_0tr_commission` | `decimal(18,2)` |  | 是 | 司机应付_0tr抽成 |
| 54 | `driver_payable_flying_card_subsidy` | `decimal(18,2)` |  | 是 | 司机应付_飞涨卡补贴金额 |
| 55 | `driver_payable_new_adjustment_fee` | `decimal(18,2)` |  | 是 | 司机应付_新动调费(旺季供需)(单位:元) |
| 56 | `real_time_split_total_five_parties` | `decimal(18,2)` |  | 是 | 实时分账_五方分账总金额 |
| 57 | `real_time_split_traffic_amount` | `decimal(18,2)` |  | 是 | 实时分账_流量方分账金额 |
| 58 | `real_time_split_brand_amount` | `decimal(18,2)` |  | 是 | 实时分账_品牌方分账金额 |
| 59 | `real_time_split_tech_service_fee` | `decimal(18,2)` |  | 是 | 实时分账_技术服务费金额 |
| 60 | `real_time_split_comprehensive_service_fee` | `decimal(18,2)` |  | 是 | 实时分账_综合服务费金额 |
| 61 | `real_time_split_driver_amount` | `decimal(18,2)` |  | 是 | 实时分账_司机分账金额 |
| 62 | `real_time_split_erqing_risk_fund` | `decimal(18,2)` |  | 是 | 实时分账_二清风险金 |
| 63 | `real_time_split_info_service_fee` | `decimal(18,2)` |  | 是 | 实时分账_信息服务费 |
| 64 | `real_time_split_adjustment_fee` | `decimal(18,2)` |  | 是 | 实时分账_动调费 |
| 65 | `passenger_estimated_distance_km` | `decimal(10,2)` |  | 是 | 乘客预估里程(单位:km) |
| 66 | `passenger_actual_distance_km` | `decimal(10,2)` |  | 是 | 乘客实际里程(单位:km) |
| 67 | `brand_name` | `varchar(128)` | `MUL` | 是 | 品牌名称 |
| 68 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 69 | `updated_time` | `datetime` |  | 是 | 更新时间 |

## honghu_time_split_data

**宏鹄订单运力分时-供需分时明细数据表**  |  24 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(11)` | `PRI` | 否 | 主键ID |
| 2 | `brand_name` | `varchar(20)` |  | 是 | 品牌名称 |
| 3 | `date_day` | `varchar(20)` |  | 否 | 日期（天） |
| 4 | `city_name` | `varchar(20)` |  | 否 | 城市名称 |
| 5 | `hour` | `tinyint(3) unsigned` |  | 否 | 小时（0-23） |
| 6 | `passenger_order_count` | `int(10) unsigned` |  | 否 | 乘客发单量 |
| 7 | `fold_rate` | `decimal(10,6)` |  | 是 | 折叠率 |
| 8 | `match_count` | `int(10) unsigned` |  | 否 | 匹配量 |
| 9 | `match_rate` | `decimal(10,6)` |  | 是 | 匹配率 |
| 10 | `response_count` | `int(10) unsigned` |  | 否 | 应答量 |
| 11 | `response_rate` | `decimal(10,6)` |  | 是 | 应答率 |
| 12 | `completed_order_count` | `int(10) unsigned` |  | 否 | 完单量 |
| 13 | `cancel_count_after_response` | `int(10) unsigned` |  | 否 | 应答后取消量 |
| 14 | `cancel_rate_after_response` | `decimal(10,6)` |  | 是 | 应答后取消率 |
| 15 | `transaction_rate` | `decimal(10,6)` |  | 是 | 成交率 |
| 16 | `completed_driver_count` | `int(10) unsigned` |  | 否 | 完单司机数 |
| 17 | `online_driver_count` | `int(10) unsigned` |  | 否 | 在线司机数 |
| 18 | `serving_driver_count` | `int(10) unsigned` |  | 否 | 服务中司机数 |
| 19 | `load_rate` | `decimal(10,6)` |  | 是 | 负载率 |
| 20 | `gmv` | `decimal(15,2)` |  | 否 | GMV（成交总额） |
| 21 | `online_duration_hour` | `decimal(10,2)` |  | 否 | 在线时长（小时） |
| 22 | `online_duration_old_hour` | `decimal(10,2)` |  | 否 | 在线时长(旧)（小时） |
| 23 | `created_time` | `datetime` |  | 否 | 创建时间 |
| 24 | `updated_time` | `datetime` |  | 否 | 更新时间 |

## honghu_xf_driver_data

**先锋司机数据**  |  8 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(11)` | `PRI` | 否 | id |
| 2 | `brand_name` | `varchar(64)` |  | 否 | 品牌名称 |
| 3 | `date_day` | `varchar(32)` |  | 否 | 日期 |
| 4 | `city_name` | `varchar(64)` |  | 否 | 日期 |
| 5 | `xf_driver_count` | `int(11)` |  | 是 | 先锋司机数 |
| 6 | `xf_driver_out_rate` | `decimal(10,2)` |  | 是 | 先锋司机出车率 |
| 7 | `created_time` | `datetime` |  | 否 | 创建时间 |
| 8 | `updated_time` | `datetime` |  | 否 | 更新时间 |

## operator_brand

**运营主体-品牌名称城市对照表**  |  11 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `int(11)` | `PRI` | 否 |  |
| 2 | `operator_entity` | `varchar(24)` |  | 否 | 运营主体 |
| 3 | `brand_name` | `varchar(24)` | `MUL` | 否 | 品牌名称 |
| 4 | `city_name` | `varchar(24)` |  | 否 | 运营城市 |
| 5 | `contact_person` | `varchar(24)` |  | 是 | 对接人 |
| 6 | `is_opening` | `char(1)` |  | 是 | 是否开城中（0代表否 1代表是） |
| 7 | `open_city_date` | `datetime` |  | 是 | 开城日期 |
| 8 | `create_time` | `datetime` |  | 是 | 创建时间 |
| 9 | `update_time` | `datetime` |  | 是 | 更新时间 |
| 10 | `update_by` | `varchar(24)` |  | 是 | 更新人 |
| 11 | `create_by` | `varchar(24)` |  | 是 | 创建人 |

## order_real_time_data

**订单实时累计数据表**  |  44 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 主键ID |
| 2 | `tenant_name` | `varchar(20)` |  | 是 | 租户名称 |
| 3 | `tenant_id` | `varchar(20)` |  | 是 | 租户id |
| 4 | `datae_column_b4276e28f8_day_real` | `date` |  | 是 | 数据日期 |
| 5 | `cal_7202039077` | `bigint(20)` |  | 是 | 匹配数 |
| 6 | `cal_eee801eeed` | `bigint(20)` |  | 是 | 应答数 |
| 7 | `cal_6bb0fc3c10` | `bigint(20)` |  | 是 | 完单数 |
| 8 | `cal_d2b0e03aea` | `bigint(20)` |  | 是 | 应答后司机取消数 |
| 9 | `cal_43d414f91f` | `bigint(20)` |  | 是 | 应答后乘客取消数 |
| 10 | `cal_7adff81b3c` | `bigint(20)` |  | 是 | 乘客发单数 |
| 11 | `cal_8c37dbc1e0` | `decimal(10,6)` |  | 是 | 匹配率 |
| 12 | `cal_897d7954b0` | `decimal(10,6)` |  | 是 | 应答后司机取消率 |
| 13 | `cal_9354d51f74` | `decimal(10,6)` |  | 是 | 应答后乘客取消率 |
| 14 | `cal_794655f35b` | `decimal(10,6)` |  | 是 | 应答率 |
| 15 | `cal_7eee019f5d` | `decimal(10,6)` |  | 是 | 成交率 |
| 16 | `cal_b6c66a2567` | `decimal(16,6)` |  | 是 | 应答后司乘取消率 |
| 17 | `relative_12d05a9353fea1f154b3571ba67fcb86` | `decimal(16,8)` |  | 是 | 匹配数日环比 |
| 18 | `relative_00136b3ddd118e09d4221f1917ceb240` | `decimal(16,8)` |  | 是 | 匹配数周同比 |
| 19 | `relative_ff86147813ac885aeb148f22fceaf666` | `decimal(16,8)` |  | 是 | 应答数日环比 |
| 20 | `relative_70b60918b3b7bb5b880d1d2b18ead645` | `decimal(16,8)` |  | 是 | 应答数周同比 |
| 21 | `relative_3fa7711ecda0d122fd7e6c650b5cc534` | `decimal(16,8)` |  | 是 | 完单数日环比 |
| 22 | `relative_d29f19ca16f3618a2c3d558d78b73446` | `decimal(16,8)` |  | 是 | 完单数周同比 |
| 23 | `relative_9d47de064151c8e5e064e39f87cfe9c3` | `decimal(16,8)` |  | 是 | 应答后司机取消数日环比 |
| 24 | `relative_00aaff3a627d6b034b6a033bf1543e45` | `decimal(16,8)` |  | 是 | 应答后司机取消数周同比 |
| 25 | `relative_25e01068e35ee696d874d83155648baa` | `decimal(16,8)` |  | 是 | 应答后乘客取消数日环比 |
| 26 | `relative_cec74b3ff1b7dad04138fac942c6d620` | `decimal(16,8)` |  | 是 | 应答后乘客取消数周同比 |
| 27 | `relative_754575dcc0a19a6a2f02378a1dd48dca` | `decimal(16,8)` |  | 是 | 乘客发单数日环比 |
| 28 | `relative_a89886fde4d3a1c830bbb8184a816b18` | `decimal(16,8)` |  | 是 | 乘客发单数周同比 |
| 29 | `relative_14b81b2ae191687498f221a3632ce48b` | `decimal(16,8)` |  | 是 | 匹配率日环比差值 |
| 30 | `relative_86b9193b8afaad1bac24dc32875ace99` | `decimal(16,8)` |  | 是 | 匹配率周同比差值 |
| 31 | `relative_fc7f4f4407ca991955377a501e0348f9` | `decimal(16,8)` |  | 是 | 应答后司机取消率日环比差值 |
| 32 | `relative_ac6a8a707588b655a6f61b5e33d618bf` | `decimal(16,8)` |  | 是 | 应答后司机取消率周同比差值 |
| 33 | `relative_c16e340a5722b13d3b510d40f7841c9b` | `decimal(16,8)` |  | 是 | 应答后乘客取消率日环比差值 |
| 34 | `relative_8a7e92d3b42eb185d66d475334e017b7` | `decimal(16,8)` |  | 是 | 应答后乘客取消率周同比差值 |
| 35 | `relative_e9d89cdd755a64e5b78d9455c9feea13` | `decimal(16,8)` |  | 是 | 应答率日环比差值 |
| 36 | `relative_c8d6e2ed6cdb1f0abab2a39e0cc126a9` | `decimal(16,8)` |  | 是 | 应答率周同比差值 |
| 37 | `relative_dc7092755aaae6539c794f91d1d7946f` | `decimal(16,8)` |  | 是 | 成交率日环比差值 |
| 38 | `relative_0bde2cb112bca4a2cdabfb27451fbe39` | `decimal(16,8)` |  | 是 | 成交率周同比差值 |
| 39 | `relative_634dd09ded5b61afe46b9939cc80ebff` | `decimal(16,8)` |  | 是 | 应答后司乘取消率日环比差值 |
| 40 | `relative_f45640343d9deea599a3d205bea72f93` | `decimal(16,8)` |  | 是 | 应答后司乘取消率周同比差值 |
| 41 | `pull_time` | `varchar(60)` |  | 是 | 拉取数据时间 |
| 42 | `time_period` | `int(10)` |  | 是 | 数据时间段（到时） |
| 43 | `created_time` | `datetime` |  | 是 | 创建时间 |
| 44 | `updated_time` | `datetime` |  | 是 | 更新时间 |

## transport_data_report

**鸿鹄传输数据统计明细**  |  10 个字段

| # | 字段名 | 类型 | 键 | 可为空 | 注释 |
|---|--------|------|-----|--------|------|
| 1 | `id` | `bigint(20)` | `PRI` | 否 | 自增主键 |
| 2 | `inner_honghu_company_id` | `varchar(50)` | `MUL` | 是 | 鸿鹄公司ID |
| 3 | `area` | `varchar(20)` | `MUL` | 是 | 城市ID |
| 4 | `dm` | `varchar(20)` | `MUL` | 是 | 数据月份（yyyy-MM） |
| 5 | `report_standard` | `varchar(20)` |  | 是 | 推送标准（jtb/bd） |
| 6 | `order_count` | `int(11)` |  | 是 | 订单数 |
| 7 | `driver_count` | `int(11)` |  | 是 | 司机数 |
| 8 | `plate_count` | `int(11)` |  | 是 | 车辆数 |
| 9 | `pull_time` | `varchar(50)` |  | 是 | 拉取时间 |
| 10 | `brand_name` | `varchar(100)` | `MUL` | 是 | 品牌名称 |
