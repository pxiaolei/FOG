# hhdata 指标计算参考指南

## 1. 数据表结构

### hhdata__fact_daily_metrics（每日指标汇总表）

来源：精简汇总数据，由上游内部入库流程写入。

| 字段 | 类型 | 中文名 | 类别 |
|------|------|--------|------|
| date | date | 日期 | 维度 |
| city_id | integer | 城市ID | 维度 |
| brand_id | integer | 品牌ID | 维度 |
| city_name | varchar(50) | 城市名称 | 维度（JOIN dim_cities） |
| brand_name | varchar(100) | 品牌名称 | 维度（JOIN dim_brands） |
| placed_orders | integer | 乘客发单量 | 订单 |
| broadcast_orders | integer | 播单量 | 订单 |
| matched_orders | integer | 匹配量 | 订单 |
| answered_orders | integer | 应答量 | 订单 |
| completed_orders | integer | 完单数 | 订单 |
| cancelled_before_answer | integer | 应答前取消量 | 取消 |
| cancelled_by_passenger | integer | 乘客取消量 | 取消 |
| cancelled_by_driver | integer | 司机取消量 | 取消 |
| online_duration_hours | numeric(10,2) | 司机在线时长(TSH) | 司机 |
| online_drivers | integer | 在线司机数 | 司机 |
| completed_drivers | integer | 完单司机数 | 司机 |
| peak_online_drivers | integer | 峰期在线司机数 | 司机 |
| peak_valid_drivers | integer | 峰期有效司机数 | 司机 |
| valid_drivers | integer | 有效司机数 | 司机 |
| approved_drivers | integer | 审核通过司机数 | 司机 |
| first_online_drivers | integer | 首次在线司机数 | 司机 |
| first_completed_drivers | integer | 首次完单司机数 | 司机 |
| gmv | numeric(15,2) | GMV | 财务 |
| total_b_subsidy | numeric(15,2) | 总B补金额 | 财务 |
| merchant_b_subsidy | numeric(15,2) | 商家B补金额 | 财务 |
| total_commission | numeric(15,2) | 总抽佣 | 财务 |
| brand_commission | numeric(15,2) | 品牌抽佣 | 财务 |
| card_merchant_income | numeric(15,2) | 售卡商家收入 | 财务 |

唯一约束：(brand_id, city_id, date)

---

## 2. hhdata vs lxdata 计算差异

| 方面 | hhdata（数据来源 A） | lxdata（数据来源 B） |
|------|---------------------|---------------------|
| 表数量 | 1 张（fact_daily_metrics） | 4-5 张（orders/driver_force/order_marketing/coupon_marketing） |
| 数据粒度 | 城市 + 品牌 + 日期 | 城市 + 品牌 + 日期 + 渠道/时段 |
| 出数速度 | 快（每日汇总） | 慢（需多表聚合） |
| 查询方式 | 单表 SELECT | 多表 JOIN + GROUP BY + pandas merge |
| 线上毛利率 | = 商家抽佣TR + 售卡收入率 - 商家B补率 - 1% | = 商家抽佣TR + 售卡收入率 - **商家独B补率**（活动+卡券分别取） - 1% |

**日报 v1 仅使用 hhdata**，后续可扩展 lxdata 提供更细粒度的补贴拆解。

---

## 3. 标准计算公式

### 3.1 直接取用字段（无需计算）

| 指标 | 字段 |
|------|------|
| 完单 | completed_orders |
| 发单 | placed_orders |
| GMV | gmv |
| 在线司机 | online_drivers |
| TSH | online_duration_hours |
| 首次完单司机数 | first_completed_drivers |

### 3.2 衍生量值指标（除法）

| 指标 | 公式 | 除零处理 |
|------|------|---------|
| 客单价 | GMV / 完单数 | 返回 None |
| 人均完单量 | 完单数 / 完单司机数 | 返回 None |
| TPH | 完单数 / 在线时长 | 返回 None |
| 人均在线时长TSH | 在线时长 / 在线司机数 | 返回 None |

### 3.3 率值指标（除法）

| 指标 | 公式 | 除零处理 |
|------|------|---------|
| 商家B补率 | 商家B补 / GMV | 返回 None |
| 商家抽佣TR | 品牌抽佣 / GMV | 返回 None |
| 总TR | 总抽佣 / GMV | 返回 None |
| 售卡收入率 | 售卡商家收入 / GMV | 返回 None |
| 线上毛利率 | 商家抽佣TR + 售卡收入率 - 商家B补率 - 1% | 任一项 None → None |
| 发单应答率 | 应答量 / 发单量 | 返回 None |
| 应答完单率 | 完单数 / 应答量 | 返回 None |
| 匹配应答率 | 应答量 / 匹配量 | 返回 None |
| 司机取消率 | 应答后司机取消量 / 应答量 | 返回 None |
| 乘客取消率 | 应答后乘客取消量 / 应答量 | 返回 None |
| 总取消率 | 应答前取消订单量 / 应答量 | 返回 None |
| 司机利用率 | 完单司机数 / 在线司机数 | 返回 None |
| 峰期有效司机率 | 峰期有效司机数 / 峰期在线司机数 | 返回 None |

---

## 4. 环比 / 同比计算

### 4.1 量值指标

```
环比 = (当日值 - 昨日值) / 昨日值    # 单位：比率（展示转为 %）
同比 = (当日值 - 上周同日值) / 上周同日值
```

### 4.2 率值指标

```
环比 = 当日率值 - 昨日率值    # 单位：百分点差值（pp）
同比 = 当日率值 - 上周率值
```

> **关键**：率值指标的环比/同比是 **pp 差值**，不是变化比率。
> 例如：B补率从 8% 升到 10%，环比 = +2.0pp（不是 +25%）。

### 4.3 城市基准

```
城市环比 = (城市当日汇总值 - 城市昨日汇总值) / 城市昨日汇总值
城市同比 = (城市当日汇总值 - 城市上周汇总值) / 城市上周汇总值
```

城市汇总 = 该城市所有品牌的数据求和（单个品牌不单独排除）。

### 4.4 异动偏离

```
偏离度 = |品牌环比 - 城市环比|
量值指标偏离 > 5pp → 标记异常
率值指标偏离 > 2pp → 标记异常
```

---

## 5. 边界情况处理

| 场景 | 处理 |
|------|------|
| 分母为 0 | 返回 None，展示为空 |
| 昨日/上周无数据 | 环比/同比列展示空 |
| 品牌名为 "-" | 替换为 "方舟行车主" |
| 码表中无该运营主体 | 返回空 DataFrame，跳过 |
| hhdata 当日无数据 | 返回空 DataFrame，跳过 |
| 新品牌（无上周数据） | 同比列为空 |
| yidongfenxi 导入失败 | 跳过深度分析，不影响主流程 |

---

## 6. 代码位置

| 模块 | 路径 |
|------|------|
| 指标计算函数 | `lxx_share/hhdata_metrics.py` |
| 日报构建 | `lx-dapanribao/scripts/report_builder.py` |
| 日报配置 | `lx-dapanribao/scripts/config.py` |
| 数据加载 | `lx-dapanribao/scripts/data_loader.py` |
| 异动检测 | `lx-dapanribao/scripts/anomaly_detector.py` |
| 飞书普通表格发布计划 | `lx-dapanribao/scripts/feishu_publisher.py` |
| hhdata 导入 | 上游内部入库流程 |
| lxdata 计算 | `lx-zhibiaojisuan/scripts/lxdata_loader.py` |
