---
name: lx-txdocs
description: 个人版腾讯文档发布 Skill。将本地 Excel 数据批量发布到个人版腾讯文档在线表格，统一管理腾讯文档个人版 OpenAPI 凭证、运营主体目标缓存、dry-run 预览和发布结果输出。适用于个人腾讯文档发布、txdocs、lx-txdocs；不要用于腾讯文档企业版/SaaS，企业版使用 lx-txsaasdocs。
agent_created: true
---

# lx-txdocs — 个人版腾讯文档发布

## 定位

本 Skill 只负责“发布到个人版腾讯文档”。业务 Skill 负责生成本地数据，发布动作统一调用本 Skill。

当前只支持个人版 OpenAPI：

- 使用 `lxx_share.tdocs_api`
- 配置统一读取 `config/fog_config.yaml` 的 `lx_txdocs.tdocs` 段
- 兼容读取旧配置段 `lx_txwendang.tdocs`，但新配置和新文档都使用 `lx_txdocs`

本 Skill 不接 MCP，不处理腾讯文档企业版/SaaS。企业版 API 写入统一放到 `lx-txsaasdocs`。

本 Skill 负责目标缓存、dry-run 预览和发布结果输出。

## 触发场景

- 用户要求“发布到个人版腾讯文档”“推送到个人版线上表格”“腾讯文档发布”
- 其他 Skill 已生成 Excel 输出目录，需要批量写入个人版在线表格
- 需要检查腾讯文档个人版 OpenAPI 凭证或目标运营主体缓存

## 前置条件

- `config/fog_config.yaml` 中 `lx_txdocs.tdocs.openapi.client_id`、`access_token`、`open_id` 已配置
- `config/fog_config.yaml` 中 `lx_txdocs.tdocs.root_folder_id` 已配置
- `assets/entity_cache.json` 已有运营主体到腾讯文档目标的映射

不要在 `.workbuddy/skills/lx-txdocs/assets/config.yaml` 写新配置；运行时统一读取 `config/fog_config.yaml`。

## 批量发布 Excel 目录

适用于拆表输出目录，文件名格式为：

```text
{运营主体}_{描述}.xlsx
```

预览：

```bash
python .workbuddy/skills/lx-txdocs/scripts/publish_excel_folder.py \
  "workspace/01主体拆表/输出/<输出目录>" \
  --sheet-name "0601司机明细" \
  --dry-run
```

确认预览后执行：

```bash
python .workbuddy/skills/lx-txdocs/scripts/publish_excel_folder.py \
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
.workbuddy/skills/lx-txdocs/assets/entity_cache.json
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

过渡期兼容：如果新缓存不存在，脚本会依次读取旧路径 `.workbuddy/skills/lx-txwendang/assets/entity_cache.json` 和 `.workbuddy/skills/lx-zhutichaibiao/assets/entity_cache.json`；旧扁平 JSON 格式仍可读取，但会提示迁移到 `schema_version: 1`。

## OpenAPI 工具

验证凭证：

```bash
python .workbuddy/skills/lx-txdocs/scripts/tdocs_api.py --verify
```

首次设置：

```bash
python .workbuddy/skills/lx-txdocs/scripts/tdocs_api.py --setup
```

## 跨 Skill 依赖

| 消费方 | 依赖字段 | 用途 |
|--------|----------|------|
| `lx-zhutichaibiao` | `file_id`, `url` | 发布拆分结果、生成通知链接 |

约束：

- 修改 `entity_cache.json` 结构或路径时，必须同步检查 `lx-zhutichaibiao`
- `entity_cache.json` 必须通过 schema version 和必需字段校验后再使用
- 发布脚本必须先支持 `--dry-run`，确认后再写腾讯文档
- 不输出 access_token、refresh_token、client_secret
