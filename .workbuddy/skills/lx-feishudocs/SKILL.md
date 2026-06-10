---
name: lx-feishudocs
description: 飞书云文档普通电子表格 Skill。通过 WorkBuddy 内置 lark-cli 操作飞书 Sheets 普通表格，支持账号状态检查、创建普通电子表格、读取工作簿信息、写入 CSV 到单元格区域、读取 CSV 验证。适用于飞书云文档、飞书普通表格、Feishu Sheets、Lark Sheets，不用于飞书多维表格/Base/智能表格。
agent_created: true
location: project
---

# lx-feishudocs — 飞书普通电子表格

## 定位

本 Skill 是 FOG 的飞书云文档后端，负责所有线上普通表格发布和读写链路。

当前只面向**飞书普通电子表格 Sheets**：

- 创建普通电子表格。
- 查询工作簿和 sheet 列表。
- 向普通 sheet 写入 CSV/二维表数据。
- 从普通 sheet 读取 CSV 做写后验证。

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
  --title "FOG飞书普通表格测试"
```

写入 CSV 到普通 sheet：

```bash
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py csv-put \
  --spreadsheet-token "<spreadsheet_token>" \
  --sheet-id "<sheet_id>" \
  --start-cell A1 \
  --csv-file rows.csv
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
python .workbuddy/skills/lx-feishudocs/scripts/feishu_sheets.py smoke
```

## 安全边界

- 不输出 app secret、access token、refresh token。
- 写入外部飞书表格前先 dry-run 或由上层业务 Skill 明确 `--confirmed`。
- 只操作普通电子表格；看到 Base、多维表格、智能表格需求时停止并说明边界。
- 写后验证必须再次读取目标范围，不能只相信写接口返回。

## 给上层 Skill 的约定

- 日报发布目标：飞书普通电子表格，每个运营主体一个 spreadsheet，每天一个 sheet。
- 农夫协作目标：飞书普通电子表格，按品牌+城市定位回填。
- A/B 表同步：`lx-biaogetongbu --online --online-backend feishu`。
