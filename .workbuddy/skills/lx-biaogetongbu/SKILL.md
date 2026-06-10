---
name: lx-biaogetongbu
description: 表格同步工具。用于把 A 表中的记录按字段映射同步到 B 表，覆盖静默乘客登记、背审登记、主体拆表结果同步、农服大文档按品牌城市回填等场景。支持本地 Excel append / update-by-key；支持腾讯文档在线表格 adapter，但 live MCP 可能受限额影响，线上写入必须先 dry-run。
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
- 农服回填：把运营主体填写结果按品牌+城市回填到大文档指定列。

当前支持：

| 后端 | 模式 | 状态 |
|---|---|---|
| 本地 Excel | `append` | 已离线验证 |
| 本地 Excel | `update-by-key` | 已离线验证 |
| 腾讯文档在线表格 | `append` / `update-by-key` | 已实现 adapter；受 MCP 限额影响，未做 live 写入验收 |

不直接写后台系统或数据库。

## 安全边界

- 不删除或修改 A 表原始行。
- 不自动发送、不自动提交后台。
- 未传 `--confirmed` 时不写入 B 表。
- 正式写入 B 表前自动备份目标文件。
- `update-by-key` 只更新 `--update-column` 指定列，不整行覆盖。
- `update-by-key` 默认不使用空值覆盖 B 表；确需清空时显式传 `--allow-blank-updates`。
- 腾讯文档写入必须先 `--dry-run` 看清计划，再 `--confirmed`。
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

按品牌+城市回填指定列：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/sync_table.py \
  --mode update-by-key \
  --source "workspace/10表格同步/待处理/A.xlsx" \
  --target "workspace/10表格同步/待处理/B.xlsx" \
  --key "品牌" \
  --key "城市" \
  --update-column "填写结果" \
  --update-column "备注" \
  --dry-run
```

腾讯文档在线表格 dry-run：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/sync_table.py \
  --online \
  --mode update-by-key \
  --source-url "https://docs.qq.com/sheet/..." \
  --target-url "https://docs.qq.com/sheet/..." \
  --source-tab "0610主体填写" \
  --target-tab "大文档" \
  --key "品牌" \
  --key "城市" \
  --update-column "填写结果" \
  --dry-run
```

## 参数说明

| 参数 | 说明 |
|---|---|
| `--mode` | `append` 或 `update-by-key`；默认 `append` |
| `--source` | A 表，本地 `.xlsx` / `.xlsm` 文件 |
| `--target` | B 表，本地 `.xlsx` / `.xlsm` 文件 |
| `--source-sheet` | A 表 sheet 名；不传则使用活动 sheet |
| `--target-sheet` | B 表 sheet 名；不传则使用活动 sheet |
| `--map` | 字段映射，格式为 `源列=目标列`；不传时按同名列同步 |
| `--key` | append 时是去重键；update-by-key 时是定位键；可重复传入，也可逗号分隔 |
| `--update-column` | update-by-key 允许更新的 B 表列；必须显式指定 |
| `--literal` | 固定写入目标列，格式为 `目标列=固定值` |
| `--online` | 使用腾讯文档在线表格后端 |
| `--source-url` / `--target-url` | 腾讯文档 URL 或 file_id |
| `--source-tab` / `--target-tab` | 在线表格 sheet 标题或 sheet_id |
| `--output` | 另存为新文件；不传则正式写入目标表原文件 |
| `--dry-run` | 只预览，不写 B 表 |
| `--confirmed` | 确认写入 B 表 |

## 执行步骤

1. 枚举并确认真实来源文件和目标文件。
2. 运行 `--dry-run`，检查字段映射、去重键和预计追加行数。
3. 用户确认后运行 `--confirmed`。
4. 检查处理日志和目标表备份。

## 腾讯文档执行顺序

线上表格执行顺序固定：

1. `query_file_info` 解析 URL 短 ID 为真实 `file_id`。
2. `sheet.get_info` 确认 sheet / tab。
3. `sheet.get_range` 读取表头和有效数据。
4. 生成 dry-run 计划。
5. 用户确认后用 `sheet.batch_update` 写入。
6. 再次 `sheet.get_range` 验证写回结果。

如果腾讯 MCP 返回限额错误，直接报告失败原因，不编造 dry-run 或写入结果。

## update-by-key 规则

- key 默认必须包含品牌+城市。
- 大文档同一个 key 多行命中时，不写入，标记冲突。
- 来源表同一个 key 多行命中时，不写入，标记冲突。
- 只更新 `--update-column` 指定列，不整行覆盖。
- dry-run 必须输出将更新的行列坐标和原值/新值摘要。
- 空值默认不覆盖；确需清空时传 `--allow-blank-updates`。

## 场景 profile

把高频场景沉淀到 `.workbuddy/skills/lx-biaogetongbu/assets/profiles/`：

```json
{
  "mode": "update-by-key",
  "keys": ["品牌", "城市"],
  "mapping": {
    "品牌": "品牌",
    "城市": "城市",
    "填写结果": "填写结果"
  },
  "update_columns": ["填写结果"],
  "require_dry_run": true
}
```

profile 只能保存字段规则和默认模式，不能保存真实腾讯文档链接、token 或个人路径。

已提供示例：`assets/profiles/nongfu_update_by_key.example.json`。
