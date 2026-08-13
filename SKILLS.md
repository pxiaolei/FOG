# FOG 共享 Skill 索引

> 本文件由 `python3 tools/generate_skill_index.py` 根据共享仓真实目录生成；不要手工维护 Skill 表。流程和安全边界以各 Skill 的 `SKILL.md` 为准。

当前共 10 个 Skill：10 个标准共享契约，0 个历史保留项。

| Skill | 显示名 | 调用策略 | 状态 | 入口 | 描述 |
| --- | --- | --- | --- | --- | --- |
| `lx-biaogetongbu` | 表格同步 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-biaogetongbu/SKILL.md) | 表格同步工具。用于把 A 表中的记录按字段映射同步到 B 表，覆盖静默乘客登记、背审登记、主体拆表结果同步、农服大文档按品牌城市回填等场景。支持本地 Excel append / update-by-key；在线后端只支持飞书普通电子表格 feishu。当用户要求表格同步、从 A 表同步到 B 表、同步背审申诉、静默乘客或拆表结果时使用。 |
| `lx-feishudocs` | 飞书普通表格 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-feishudocs/SKILL.md) | 飞书云文档普通电子表格 Skill。通过 WorkBuddy 内置 lark-cli 操作飞书 Sheets 普通表格，支持账号状态检查、创建普通电子表格、读取工作簿信息、写入 CSV 到单元格区域、读取 CSV 验证。适用于飞书云文档、飞书普通表格、Feishu Sheets、Lark Sheets，不用于飞书多维表格/Base/智能表格。 |
| `lx-haibao` | 端外海报生成 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-haibao/SKILL.md) | 企业版 WorkBuddy 专用司机活动海报生成。用于从城市活动 TXT 生成已配置品牌的司机活动海报；按 check、dry-run、confirmed sample/full generation 执行；自动按 TXT 文件名识别品牌；同事共享默认只使用 KIE 图片 Provider；默认 hybrid 模式把模板图和真实 Logo 传给模型生成海报主体，再由脚本贴入真实二维码并逐张验证。 |
| `lx-init` | FOG旧初始化入口 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-init/SKILL.md) | FOG 旧初始化兼容 Skill。仅当用户明确提到 lx-init、FOG 初始化、初始化 FOG 或检查配置等旧入口时使用；新用户优先使用 tools/fog.py，本 Skill 只保留旧命令兼容。 |
| `lx-nongfu` | 农夫协作文档 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-nongfu/SKILL.md) | 农夫/运营主体协作文档编排 Skill。用于把线下 Excel 或飞书普通表格大文档按运营主体拆分到各主体的日常信息表，新建填写 sheet，生成运营主体通知，并在主体填写完成后按品牌+城市回填大文档。适用于大文档拆分、农夫协作、运营主体填表、日常信息收集、主体回填、品牌城市回写等场景。 |
| `lx-tongzhi` | 触达通知生成 | 可隐式路由 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-tongzhi/SKILL.md) | 触达通知生成 Skill。根据同一份业务事实，按商家/运营主体、司机、线下渠道三类人群切换通知视角，生成短信、push、微信/群通知和操作说明，并按禁词与风险词规则校验。当用户要求通知、短信、push、群通知或面向特定人群的通知文案时使用；第一版只生成内容和校验报告，不发送消息。 |
| `lx-update` | FOG 安全更新 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-update/SKILL.md) | FOG 同事侧安全更新工具。用户要求更新 FOG、同步共享 Skill、拉取最新版或检查 GitHub 更新时使用；只允许从 pxiaolei/FOG 的 main 分支做已确认的 fast-forward，不覆盖本地配置、业务文件或未提交改动。 |
| `lx-zhutichaibiao` | 运营主体拆表 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx-zhutichaibiao/SKILL.md) | 按运营主体/城市/品牌拆表工具。将待拆表格按公司库 operator_brand 码表中的运营主体、城市、品牌和对接人拆分成多个独立文件，打包输出。支持拆分后交给 lx-nongfu / lx-feishudocs 发布到飞书普通表格，并生成面向各运营主体的通知消息。触发词：拆主体表、主体拆表、lx-zhutichaibiao、zhutichaibiao、按运营主体拆、按城市拆、按品牌拆、纯品牌拆、生成通知、发消息给各主体。 |
| `lx_shujuku` | 公司数据库只读查询 | 可隐式路由 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lx_shujuku/SKILL.md) | 出行数据报表平台（dataReporting）公司数据库只读访问工具，提供只读 SQL、完整结果双遍分页验证、结构化证据包、表结构浏览、operator_brand 码表和业务查询模板。当用户要求查询公司数据库、dataReporting、宏鹄活动/运力/订单/卡券/详情、接起率或 TR 值时使用；不用于本地 RDS 查询或写库。 |
| `lxx_share` | LX共享基础模块 | 显式 | 标准共享契约 | [`SKILL.md`](.workbuddy/skills/lxx_share/SKILL.md) | LX 共享基础模块，提供统一配置读取、公司库码表映射、Excel 工具和缓存工具，供 lx-zhutichaibiao、lx-haibao 等共享 Skill 通过 import 复用。仅作为代码依赖使用，不面向用户任务直接触发。 |

## 校验

```bash
python3 tools/generate_skill_index.py --check
```

校验会动态枚举真实目录；标准共享契约还会检查 frontmatter、`agents/openai.yaml` 和唯一执行契约结构。历史保留项只表示文件仍在，不表示会随私人源仓自动更新。
