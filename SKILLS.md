# FOG Skill 索引

> 本文件由 `python3 tools/generate_skill_index.py` 根据真实目录生成；不要手工维护 Skill 清单。具体流程、输入输出和安全边界以各 Skill 的 `SKILL.md` 为准。

当前共 11 个 Skill。`显式` 表示 `allow_implicit_invocation: false`，必须由用户明确点名或确认后使用。

| Skill | 显示名 | 调用策略 | 入口 | 描述 |
| --- | --- | --- | --- | --- |
| `lx-biaogetongbu` | 表格同步 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-biaogetongbu/SKILL.md) | 表格同步工具。用于把 A 表中的记录按字段映射同步到 B 表，覆盖静默乘客登记、背审登记、主体拆表结果同步、农服大文档按品牌城市回填等场景。支持本地 Excel append / update-by-key；在线后端只支持飞书普通电子表格 feishu。当用户要求表格同步、从 A 表同步到 B 表、同步背审申诉、静默乘客或拆表结果时使用。 |
| `lx-feishudocs` | 飞书普通表格 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-feishudocs/SKILL.md) | 飞书云文档普通电子表格 Skill。通过 WorkBuddy 内置 lark-cli 操作飞书 Sheets 普通表格，支持账号状态检查、创建普通电子表格、读取工作簿信息、写入 CSV 到单元格区域、读取 CSV 验证。适用于飞书云文档、飞书普通表格、Feishu Sheets、Lark Sheets，不用于飞书多维表格/Base/智能表格。 |
| `lx-haibao` | 端外海报生成 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-haibao/SKILL.md) | 司机活动海报生成。用于从城市活动 TXT 生成已配置品牌的司机活动海报；按 check、dry-run、confirmed sample/full generation 执行；自动按 TXT 文件名识别品牌；共享工作区默认只使用 KIE 图片 Provider；默认 hybrid 模式把模板图和真实 Logo 传给模型生成海报主体，再由脚本贴入真实二维码并逐张验证。 |
| `lx-init` | 初始化工作区 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-init/SKILL.md) | 工作区初始化：确认目录，缺则补齐 Python/Node/Git，安装项目依赖，并启动本机窗口填写账号配置。仅在用户明确要求初始化、安装工作区或 lx-init 时使用。 |
| `lx-kaicheng` | 开城前城市了解 | 可隐式路由 | [`SKILL.md`](.workbuddy/skills/lx-kaicheng/SKILL.md) | 合作伙伴开城前城市信息查询。当用户说“我要开xx城市”、询问开城前置条件、开城材料或城市营商环境时使用；基于随包城市资料回答，不用于后台开关城配置、经营数据查询或开城后的异动分析。 |
| `lx-nongfu` | 农夫协作文档 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-nongfu/SKILL.md) | 农夫/运营主体协作文档编排 Skill。用于把线下 Excel 或飞书普通表格大文档按运营主体拆分到各主体的日常信息表，新建填写 sheet，生成运营主体通知，并在主体填写完成后按品牌+城市回填大文档。适用于大文档拆分、农夫协作、运营主体填表、日常信息收集、主体回填、品牌城市回写等场景。 |
| `lx-tongzhi` | 触达通知生成 | 可隐式路由 | [`SKILL.md`](.workbuddy/skills/lx-tongzhi/SKILL.md) | 触达通知生成 Skill。根据同一份业务事实，按商家/运营主体、司机、线下渠道三类人群切换通知视角，生成短信、push、微信/群通知和操作说明，并按禁词与风险词规则校验。当用户要求通知、短信、push、群通知或面向特定人群的通知文案时使用；第一版只生成内容和校验报告，不发送消息。 |
| `lx-update` | 更新工作区 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-update/SKILL.md) | 检查当前工作区绑定仓库的版本，确认完整 commit 后更新并保护本机配置与业务文件。 |
| `lx-zhutichaibiao` | 运营主体拆表 | 显式 | [`SKILL.md`](.workbuddy/skills/lx-zhutichaibiao/SKILL.md) | 按运营主体/城市/品牌拆表工具。将待拆表格按公司库 operator_brand 码表中的运营主体、城市、品牌和对接人拆分成多个独立文件，打包输出。支持拆分后交给 lx-nongfu / lx-feishudocs 发布到飞书普通表格，并生成面向各运营主体的通知消息。触发词：拆主体表、主体拆表、lx-zhutichaibiao、zhutichaibiao、按运营主体拆、按城市拆、按品牌拆、纯品牌拆、生成通知、发消息给各主体。 |
| `lx_shujuku` | 公司数据库只读查询 | 可隐式路由 | [`SKILL.md`](.workbuddy/skills/lx_shujuku/SKILL.md) | 出行数据报表平台（dataReporting）公司数据库只读访问工具，提供只读 SQL、有界单遍游标分页、结构化证据包、表结构与白名单表索引元数据浏览、operator_brand 码表和业务查询模板。当用户要求查询公司数据库、dataReporting、宏鹄活动/运力/订单/卡券/详情、接起率或 TR 值时使用；不用于本地 RDS 查询或写库。 |
| `lxx_share` | LX共享基础模块 | 显式 | [`SKILL.md`](.workbuddy/skills/lxx_share/SKILL.md) | LX 共享基础模块，提供统一配置读取、公司库码表映射、Excel 工具和缓存工具，供 lx-zhutichaibiao、lx-haibao 等共享 Skill 通过 import 复用。仅作为代码依赖使用，不面向用户任务直接触发。 |

## 校验

```bash
python3 tools/generate_skill_index.py --check
```

该命令同时校验：Skill 名不重复、frontmatter 精确为 `name`/`description`、执行契约结构唯一、`agents/openai.yaml` 元数据和调用策略完整，以及本索引未漂移。
