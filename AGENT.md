# FOG 共享工作区协作说明

> 目标受众：AI Agent（WorkBuddy / Codex）。本文档只描述分享给同事使用的 FOG 工作区，不包含私人工作区、内部数据库迁移和个人凭证。

## 1. 项目定位

FOG 是 LXX 出行业务运营自动化 Skill 工作区，面向同事的共享版只包含可复用的工具、配置模板、共享 Skill 和空 workspace 目录结构。

核心流程：

```text
配置检查 -> 业务文件放入 workspace -> 调用对应 Skill -> dry-run 预览 -> 确认后生成输出或写入飞书普通表格
```

共享版不携带真实账号、token、数据库密码、个人路径、业务原表、运行输出、缓存和本地私有 Skill。

## 2. 共享 Skill 清单

| Skill | 用途 | 主要输入/配置 |
|---|---|---|
| `lx_shujuku` | 查询公司 dataReporting，只读访问业务表和 `operator_brand` 码表 | `config/fog_config.yaml` |
| `lxx_share` | 共享 Python 基础模块，供其他 Skill 复用 | 不直接触发 |
| `lx-init` | 初始化和旧兼容检查入口；新流程优先用 `tools/fog.py` | `config/fog_config.yaml` |
| `lx-zhutichaibiao` | 按运营主体、城市、品牌拆分 Excel | workspace 文件 |
| `lx-feishudocs` | 飞书普通电子表格创建、读取、写入 | 飞书配置 |
| `lx-biaogetongbu` | A 表到 B 表同步，支持按 key 回填 | Excel/飞书表格 |
| `lx-tongzhi` | 生成商家、司机、线下渠道通知，并做禁词检查 | 业务事实和模板 |
| `lx-nongfu` | 农夫协作文档编排：拆分、通知、品牌城市回填 | workspace 文件和飞书配置 |
| `lx-dapanribao` | 生成运营日报和飞书普通表格发布计划 | 数据库只读配置 |
| `lx-celuehuodong` | 策略活动表处理、免佣卡和后台导入文件生成 | 活动表/模板文件 |
| `lx-haibao` | 根据活动 TXT 生成司机活动海报 | 图片 API 和品牌配置 |
| `lx-yuedufandian` | 月度返点规则留档、源 Excel 入库、计算并输出结果 | 返点源表和规则文件 |

内部导入、共补入库、个人数据库迁移等 Skill 不属于共享版；不要在共享工作区里假设存在。

## 3. 配置边界

- 共享模板：`config/fog_config.yaml.example`
- 每个人自己的真实配置：`config/fog_config.yaml`
- 真实配置不得提交到 Git，也不得写进 `SKILL.md`、脚本或 README。
- 新增共享配置项时，同时更新 `config/fog_config.yaml.example`、相关 Skill 文档和检查逻辑。
- 不要新增面向同事的 per-Skill `assets/config.yaml` 真实配置入口；真实配置统一放在根配置里。

## 4. 目录约定

```text
FOG/
├── config/
│   └── fog_config.yaml.example
├── .workbuddy/skills/
├── tools/
└── workspace/
    ├── 00todo/
    ├── 01主体拆表/
    ├── 02数据导入/
    ├── 03数据报表/
    ├── 04数据分析/
    ├── 05策略活动/
    ├── 06后台操作/
    ├── 07共补活动/
    ├── 08端内宣传图/
    ├── 09端外海报图/
    ├── 10表格同步/
    ├── 12农夫协作/
    └── 13月度返点计算/
```

`workspace/` 只提交空目录占位文件。真实业务文件、处理日志、输出表、图片、压缩包和缓存都不进入 Git。

## 5. 操作规则

- 修改前先读对应 `SKILL.md`、共享工具和配置模板。
- 涉及业务文件时，先枚举真实文件名，再读取和处理。
- 写入飞书普通表格、批量回填、移动文件、生成图片或可能产生费用的动作，默认先 dry-run。
- 不编造数据库结果、文件内容、行号、命令输出或执行结果；读不到就直接说明。
- 保持改动聚焦，不顺手重构无关代码。
- Windows 同事使用面优先保证 `tools/windows/install.ps1` 和 `tools/windows/check.ps1` 可用。

## 6. 分享边界

共享仓库只接收白名单内容：

- `.workbuddy/skills/` 下列入 `config/template_manifest.yaml` 的共享 Skill
- `tools/`
- `config/fog_config.yaml.example`
- 空 workspace 目录占位
- 共享 README/AGENT 文档

禁止分享：

- `config/fog_config.yaml`
- `config/personal_config.yaml`
- `config/database.yaml`
- `.env`
- 业务数据、导入文件、输出文件、缓存、日志
- 私人 skill、内部数据库迁移文件、个人路径和凭证

同步前后都要执行敏感信息扫描，并检查 `git status`。
