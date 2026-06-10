---
name: lx-txsaasdocs
description: 腾讯文档企业版/SaaS API Skill。通过企业内部自建应用 access_token 调用腾讯文档 SaaS Open API，支持企业版文件查询、在线智能表子表和记录写入；不使用 MCP。适用于腾讯文档企业版、SaaS OpenAPI、txsaasdocs、lx-txsaasdocs、企业版文档 API 写入。
agent_created: true
---

# lx-txsaasdocs — 腾讯文档企业版 API

## 定位

本 Skill 用于通过 HTTPS Open API 操作腾讯文档企业版/SaaS 文档，不使用 MCP。

当前封装已覆盖官方文档中可确认的接口面：

- 企业内部应用 `access_token` 获取
- Drive 文件信息查询
- 在线智能表：查询/新增子表
- 在线智能表：追加记录

普通“在线表格”的 range 写入接口尚未在已核对的企业版 SaaS 文档中确认，不要把个人版 `spreadsheet/v3` 端点直接套到企业版。需要写普通在线表格时，先补官方端点或实测验证，再扩展本 Skill。

## 配置

共享模板只提交空配置。真实凭证写到项目根目录 `config/fog_config.yaml` 的 `lx_txsaasdocs` 段，不要提交 token 和 secret。

必填配置：

```yaml
lx_txsaasdocs:
  api:
    base_url: "https://<企业腾讯文档域名>"
    token_endpoint: "https://<企业管理后台给出的Token端点>"
    client_id: ""
    client_secret: ""
```

`scripts/saas_openapi.py --config-path` 只用于显式调试或临时验证；默认运行入口必须读取项目根配置。

`token_endpoint` 来自企业管理后台自建应用的“端点信息”。官方认证文档说明该端点使用 `POST`，`Content-Type` 为 `application/x-www-form-urlencoded`，参数为 `client_id`、`client_secret`、`grant_type=client_credentials`。

## 常用命令

验证认证配置：

```bash
python .workbuddy/skills/lx-txsaasdocs/scripts/saas_openapi.py verify-auth
```

查询文件信息：

```bash
python .workbuddy/skills/lx-txsaasdocs/scripts/saas_openapi.py get-file <file_id>
```

查询智能表子表：

```bash
python .workbuddy/skills/lx-txsaasdocs/scripts/saas_openapi.py list-smartsheets <file_id>
```

新增智能表子表：

```bash
python .workbuddy/skills/lx-txsaasdocs/scripts/saas_openapi.py add-smartsheet <file_id> --title "日常信息"
```

追加智能表记录，先 dry-run：

```bash
python .workbuddy/skills/lx-txsaasdocs/scripts/saas_openapi.py add-records <file_id> <sheet_id> \
  --records-json records.json \
  --dry-run
```

确认后执行：

```bash
python .workbuddy/skills/lx-txsaasdocs/scripts/saas_openapi.py add-records <file_id> <sheet_id> \
  --records-json records.json \
  --confirmed
```

`records.json` 可以是：

```json
[
  {
    "品牌": [{"type": "text", "text": "示例品牌"}],
    "城市": [{"type": "text", "text": "示例城市"}],
    "数量": 12
  }
]
```

也可以直接传官方 `addRecords` 请求体。

## 安全边界

- 不读取、不输出 `client_secret` 和 `access_token`。
- 写入命令必须先 `--dry-run`，正式写入必须显式传 `--confirmed`。
- 如果 API 返回错误，只报告真实错误码、message 和 `X-Trace-Id`，不编造成功结果。
- 企业版权限、空间、普通在线表格 range 写入能力必须以官方文档或真实验证为准。

## 参考文档

- 企业内部应用 access_token: `https://identity.tencent.com/docs/openapi/authentication/app-access-token-internal/`
- 腾讯文档 SaaS 开放接口: `https://docs.qq.com/open/document/saas/`
- 腾讯文档 SaaS 文件接口索引: `https://docs.qq.com/open/document/saas/openapi/file/`
- 腾讯文档 SaaS 在线智能表接口索引: `https://docs.qq.com/open/document/saas/openapi/smartsheet/`
