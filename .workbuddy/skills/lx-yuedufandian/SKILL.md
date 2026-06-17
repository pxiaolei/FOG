---
name: lx-yuedufandian
description: 月度返点计算 Skill。用于按月读取账单对账、LX 品牌过程考核数据、目标拆解表和公司库 operator_brand 码表，生成运营主体品牌月度返佣/返点 Excel，并可同步结果到本地 PostgreSQL。
trigger_keywords:
  - 月度返点
  - 月度返佣
  - 返点计算
  - 返佣计算
  - 月度完单考核
  - 过程考核返佣
  - 规模返佣
location: project
---

# lx-yuedufandian — 月度返点计算

## 定位

本 Skill 处理每月运营主体品牌返点计算：

- 先读取 `workspace/13月度返点计算/YYYY年M月/源数据/` 下的账单、过程考核、目标拆解和开城奖励 Excel，并导入本地 PostgreSQL。
- 先沉淀当月人工规则 `规则/YYYY年M月月度返点规则.md` 和机器规则 `规则/rules.yaml`。
- 按公司库 `operator_brand` 的 `对接人 -> 运营主体/品牌/城市` 精确范围计算。
- 默认从 PostgreSQL import 批次读取源数据计算；Excel 只作为入库来源。
- 输出 `输出/YYYY年M月月度返点-输出.xlsx`。
- 仅在显式 `--confirmed --sync-db` 时同步本地 PostgreSQL。

## 关键口径

- 规模返佣按运营主体出行口径日均完单判断阶梯，不按 GMV 判断；`xx优行` 完单不计入出行规模。
- 过程 2000 单门槛和完单 1000 单门槛按运营主体出行口径日均完单判断。
- `xx优行` 完全独立考核，不套用出行的规模、过程和完单规则。
- 聚合考核时，同一运营主体下多个聚合目标先把一/二/三档日均目标求和，再统一判断命中档位；组内输出品牌复用同一套规模返点、过程返点、完单返点、额外返点和最终返点。
- 先锋司机上线率分母为 0 时，按 100% 通过处理并写原因。
- 总考核 sheet 的 `过程指标完成度` 不计先锋司机 LX 额外返点，也不受过程返佣系数影响。

## 安全边界

- 不从聊天记录直接推断计算口径；脚本只读取当月 `规则/rules.yaml`。
- `import-sources --dry-run` 不写数据库；`import-sources --confirmed` 才写源数据 import 批次。
- `calculate --dry-run` 不写 Excel、不写数据库。
- `calculate --confirmed --sync-db` 才写结果 run 批次。
- 源数据文件只读；输出文件可覆盖，但会按当前计算结果重建 `总考核`、`过程考核`。
- 公司库码表只读查询，来源为 `lx_shujuku.operator_brand`。
- 源文件缺失、多匹配、关键表头缺失或规则类型未知时直接失败。

## 常用命令

生成当月规则模板：

```bash
python .workbuddy/skills/lx-yuedufandian/scripts/run_monthly_rebate.py init-rules \
  --month 2026-05 \
  --work-dir "workspace/13月度返点计算/2026年5月"
```

导入源 Excel 到 PostgreSQL：

```bash
python .workbuddy/skills/lx-yuedufandian/scripts/run_monthly_rebate.py import-sources \
  --month 2026-05 \
  --work-dir "workspace/13月度返点计算/2026年5月" \
  --confirmed
```

只导入上月过程指标，用于本月 TSH 增速：

```bash
python .workbuddy/skills/lx-yuedufandian/scripts/run_monthly_rebate.py import-process \
  --month 2026-04 \
  --work-dir "workspace/13月度返点计算/2026年4月" \
  --confirmed
```

预览计算：

```bash
python .workbuddy/skills/lx-yuedufandian/scripts/run_monthly_rebate.py calculate \
  --month 2026-05 \
  --work-dir "workspace/13月度返点计算/2026年5月" \
  --contacts 雷维亮 \
  --dry-run
```

从 PostgreSQL import 批次写 Excel：

