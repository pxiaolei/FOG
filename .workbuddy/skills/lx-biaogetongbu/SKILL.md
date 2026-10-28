---
name: lx-biaogetongbu
description: 表格同步工具。用于把 A 表中的记录按字段映射同步到 B 表，覆盖静默乘客登记、背审登记、日常退卡、异常判责 case、主体拆表结果同步、农服大文档按品牌城市回填等场景。支持本地 Excel append / update-by-key；在线后端只支持飞书普通电子表格 feishu。当用户要求表格同步、从 A 表同步到 B 表、同步背审申诉、静默乘客、日常退卡、异常判责 case 或拆表结果时使用。
---

# lx-biaogetongbu — 表格同步

## 定位

本 Skill 处理“从 A 表挪到 B 表”的通用表格同步场景：

- 静默乘客登记：从待登记名单追加到登记台账。
- 背审登记：从待背审清单追加到背审登记表。
- 日常退卡：从配置的运营主体退卡表追加到日常退卡总表，并回填平台处理结果。
- 异常判责 case：从配置的运营主体登记表追加到「10月case提报」，并回填治理复核结果。
- 主体拆表同步：把 `lx-zhutichaibiao` 拆出来的表同步到目标汇总表或登记表。
- 农服回填：把运营主体填写结果按品牌+城市回填到大文档指定列。

当前支持：

| 后端 | 模式 | 状态 |
|---|---|---|
| 本地 Excel | `append` | 已离线验证 |
| 本地 Excel | `update-by-key` | 已离线验证 |
| 飞书普通电子表格 | `append` / `update-by-key` | 已接 `feishu` 后端，使用 `lx-feishudocs` 和 WorkBuddy 内置 lark-cli |
| 飞书普通电子表格 | 运营主体固定场景 | 已接 `operator_workbook_sync.py`，支持背审申诉、静默乘客、日常退卡和异常判责 case；单元格图片随追加行重新挂载到目标表 |

不直接写后台系统或数据库。

## 安全边界

- 不删除或修改 A 表原始行。
- 不自动发送、不自动提交后台。
- 未传 `--confirmed` 时不写入 B 表，也不下载或上传单元格图片，也不创建本地输出、目标备份、处理日志或 summary JSON。
- 正式写入 B 表前自动备份目标文件。
- `update-by-key` 只更新 `--update-column` 指定列，不整行覆盖。
- `update-by-key` 默认不使用空值覆盖 B 表；确需清空时显式传 `--allow-blank-updates`。
- 在线表格写入必须先 `--dry-run` 看清计划，再 `--confirmed`。
- 在线 confirmed 写入后必须逐项读回全部更新单元格和全部追加 payload；不提供跳过验证参数，任一错配即失败且不生成成功日志。
- 未显式指定 `--online-backend` 时默认使用 `feishu`，也就是飞书普通电子表格。
- 只有 confirmed 运行生成处理日志；dry-run 只向 stdout 输出来源、目标、字段映射、去重键、预计追加行数和跳过原因。

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
  --all-operators
```

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/operator_workbook_sync.py \
  --scenario jingmo_chengke \
  --master-url "<静默乘客大表飞书链接>" \
  --contact-person "雷维亮" \
  --operator 盛世兄弟,江豚出行,乖乖马出行
```

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/operator_workbook_sync.py \
  --scenario tuika_richang \
  --all-operators
```

```bash
python .workbuddy/skills/lx-biaogetongbu/scripts/operator_workbook_sync.py \
  --scenario yichang_panzhe_case \
  --all-operators
