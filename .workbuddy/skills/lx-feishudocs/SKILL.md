---
name: lx-feishudocs
description: 飞书云文档普通电子表格 Skill。通过 WorkBuddy 内置 lark-cli 操作飞书 Sheets 普通表格，支持账号状态检查、创建普通电子表格、读取工作簿信息、写入 CSV 到单元格区域、读取 CSV 验证。适用于飞书云文档、飞书普通表格、Feishu Sheets、Lark Sheets，不用于飞书多维表格/Base/智能表格。
---

# lx-feishudocs — 飞书普通电子表格

## 定位

本 Skill 是 FOG 的飞书云文档后端，负责所有线上普通表格发布和读写链路。

当前只面向**飞书普通电子表格 Sheets**：

- 创建普通电子表格。
- 查询工作簿和 sheet 列表。
- 向普通 sheet 写入 CSV/二维表数据。
- 从普通 sheet 读取 CSV 做写后验证。
- 作为上层 Skill 的 lark-cli 定位和账号底座；图片等富文本对象由上层按场景直接调用 `sheets +cells-get` / `+cells-set`。

不使用飞书多维表格 Base，不使用智能表格。需要 Base/多维表格能力时必须另起需求，不要把普通表格发布链路混到 Base。

## 配置

真实账号和 token 由 WorkBuddy 飞书连接器维护，不写入本项目配置。

`config/fog_config.yaml` 只保存非敏感偏好：

```yaml
lx_feishudocs:
  cli_path: ""
  identity: "user"
  spreadsheet_type: "sheets"
  default_folder_token: ""
  cache_path: ".workbuddy/skills/lx-feishudocs/assets/feishu_sheet_cache.json"
```

`cli_path` 为空时脚本自动按以下顺序查找：

1. 环境变量 `LARK_CLI`
2. `PATH` 中的 `lark-cli`
3. WorkBuddy 内置路径 `~/.workbuddy/binaries/node/cli-connector-packages/lib/node_modules/@larksuite/cli/bin/lark-cli`

普通表格创建、写入、读回最少需要授权以下 scope：

```text
sheets:spreadsheet:create sheets:spreadsheet:write_only sheets:spreadsheet:read sheets:spreadsheet:readonly
```

## 常用命令

检查账号状态：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py status
```

普通表格 dry-run 创建预览：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py create-workbook \
  --title "FOG飞书普通表格测试" \
  --dry-run
```

创建普通表格：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py create-workbook \
  --title "FOG飞书普通表格测试" \
  --confirmed
```

写入 CSV 到普通 sheet：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py csv-put \
  --spreadsheet-token "<spreadsheet_token>" \
  --sheet-id "<sheet_id>" \
  --start-cell A1 \
  --csv-file rows.csv \
  --confirmed
```

读取普通 sheet 验证：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py csv-get \
  --spreadsheet-token "<spreadsheet_token>" \
  --sheet-id "<sheet_id>" \
  --range A1:C10
```

最小 smoke：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py smoke --confirmed
```

## 安全边界

- 不输出 app secret、access token、refresh token。
- `create-workbook`、`csv-put`、`smoke` 默认只输出预览；`--dry-run` 同样只预览，且二者都不会调用 lark-cli 写命令。
- 真实创建或写入必须显式传 `--confirmed`；`--dry-run` 与 `--confirmed` 互斥。
- 该 Skill 禁止隐式调用；上层 Skill 必须把确认动作显式传递到命令行。
- 只操作普通电子表格；看到 Base、多维表格、智能表格需求时停止并说明边界。
- `create-workbook --confirmed` 创建后必须用新 token 调用 `+workbook-info`，并用 `drive +inspect` 校验类型、token 和标题；若传入初始表头或数据，还要从首个 sheet 的 `A1` 起完整读回矩阵。任一读回缺失或不一致都判定失败。
- 创建接口的 `folder_token` 是写前绑定目标，但飞书当前读接口不返回创建后的父文件夹；输出会明确标记“API 不提供创建后 folder 读回”，不得伪称该字段已验证。
- `csv-put --confirmed` 必须绑定且只能绑定一个工作簿和一个 sheet；脚本根据 `start-cell` 与 CSV 行列数计算完整 A1 范围，写后用 `+csv-get` 读回并逐格比对完整矩阵。读回截断、缺格、多格或任一值不一致都判定失败，不能只相信写接口返回。
- 读回失败发生在外部写接口受理之后，不代表飞书已自动撤销写入；此时停止后续发布并报告首个不一致单元格。
- 本脚本的 `csv-get` / `csv-put` 只覆盖标量值；单元格图片、附件、富文本和浮动图片不能通过 CSV 往返，必须由上层 Skill 使用对应 Sheets 图片/富文本接口并回读验证。

## 给上层 Skill 的约定

- 日报发布目标：飞书普通电子表格，每个运营主体一个 spreadsheet，每天一个 sheet。
- 农夫协作目标：飞书普通电子表格，按品牌+城市定位回填。
- A/B 表同步：`lx-biaogetongbu --online --online-backend feishu`。

## 执行契约

### 输入

- 飞书普通电子表格的 token/URL、sheet、目标范围和待写二维数据或 CSV。
- 账号状态与写入确认；Base/多维表格需求不进入本 Skill。

### 输出

- 工作簿/sheet 元数据、写入范围、行列数和写后读回结果。
- 创建操作返回的 file token、URL，以及类型/token/标题读回；认证凭证不出现在输出中。
- `folder_token` 只记录为脱敏后的请求绑定，不作为已读回字段。

### 验收

- 创建后新 token 可读、至少存在一个 sheet，且 `drive +inspect` 的类型、token、标题与创建请求一致；初始表头和数据存在时，首个 sheet 的完整矩阵也必须逐格一致。
- CSV 写入前目标唯一，写入后完整范围的行列数和全部单元格逐格一致。
- API 成功但读回不一致时判定失败，不把接口受理等同于写入完成。
