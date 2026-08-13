# FOG 共享工作区协作说明

> 本文件是面向国内 WorkBuddy 与 Windows 同事的共享治理入口。Skill 清单看 `SKILLS.md`，具体流程看对应 `SKILL.md`；维护者私人工作区、内部迁移和个人凭证不属于本仓。

## 1. 接手顺序与真源

1. 确认仓根、分支和 `git status`，保留同事已有改动。
2. 读取 `AGENT.md`、`SKILLS.md` 和目标 Skill 的完整 `SKILL.md`。
3. 涉及业务文件时动态枚举真实文件名；不能只依赖受 `.gitignore` 影响的 Git 文件集合。
4. 涉及数据库时先确认数据源、库/schema、权限和只读/写入边界。

真源分工：

- `AGENT.md`：长期共享规则，不维护手写 Skill 大表。
- `SKILLS.md`：由共享仓真实目录生成的索引。
- 各 `SKILL.md`：输入、输出、安全边界和验收流程。
- `config/fog_config.yaml.example`：可共享配置字段模板。
- 操作者自己的 `config/fog_config.yaml`：真实配置，保持 gitignored。

## 2. 项目与运行边界

FOG 是 LXX 出行业务运营自动化的同事共享工作区，只包含可复用 Skill、跨平台工具、配置模板和空 workspace 结构。

- 默认环境为 Windows + 国内 WorkBuddy，不假设具备 Codex、OpenAI `image_gen`、Mac 绝对路径或维护者私有脚本。
- 优先提供 Python、PowerShell 和 `.cmd` 入口；发现 Codex-only、Mac-only 或维护者配置依赖时先停下，不照搬执行。
- 标准流程为 `配置检查 -> 枚举输入 -> dry-run -> 明确确认 -> 写入/输出 -> 读回验收`。
- 内部导入、数据库迁移、维护者闭环和私人 Skill 不属于共享版。

## 3. 配置与凭证安全

- 仓库不得包含真实账号、token、Cookie、数据库密码、邮箱授权码、个人路径、业务原表、运行输出或缓存。
- 真实配置只放 `config/fog_config.yaml`；不得写入 `SKILL.md`、脚本、日志、命令参数或 Git。
- 新增共享配置项时同步更新 example、相关 Skill 文档和检查逻辑。
- 不新增面向同事的 per-Skill 真实配置入口；统一从根配置读取。
- 外部 ZIP/附件必须校验路径穿越、符号链接、文件类型、大小、成员数、压缩比和重复输出名。

## 4. Skill 治理

真实 Skill 目录是 `.workbuddy/skills/<skill-name>/`。索引生成和检查命令：

```bash
python3 tools/generate_skill_index.py
python3 tools/generate_skill_index.py --check
```

- 标准共享 Skill 的 frontmatter 只含 `name`、`description`，并具备 `agents/openai.yaml` 和唯一的 `## 执行契约`、`### 输入`、`### 输出`、`### 验收`。
- `SKILLS.md` 必须与真实共享目录一致；维护者私有 Skill 不以“历史保留”名义滞留在 FOG。
- 高风险写入、认证会话和维护者能力不得允许无条件隐式调用。
- 修改 Skill 后必须重生成索引，并运行该 Skill 自身测试或 smoke。

`lx_shujuku` 固定规则：

- 真源文件为 `SKILL.md`、`assets/schema.json`、`references/table_catalog.md`；表数、字段和注释不得手猜。
- SQL 生成和生产查询性能规则见 `references/sql-query-performance.md`。
- schema 更新顺序为 `schema-diff -> refresh-schema --yes -> describe/单测 -> schema-diff`。
- 默认受限查询命中上限时只能称“可能截断”；完整结果使用 `query --full`，只有前后计数、稳定唯一排序、双遍分页 hash 和返回总数全部一致时才能声明完整。
- 刷新产生的 `*.bak.*` 是本地备份，不提交。

## 5. 数据与操作准确性