```

静默 / 日常退卡 / 背审申诉 / 异常判责 case 场景走 lark-cli，不依赖飞书 MCP。不加 `--confirmed` 即 dry-run。日常退卡、背审申诉和异常判责 case 的主体 URL 读本机 config，可按需加 `--apply-validation-status` 只写缺项到状态列。

默认只预览。真实写入必须显式加 `--confirmed`；未 confirmed 时 `--output-json` 不落盘。若指定的 summary 已存在，必须同时传 `--overwrite --confirmed`，且该检查在创建飞书 client 前完成。

固定场景行为：

- `beishen_shensu`：从本机 config 的主体 URL 列表读取背审申诉表（`use_configured_operator_urls`，跳过文件夹发现；主体按工作簿标题识别），追加到总表「司机背审申诉」（profile `master_sheet_id=0AOZVh`）。`skip_already_in_master=false`：总表已有同一 `司机ID` 仍追加（改图重提），不把 O 标成已提报。同一轮多行未提报且司机相同，只追加靠前第一行，其余 O 写 `同期重复提报`（之后与 `已提报`、`/举例` 一样跳过）。只同步源表 A–N（`max_source_column=14`），按表头名写入总表 B–O（总表 A 为空）；J–N 为图片列（人证、承诺书、司机端审核失败原因截图、HH后台审核失败截图、身份证正面），`--confirmed` 时用 `drive +preview --type source_file` 下载再用 `sheets +cells-set-image` 重新挂载；状态写到 O 列（`status_column_number=15`，表头 `提报`），成功写 `已提报`；O 列缺项提示不跳过；A–N 缺项写中文提示到 O（如 `缺少B列、I列信息`、`缺少L列图片`）；`match_decorated_headers` 允许表头在字段名后带模板链接或非字母数字后缀（`承诺书https://…` 对齐为承诺书，`车牌号` 不会对齐到 `车牌号码`）；总表 P `背审结果` 按 `司机ID` 回填主体 P，`use_last_row` 只用该司机最后一行，且该行 P 非空才回填（`ignore_duplicates` 不阻断）。默认 dry-run；`--apply-validation-status` 写缺项和 `同期重复提报`；`--confirmed` 才写总表/已提报/挂图片/回填。详见 `workspace/10表格同步/README_beishen.md`。
- `jingmo_chengke`：读取 `{运营主体}-静默乘客`，按 `品牌+城市+订单ID+用户ID（乘客ID）` 防重复追加到总表「静默收集正在处理」；只同步源表 A–H（`max_source_column=8`）；状态写到 I 列（`status_column_number=9`），值为 `已提报`；`填写已提交`/`已提报`/`已提交` 均视为已处理；`require_nonempty_columns` 缺用户ID 的行跳过不整表作废；默认三家主体见 profile `default_operators`。详见 `workspace/10表格同步/README_jingmo.md`。
- `tuika_richang`：从本机 config 的主体 URL 列表读取日常退卡表（跳过文件夹发现），按 `司机id+卡券id` 防重复追加到总表「1、日常退卡填写」（`sheet_id=4c07cd`）；只同步源表 A–L（`max_source_column=12`）；状态写到 M 列（`status_column_number=13`），成功写 `已提报`；仅 `已提报`/`/` 视为已处理；缺项写中文提示到 M（如 `缺少L列图片`）；J=`是` 时 K 条件必填；N–P 多列结果回填；`result_writeback.ignore_duplicates=true` 时总表去重键重复只记 `duplicate_warnings`、不进 `blocking.master_duplicates`（回填仍用第一行）。默认 dry-run；`--apply-validation-status` 只写缺项；`--confirmed` 才写总表/回填/已提报。详见 `workspace/10表格同步/README_tuika.md`。
- `yichang_panzhe_case`：从本机 config 的主体 URL 列表读取异常判责 case 表（`use_configured_operator_urls`，跳过文件夹发现；工作簿标题 `{名}-异常判责case登记-新` 识别主体），追加到总表「10月case提报」（profile `master_sheet_id=aWDUZd`，workbook「商家新-异常判责case登记-LX」）。`skip_already_in_master=false`：总表已有同一 `订单ID` 仍追加（改图重提）。同一轮多行未提报且订单相同，只追加靠前第一行，其余 T 写 `同期重复提报`（之后与 `已提报`、`/举例` 一样跳过）。只同步源表 A–S 里总表同名列（`max_source_column=19`）；N 列表头主体是「平台跑数」、总表是「中台跑数」，不放进 profile 字段名，`common_append` 对不上就跳过。A「提报人」可空。必填文本是 B–L 与 O；M「订单判责通知书截图」必填图；P–S「其他证据1–4（照片）」进 `image_columns`，`require_any_image_columns` 要求至少一张，四列全空才写 `缺少P–S列图片`。状态写到 T 列（`status_column_number=20`，表头 `是否提报`）。总表 T `【治理反馈】本单复核结果` 按 `订单ID` 回填主体 U（表头带换行「（商家无需填写）」，`match_decorated_headers` 对齐），`use_last_row` 只用最后一行，该行结果为空则不回填。主体 U 去掉首尾空白后为 `/示例` 或 `/举例` 时不回填（`result_writeback.skip_source_values`）。默认 dry-run（每日约 15:30）；`--apply-validation-status` 写缺项和 `同期重复提报`；`--confirmed` 才写总表/已提报/挂图片/回填。详见 `workspace/10表格同步/README_yichang_panzhe.md`。
- 来源表缺少 `是否提交` 表头时，confirmed 写入会在来源表下一空表头列补上该列。
- 图片列如果属于本次要追加的行，脚本会读取单元格 `embed-image`，用 `drive +preview --type source_file` 下载源图，再调用目标表 `sheets +cells-set-image` 重新挂载。跨工作簿禁止复用来源 `image_token`：该 token 只挂在来源电子表格上，直接 `+cells-set` 会返回飞书 `40402 / 602134071 setCell file is not mounted`。同一单元格只有一张图时直接 `+cells-set-image`；多张图时先逐张挂到目标工作簿，再用新的目标 `image_token` 组装 `embed-image`。`--image` 必须是临时目录内的相对路径。详见 `workspace/10表格同步/README_tuika.md`。
- 固定运营主体场景会完整读回全部追加行的每个写入单元格，并按图片数量确认目标单元格已挂上图片。读回结果附带尺寸供对照。目标 `image_token` 与来源不同是重新挂载后的正常结果。来源状态/结果更新同样全量读回，不做前 30 条抽样。
- 浮动图片、无法解析出 `image_token` 的富文本图片仍会阻断 confirmed 写入，避免把图片/富文本当纯文本丢失。已存在于大表、仅补提交状态的行不会因图片阻断。

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
| `--dry-run` | 只预览，不写 B 表、输出、备份、处理日志或 summary JSON |
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
7. 逐项读回全部写回结果；任一目标坐标与计划 payload 不一致即失败。

