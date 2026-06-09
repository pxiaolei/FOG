---
name: lx-biaogetongbu
description: 表格同步工具。用于把 A 表中的记录按字段映射同步到 B 表，覆盖静默乘客登记、背审登记、主体拆表结果同步等“从来源表追加到目标登记表/汇总表”的场景。首版只处理本地 Excel 文件，强制 dry-run 或 confirmed，正式写入前备份目标表。
trigger_keywords:
  - 表格同步
  - 同步表格
  - biaogetongbu
  - lx-biaogetongbu
  - 从A表同步到B表
  - 静默乘客登记
  - 背审登记
  - 拆表同步
location: project
---

# lx-biaogetongbu — 表格同步

## 定位

本 Skill 处理“从 A 表挪到 B 表”的通用表格同步场景：

- 静默乘客登记：从待登记名单追加到登记台账。
- 背审登记：从待背审清单追加到背审登记表。
- 主体拆表同步：把 `lx-zhutichaibiao` 拆出来的表同步到目标汇总表或登记表。

首版只做本地 Excel 的安全追加同步，不直接调用腾讯文档、后台系统或数据库写入。

## 安全边界

- 不删除或修改 A 表原始行。
- 不自动发送、不自动提交后台。
- 未传 `--confirmed` 时不写入 B 表。
- 正式写入 B 表前自动备份目标文件。
- 每次运行生成处理日志，记录来源、目标、字段映射、去重键、追加行数和跳过原因。

## 常用命令

先预览：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/sync_table.py \
  --source "workspace/10表格同步/待处理/A.xlsx" \
  --target "workspace/10表格同步/待处理/B.xlsx" \
  --key "司机ID" \
  --dry-run
```

确认后写入：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/sync_table.py \
  --source "workspace/10表格同步/待处理/A.xlsx" \
  --target "workspace/10表格同步/待处理/B.xlsx" \
  --key "司机ID" \
  --confirmed
```

字段名不一致时显式映射：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/sync_table.py \
  --source "待同步.xlsx" \
  --target "登记表.xlsx" \
  --map "司机id=司机ID" \
  --map "品牌名称=品牌" \
  --map "城市=城市" \
  --key "司机ID" \
  --literal "来源=主体拆表" \
  --dry-run
```

## 参数说明

| 参数 | 说明 |
|---|---|
| `--source` | A 表，本地 `.xlsx` / `.xlsm` 文件 |
| `--target` | B 表，本地 `.xlsx` / `.xlsm` 文件 |
| `--source-sheet` | A 表 sheet 名；不传则使用活动 sheet |
| `--target-sheet` | B 表 sheet 名；不传则使用活动 sheet |
| `--map` | 字段映射，格式为 `源列=目标列`；不传时按同名列同步 |
| `--key` | 去重键，可重复传入，也可逗号分隔；去重键按目标列判断 |
| `--literal` | 固定写入目标列，格式为 `目标列=固定值` |
| `--output` | 另存为新文件；不传则正式写入目标表原文件 |
| `--dry-run` | 只预览，不写 B 表 |
| `--confirmed` | 确认写入 B 表 |

## 执行步骤

1. 枚举并确认真实来源文件和目标文件。
2. 运行 `--dry-run`，检查字段映射、去重键和预计追加行数。
3. 用户确认后运行 `--confirmed`。
4. 检查处理日志和目标表备份。

## 后续扩展

- 腾讯文档企业版 A 表到 B 表同步。
- 后台登记表同步。
- 场景 profile：把静默乘客登记、背审登记等固定映射沉淀为 JSON 配置。
