---
name: lx-txwendang
description: 腾讯文档发布 Skill。将本地 Excel 数据批量发布到腾讯文档在线表格，统一管理腾讯文档 OpenAPI 凭证、运营主体目标缓存、dry-run 预览和发布结果输出。适用于发布到腾讯文档、腾讯文档发布、推送到线上、txwendang、lx-txwendang。
agent_created: true
---

# lx-txwendang — 腾讯文档发布

## 定位

本 Skill 只负责“发布到腾讯文档”。业务 Skill 负责生成本地数据，发布动作统一调用本 Skill。

当前支持两条发布通道：

- 个人版/旧 OpenAPI：使用 `lxx_share.tdocs_api`，配置统一读取 `config/fog_config.yaml` 的 `lx_txwendang.tdocs` 段。
- 企业版/SaaS MCP：使用 `scripts/saas_mcp.py` 调用全局 `tencent-saas-docs` 的 MCP 服务，默认读取 `~/.workbuddy/mcp.json` 中 `mcpServers.tencent-docs.headers.Authorization`。

本 Skill 负责目标缓存、dry-run 预览、限流退避和发布结果输出。

## 触发场景

- 用户要求“发布到腾讯文档”“推送到线上”“腾讯文档发布”
- 其他 Skill 已生成 Excel 输出目录，需要批量写入在线表格
- 需要检查腾讯文档 OpenAPI 凭证或目标运营主体缓存
- 需要在企业版根文件夹下创建或补齐运营主体文件夹和表格

## 前置条件

- `config/fog_config.yaml` 中 `lx_txwendang.tdocs.openapi.client_id`、`access_token`、`open_id` 已配置
- `config/fog_config.yaml` 中 `lx_txwendang.tdocs.root_folder_id` 已配置
- `assets/entity_cache.json` 已有运营主体到腾讯文档目标的映射

不要在 `.workbuddy/skills/lx-txwendang/assets/config.yaml` 写新配置；运行时统一读取 `config/fog_config.yaml`。

## 企业版 SaaS MCP

企业版能力走 `tencent-saas-docs` MCP，不走旧 `lxx_share.tdocs_api`。默认配置位置：

```text
~/.workbuddy/mcp.json
```

关键字段：

```json
{
  "mcpServers": {
    "tencent-docs": {
      "url": "https://saas.docs.qq.com/openapi/mcp",
      "headers": {
        "Authorization": "..."
      }
    }
  }
}
```

不要输出或提交 `Authorization` 值。也可以通过环境变量 `TENCENT_DOCS_TOKEN` 覆盖。

### 补齐企业版主体结构

按对接人从 `lx_shujuku.operator_brand` 查询运营主体，并在企业版根文件夹下补齐：

```text
{运营主体}-运营主体/
  {运营主体}-大盘数据日报
  {运营主体}-日常信息
  {运营主体}-背审申诉
  {运营主体}-静默乘客
```

预览（不写腾讯文档，不搜索线上时不会触发 SaaS MCP 调用）：

```bash
python .workbuddy/skills/lx-txwendang/scripts/ensure_enterprise_structure.py \
  --person 雷维亮 \
  --root-folder-id TlznihwNLTGuzisgAg \
  --dry-run --no-search
```

执行：

```bash
python .workbuddy/skills/lx-txwendang/scripts/ensure_enterprise_structure.py \
  --person 雷维亮 \
  --root-folder-id TlznihwNLTGuzisgAg \
  --min-interval 5 \
  --retries 3 \
  --rate-limit-sleep 600
```

如果 SaaS MCP 返回 `400007 / You have reached access limit`，脚本会按参数等待重试；如果仍失败，会保留已成功写入的缓存，下次可续跑。

企业版缓存默认路径：

```text
.workbuddy/skills/lx-txwendang/assets/enterprise_entity_cache.json
```

缓存包含企业版文件夹 ID 和各表格 ID，不进入版本控制。

## 批量发布 Excel 目录

适用于拆表输出目录，文件名格式为：

```text
{运营主体}_{描述}.xlsx
```

预览：

```bash
python .workbuddy/skills/lx-txwendang/scripts/publish_excel_folder.py \
  "workspace/01主体拆表/输出/<输出目录>" \
  --sheet-name "0601司机明细" \
  --dry-run
```

确认预览后执行：

```bash
python .workbuddy/skills/lx-txwendang/scripts/publish_excel_folder.py \
  "workspace/01主体拆表/输出/<输出目录>" \
  --sheet-name "0601司机明细"
```

脚本会执行：

1. 扫描目录中的 Excel 文件
2. 从 `entity_cache.json` 读取每个运营主体的 `file_id`
3. 为每个目标表格新增 sheet
4. 将 Excel 第一张工作表写入新 sheet
5. 输出每个运营主体的 `sheet_id`

## 缓存

默认缓存路径：

```text
.workbuddy/skills/lx-txwendang/assets/entity_cache.json
```

缓存格式：

```json
{
  "schema_version": 1,
  "entities": {
    "拼哒出行": {
      "file_id": "腾讯文档表格 ID",
      "folder_id": "运营主体文件夹 ID",
      "url": "腾讯文档链接"
    }
  }
}
```

过渡期兼容：如果新缓存不存在，脚本会读取旧路径 `.workbuddy/skills/lx-zhutichaibiao/assets/entity_cache.json`；旧扁平 JSON 格式仍可读取，但会提示迁移到 `schema_version: 1`。

## OpenAPI 工具

验证凭证：

```bash
python .workbuddy/skills/lx-txwendang/scripts/tdocs_api.py --verify
```

首次设置：

```bash
python .workbuddy/skills/lx-txwendang/scripts/tdocs_api.py --setup
```

## 跨 Skill 依赖

| 消费方 | 依赖字段 | 用途 |
|--------|----------|------|
| `lx-zhutichaibiao` | `file_id`, `url` | 发布拆分结果、生成通知链接 |
| `lx-dapanribao` | `folder_id` | 创建日报表格时指定父文件夹 |

约束：

- 修改 `entity_cache.json` 结构或路径时，必须同步检查 `lx-zhutichaibiao` 和 `lx-dapanribao`
- `entity_cache.json` 必须通过 schema version 和必需字段校验后再使用
- 发布脚本必须先支持 `--dry-run`，确认后再写腾讯文档
- 不输出 access_token、refresh_token、client_secret