写入阶段边界：

- 写入开始后不自动换后端；如果飞书写入失败，直接报告真实失败原因，要求人工确认是否续跑。
- 本项目后续写表目标是飞书普通电子表格，不使用 Base/智能表格记录接口。
- `operator_workbook_sync.py` 的固定运营主体场景支持 profile `image_columns` 中的单元格图片同步。跨工作簿图片必须先 `drive +preview --type source_file` 下载，再用目标表 `sheets +cells-set-image` 重新挂载，不能复用来源 `image_token`。通用 `sync_table.py --online` 当前仍只同步标量文本/数字值，不复制图片或其他富文本对象。

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
- `assets/profiles/tuika_richang.json`
- `assets/profiles/yichang_panzhe_case.json`

## 执行契约

### 输入

- 已动态确认的 A/B 表路径或飞书普通表格地址、sheet、字段映射、唯一键和同步模式。
- 是否只预览；任何真实写入都需要显式确认参数。

### 输出

- dry-run stdout 差异摘要，或 confirmed 后的新增/更新/跳过/冲突统计与目标位置。
- 仅 confirmed 时生成机器可读摘要、处理日志和失败记录；不得把凭证或个人路径写入 profile。

### 验收

- 源行数、匹配数、写入数、跳过数和冲突数可对账，唯一键无意外重复。
- dry-run/未确认时 B 表、输出路径、备份目录、日志目录和 summary JSON 均保持不变。
- confirmed 写入后重新读取目标，关键字段与计划一致；未读回不得报告完成。
