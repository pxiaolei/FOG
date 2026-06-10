---
name: lx-biaogetongbu
description: 表格同步工具。用于把 A 表中的记录按字段映射同步到 B 表，覆盖静默乘客登记、背审登记、主体拆表结果同步、农服大文档按品牌城市回填等场景。支持本地 Excel append / update-by-key；在线后端只支持飞书普通电子表格 feishu。
trigger_keywords:
  - 表格同步
  - 同步表格
  - biaogetongbu
  - lx-biaogetongbu
  - 从A表同步到B表
  - 静默乘客登记
  - 背审登记
  - 同步背审申诉
  - 同步静默乘客
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
| 飞书普通电子表格 | `append` / `update-by-key` | 已接 `feishu` 后端，使用 `lx-feishudocs` 和 WorkBuddy 内置 lark-cli |
| 飞书普通电子表格 | 运营主体固定场景 | 已接 `operator_workbook_sync.py`，支持背审申诉和静默乘客 |

不直接写后台系统或数据库。

## 安全边界

- 不删除或修改 A 表原始行。
- 不自动发送、不自动提交后台。
- 未传 `--confirmed` 时不写入 B 表。
- 正式写入 B 表前自动备份目标文件。
- `update-by-key` 只更新 `--update-column` 指定列，不整行覆盖。
- `update-by-key` 默认不使用空值覆盖 B 表；确需清空时显式传 `--allow-blank-updates`。
- 在线表格写入必须先 `--dry-run` 看清计划，再 `--confirmed`。
- 未显式指定 `--online-backend` 时默认使用 `feishu`，也就是飞书普通电子表格。
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

飞书普通电子表格 dry-run：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/sync_table.py \
  --online \
  --online-backend feishu \
  --mode update-by-key \
  --source-url "https://xxx.feishu.cn/sheets/..." \
  --target-url "https://xxx.feishu.cn/sheets/..." \
  --source-tab "0610主体填写" \
  --target-tab "大文档" \
  --key "品牌" \
  --key "城市" \
  --update-column "填写结果" \
  --dry-run
```

固定运营主体场景 dry-run：

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/operator_workbook_sync.py \
  --scenario beishen_shensu \
  --master-url "<背审申诉大表飞书链接>" \
  --contact-person "雷维亮" \
  --all-operators
```

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/operator_workbook_sync.py \
  --scenario jingmo_chengke \
  --master-url "<静默乘客大表飞书链接>" \
  --contact-person "雷维亮" \
  --all-operators
```

默认只预览。真实写入必须显式加 `--confirmed`。

固定场景行为：

- `beishen_shensu`：读取 `{运营主体}-背审申诉`，按 `司机ID` 防重复追加到大表；写入后给来源行写 `是否提交=填写已提交`；大表 `背审结果` 有值时回填来源表同名列。
- `jingmo_chengke`：读取 `{运营主体}-静默乘客`，按 `订单ID + 用户ID（乘客ID）` 防重复追加到大表；写入后给来源行写 `是否提交=填写已提交`。
- 来源表缺少 `是否提交` 表头时，confirmed 写入会在来源表下一空表头列补上该列。
- 背审图片列如果属于本次要追加的行，脚本会阻断 confirmed 写入，避免把图片/富文本当纯文本丢失。已存在于大表、仅补提交状态的行不会因图片阻断。

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
| `--online` | 使用在线表格后端 |
| `--online-backend` | `feishu`；默认 `feishu` |
| `--source-url` / `--target-url` | 飞书普通表格 URL / spreadsheet token |
| `--source-tab` / `--target-tab` | 在线表格 sheet 标题或 sheet_id |
| `--output` | 另存为新文件；不传则正式写入目标表原文件 |
| `--dry-run` | 只预览，不写 B 表 |
| `--confirmed` | 确认写入 B 表 |

## 执行步骤

1. 枚举并确认真实来源文件和目标文件。
2. 运行 `--dry-run`，检查字段映射、去重键和预计追加行数。
3. 用户确认后运行 `--confirmed`。
4. 检查处理日志和目标表备份。

## 飞书普通表格执行顺序

飞书普通表格目标执行顺序固定：

1. 默认使用 `--online-backend feishu`；为了清晰，关键写入任务仍建议显式传入。
2. 解析飞书普通表格 URL 为 spreadsheet token。
3. 查询 workbook / sheet 元信息。
4. 读取表头和有效数据。
5. 生成 dry-run 计划。
6. 用户确认后通过 `lx-feishudocs` 写入普通 sheet。
7. 再次读回验证写回结果。

写入阶段边界：

- 写入开始后不自动换后端；如果飞书写入失败，直接报告真实失败原因，要求人工确认是否续跑。
- 本项目后续写表目标是飞书普通电子表格，不使用 Base/智能表格记录接口。

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

profile 只能保存字段规则和默认模式，不能保存真实飞书链接、token 或个人路径。固定大表链接可在运行时用 `--master-url` 传入，或写入本机 `config/fog_config.yaml` 的 `lx_biaogetongbu.operator_sync.scenarios.<scenario>.master_url`。

已提供：

- `assets/profiles/nongfu_update_by_key.example.json`
- `assets/profiles/beishen_shensu.json`
- `assets/profiles/jingmo_chengke.json`
