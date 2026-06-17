---
name: lx-celuehuodong
description: 策略活动表处理流程。触发词：策略活动、更新共补日历、生成免佣卡、免佣卡导入后台、celuehuodong。负责从 hhdata.fact_gongbu_strategy 读取共补数据，更新城市策略活动表的共补活动 sheet、免佣卡 sheet 和城市日历，并可生成后台导入文件。默认只 dry-run 预览，必须显式确认后写入。
agent_created: true
---

# 策略活动表处理流程

本 Skill 承接策略活动表、日历和免佣卡相关动作；共补策略原表拆分、入库和同比分析属于上游内部流程，不在共享版内执行。

## 执行流程

默认先预览，不写文件：

```bash
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --auto
```

确认后执行：

```bash
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --auto --confirmed
```

指定日期：

```bash
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --start 2026-06-15 --end 2026-06-17
```

只执行一个步骤：

```bash
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --step activity --start 2026-06-15 --end 2026-06-17 --confirmed
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --step card --start 2026-06-15 --end 2026-06-17 --confirmed
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --step calendar --start 2026-06-15 --end 2026-06-17 --confirmed
python .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --step export --date-range 0615-0617 --confirmed
```

## 步骤边界

| 步骤 | 脚本 | 作用 |
|------|------|------|
| activity | `update_gongbu_activity.py` | 从数据库读取共补数据，追加到策略活动表的“共补活动”sheet |
| card | `create_mianyongka.py` | 根据共补时段和卡券配置，生成“免佣卡”sheet 记录 |
| calendar | `update_gongbu_calendar.py` | 把共补时段写入城市 sheet 的日历区域 |
| export | `generate_mianyongka_import.py` | 从“免佣卡”sheet 按品牌生成后台导入 Excel |

`all` 只执行 `activity -> card -> calendar`，后台导入文件需要单独执行 `--step export`。

## 配置来源

配置统一从项目根目录读取：

- 共享模板：`config/fog_config.yaml.example` 的 `lx_celuehuodong` 段
- 本机真实配置：`config/fog_config.yaml`
- 本机私有覆盖：`config/personal_config.yaml` 的 `lx_celuehuodong` 段

默认目录：

- 策略活动表：`workspace/05策略活动/策略活动表/城市策略活动表2604版_v2.xlsm`
- 后台导入输出：`workspace/05策略活动/导入后台表格/`
- 共补原表存档：`workspace/07共补活动/共补原表存档/`

## 安全规则

- 默认只预览，不写 Excel。
- 写入 `.xlsm` 或生成后台导入文件必须带 `--confirmed`。
- 不在 skill 内硬编码个人路径、账号、token。
- 原始共补数据以 `hhdata.fact_gongbu_strategy` 为准；先确保共补策略数据已入库，再运行本 Skill。