- 只报告实际读取或执行结果；失败、无权限、无结果、截断和 schema 漂移分别说明，不补假数据。
- 查询至少记录数据源、时间范围、过滤条件、结果粒度、总数、返回行数、分页和完整性状态。
- 同事的数据库查询范围仅限通过 `lx_shujuku` 只读访问公司 `dataReporting`；不得要求、配置或使用维护者的 RDS 连接，也不得把 RDS 表、索引或操作流程写成共享版前提。
- 写飞书、批量回填、移动文件、生成图片、付费 API 和数据库写入默认先 dry-run，真实动作需要明确确认和读回。
- 原始业务文件不覆盖；失败、部分成功或未确认时不归档源文件。
- Windows 使用面优先保证 `tools/windows/install.ps1` 和 `tools/windows/check.ps1` 可用。

### 公司库只读 SQL 性能门禁

- 生成 SQL 前先核对当前字段名、字段类型和 schema 漂移；涉及索引判断时还要核对完整索引列顺序。缓存 schema 和字段级 `PRI/MUL` 标记不能单独证明复合索引结构，也不能据此声称查询“已命中索引”。
- `JOIN`、`WHERE` 默认使用可搜索的裸字段条件。候选连接或过滤字段上不得使用 `TRIM`、`CAST`、`CONVERT`、`COLLATE`、`UPPER`、`LOWER`、日期函数、算术表达式或前导通配 `LIKE '%x'` 来临时兼容数据。
- JOIN 两侧字段的类型、字符集或排序规则不兼容时停止并报告；不得用运行时函数转换掩盖。`LEFT JOIN` 与 `INNER JOIN` 必须按业务语义选择，不得仅以性能为由互换。
- 大表或数据量未知的事实表查询必须限定业务范围，优先提供时间范围及必要的品牌、城市等过滤，只查询所需字段，避免 `SELECT *`。日期范围优先使用半开区间；字符串日期字段必须先确认格式可比较。
- 普通样例/Top N 查询使用合理 `LIMIT`；`LIMIT` 只限制返回量，不代表避免全表扫描。要求完整结果时必须走 `lx_shujuku query --full`。
- 聚合查询只要求非聚合输出字段进入 `GROUP BY`；单值聚合可以不分组。`COUNT(*)` 只表示行数，不得替代业务指标求和。
- 新增或修改的大表 JOIN、聚合查询在执行前先运行普通 `EXPLAIN`。大事实表出现未解释的 `key = NULL`、`type = ALL` 或扫描范围明显失控时停止执行。
- 默认禁止使用 `EXPLAIN ANALYZE`、`FORCE INDEX` 或提出索引 DDL；需要这些动作时交由维护者联系技术/DBA处理。

## 6. Workspace 约定

`workspace/00todo/` 是未归类事项入口；已有业务区域包括主体拆表、数据导入、数据报表、数据分析、后台操作、端内宣传图、端外海报图、表格同步和农夫协作。

`workspace/` 只提交空目录占位。业务文件、处理日志、输出表、图片、压缩包和缓存不得进入 Git。

## 7. 私人源仓与共享仓

- 私人 `p-fog` 与本仓是独立 Git 仓；共享内容由私人仓白名单同步，本仓不会接收全部私人文件。
- 自动同步只新增或更新白名单文件，不删除本仓内容，不覆盖 `.gitignore`、`README.md`、`AGENT.md`、`SKILLS.md` 和本仓索引生成器。
- 维护者发布共享快照使用私人仓 `lx-fogshare`；同事只使用本仓 `lx-update` 从 `pxiaolei/FOG` 的 `main` 分支检查和快进更新，不直接接触私人仓。
- `lx-update` 必须先只读检查，再绑定远端提交显式确认；本地脏改动、分支分叉、未授权远端删除、受保护路径或未追踪文件冲突一律停止，不自动 stash、reset、清理或合并。固定退役清单中的删除也必须逐文件展示后才可随已确认 commit 快进。
- 同步前目标仓必须干净；同步前后执行敏感信息扫描、逐文件 diff 和测试。
- 同步工具不 commit、不 push；不得用 `git add -A` 夹带同事文件。
- 禁止分享真实配置、`.env`、业务数据、输出、缓存、日志、私人 Skill、内部迁移、个人路径和凭证。
