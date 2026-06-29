# FOG 共享工作区协作说明

> 目标受众：使用国内 WorkBuddy 的 Windows 同事，以及协助同事处理本仓的 AI Agent。本文档只描述分享给同事使用的 FOG 工作区，不包含维护者私人工作区、内部数据库迁移和个人凭证。

## 1. 项目定位

FOG 是 LXX 出行业务运营自动化 Skill 工作区，面向同事的共享版只包含可复用的工具、配置模板、共享 Skill 和空 workspace 目录结构。

默认运行环境：

- Windows 电脑。
- 国内 WorkBuddy，不默认具备 Codex、OpenAI `image_gen`、Mac 本机路径或维护者私有脚本。
- 能跨平台运行的 Python 脚本、`.cmd`、PowerShell 说明优先；遇到只适合维护者本机的说明时，先停下来确认，不要照搬执行。

核心流程：

```text
配置检查 -> 业务文件放入 workspace -> 调用对应 Skill -> dry-run 预览 -> 确认后生成输出或写入飞书普通表格
```

共享版不携带真实账号、token、数据库密码、个人路径、业务原表、运行输出、缓存和本地私有 Skill。

## 2. 共享 Skill 清单

下表按当前 `FOG` 仓库里的共享目录描述。维护者从私人 `p-fog` 同步更新时，只会覆盖白名单内容；已有但未纳入白名单的历史 Skill 不代表每次都会自动更新。

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
| `lx-hhbbu` | 从公司库按日期、城市、品牌导出 B补和售卡商家收入数据 | 公司库只读配置 |
| `lx-zhoubao` | 生成周报所需的日/周聚合和报告 | 数据库只读配置 |
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
- 配置项按用途拆分：共享模板只放字段、说明和空占位；个人账号、token、图片 API Key、飞书偏好、本地目录只放自己的 `config/fog_config.yaml`。
- 如果某个 Skill 文档提到维护者私有配置、Codex-only 能力或 Mac 绝对路径，同事侧默认不可用，需要改成 WorkBuddy/Windows 可运行流程后再使用。

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
- 共享 Skill 的新增能力默认要考虑 Windows 路径、PowerShell/`.cmd` 调用、中文文件名和国内网络环境。
- 生成图片、调用付费 API、写入飞书、批量改文件前必须先 dry-run 或让用户明确确认。

## 6. 分享边界

共享仓库只接收白名单内容：

- `.workbuddy/skills/` 下由维护者在 `p-fog` 白名单中列出的共享 Skill
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