```bash
python .workbuddy/skills/lx-yuedufandian/scripts/run_monthly_rebate.py calculate \
  --month 2026-05 \
  --work-dir "workspace/13月度返点计算/2026年5月" \
  --contacts 雷维亮 \
  --confirmed
```

从 PostgreSQL import 批次写 Excel 并同步结果 run：

```bash
python .workbuddy/skills/lx-yuedufandian/scripts/run_monthly_rebate.py calculate \
  --month 2026-05 \
  --work-dir "workspace/13月度返点计算/2026年5月" \
  --contacts 雷维亮 \
  --confirmed \
  --sync-db
```

## 月度目录

```text
workspace/13月度返点计算/YYYY年M月/
├── 源数据/
├── 规则/
│   ├── YYYY年M月月度返点规则.md
│   └── rules.yaml
└── 输出/
```

## 必需源文件

以 2026 年 5 月为当前固定结构，`源数据/` 至少需要：

- `*账单对账*部分字段*.xlsx`
  - 读取全部 sheet；2026 年 5 月为 `工作表1(除拼哒、任我)`、`拼哒、任我`、`方舟行临沂`、`优行`。
  - 入库到 `lxfandian.bill_raw` 保留全字段原始行，常用字段结构化；再派生 `lxfandian.bill_agg`，按每个 sheet 的 `日期 + 品牌 + 城市 + tr类型 + 流量渠道` 聚合。
- `*LX品牌过程考核数据*.xlsx`
  - 读取全部 sheet；2026 年 5 月为 `完单`、`协同指标`、`TSH`、`先锋司机`、`司机客服接起率`。
  - 入库到 `lxfandian.proc_raw`，字段变化保留在 `raw_payload`。
- `*目标拆解*入库*.xlsx`
  - 读取 `出行`、`优行` sheet。
  - 入库到 `lxfandian.targets`。
- `*开城奖励*.xlsx`
  - 2026 年 5 月为 `2026年5月-开城奖励.xlsx` / `Sheet2`。
  - 入库到 `lxfandian.open_city`，保留全字段 `raw_payload`，计算 `新开城金额` 和 `新开城金额占比`。
  - 如果开城周期字段缺失或无法解析，按当月 `rules.yaml` 的 `open_city_reward.invalid_period_policy` 处理。

每个 Excel 的每个 sheet 都会先登记到 `lxfandian.src_sheets`，业务表通过 `src_sheet_id` 追溯来源。

## 规则文件

- `references/monthly_rules_template.md`：人工规则留档模板。
- `references/rules_yaml_template.yaml`：机器规则模板。
- `assets/data_processing_rules.md`：跨月复用的数据处理口径，包括 TSH 日均增速和品牌曾用名。
- 每月过程考核项变化时，只改当月 `rules.yaml` 的 `process.redlines` 和 `process.metrics`。

## 数据库

PostgreSQL DDL 在 `scripts/db_schema.sql`。脚本会先执行 `CREATE SCHEMA IF NOT EXISTS lxfandian` 和 `CREATE TABLE IF NOT EXISTS`。

- 专用 schema：`lxfandian`。
- 源数据批次表：`imports`、`src_sheets`、`bill_raw`、`bill_agg`、`proc_raw`、`targets`、`open_city`。
- 计算结果表：`runs`、`scope`、`base_agg`、`results`、`proc_detail`。
- `import-sources --confirmed` 写入 `lxfandian.imports` 和源数据表；账单在 `bill_raw.raw_payload` 保留全字段原始行，并在 `bill_agg` 保留 `sheet + 日期 + 品牌 + 城市 + tr类型 + 流量渠道` 聚合；过程、目标、开城也保留全字段 `raw_payload`。
- `import-process --confirmed` 写入 `process_only` 批次，用于只有上月过程指标的目录。
- `calculate` 默认读取当月最新 confirmed import；可用 `--import-id` 指定批次。
- `calculate` 会自动读取上月最新 `process_only/full` import 的 `TSH` sheet，用于 TSH 增速。
- `calculate --source excel` 保留为排障 fallback。
- `calculate --confirmed --sync-db` 写入 `lxfandian.runs` 和结果明细表，并记录本次使用的 `import_id`。
