# FOG

LXX 出行业务运营自动化 Skill 工作区。

## 1. 后续更新说明

同事如果之前已经有本地 `FOG` 项目文件夹，后续以 GitHub 仓库 `pxiaolei/FOG` 的 `main` 分支为准更新代码和共享 Skill。本地个人配置、业务文件、运行输出和缓存不要提交，也不要被更新覆盖。

每位同事需要维护自己的真实配置：

- 模板文件：[config/fog_config.yaml.example](https://github.com/pxiaolei/FOG/blob/main/config/fog_config.yaml.example)
- 真实配置：`config/fog_config.yaml`
- 真实配置里填写个人账号、token、目录、图片 API Key、腾讯文档企业版 API 凭证等
- `config/fog_config.yaml` 不进入 GitHub

常规更新命令：

```bash
git status --short
git pull --ff-only
python tools/fog.py migrate-config
python tools/fog.py init
python tools/fog.py check
```

Windows 首次初始化或环境检查可用：

```powershell
.\tools\windows\install.ps1
.\tools\windows\check.ps1
```

给 AI 的更新提示词：

```text
请在我的 FOG 项目文件夹里操作。先运行 git status --short 检查本地状态。
以 https://github.com/pxiaolei/FOG 的 main 分支为准更新共享代码和 Skill。
不要覆盖 config/fog_config.yaml、workspace/、.workbuddy/skills/*/assets/config.yaml、缓存和业务输出。
如果 config/fog_config.yaml 不存在，请按 config/fog_config.yaml.example 创建后提醒我填写。
如果我旧目录里已有配置项，请帮我把能确认的配置项迁移到 config/fog_config.yaml，但不要提交真实配置。
如果 config/fog_config.yaml 已存在，请运行 python tools/fog.py migrate-config 补新增配置项。
更新后运行 python tools/fog.py init 和 python tools/fog.py check。
如果 git status 里有我自己的改动，先告诉我具体文件，不要直接覆盖。
```

## 2. 文件夹结构

```text
FOG/
├── config/                     # 配置模板和本地真实配置
│   ├── fog_config.yaml.example # 共享配置模板，进入 GitHub
│   └── fog_config.yaml         # 每个人自己的真实配置，不进入 GitHub
├── .workbuddy/skills/          # WorkBuddy 可调用的共享 Skill
├── tools/                      # 初始化、更新检查、模板导出工具
└── workspace/                  # 业务文件工作区，业务内容不进入 GitHub
    ├── 00todo/                 # 待办事项追踪
    ├── 01主体拆表/             # 输入、输出、原表存档、处理日志
    ├── 02数据导入/             # 数据导入加工
    ├── 03数据报表/             # 日报、周报、月报、其他报表
    ├── 04数据分析/             # 数据探索和异动分析
    ├── 05策略活动/             # 活动策划、竞品策略、后台导入表
    ├── 06后台操作/             # SaaS 后台操作材料
    ├── 07共补活动/             # 共补策略处理
    ├── 08端内宣传图/           # 端内宣传物料
    ├── 09端外海报图/           # 端外海报图、活动 TXT、临时图和元数据
    ├── 10表格同步/             # A 表到 B 表同步
    └── 12农夫协作/             # 大文档拆分、主体填写、品牌城市回填
        ├── 待处理/
        ├── 输出/
        └── 处理日志/
```

## 3. Skill 说明和使用

| Skill | 大致用途 | 常见说法 |
|---|---|---|
| `lx_shujuku` | 查询公司 dataReporting，只读访问业务表，加载 `operator_brand` 码表 | “查一下数据库”“查活动数据”“看 operator_brand” |
| `lx-zhutichaibiao` | 按运营主体、城市、品牌拆分 Excel，生成各主体文件 | “把这个表按运营主体拆一下”“按城市拆表” |
| `lx-txsaasdocs` | 腾讯文档企业版/SaaS API，获取 token、查文件、写智能表 | “用企业版腾讯文档 API 写入”“查这个企业版文档” |
| `lx-biaogetongbu` | 本地 Excel 或腾讯文档企业版表格的 A 表到 B 表同步，支持按 key 回填 | “把 A 表同步到 B 表”“按品牌城市回填大文档” |
| `lx-tongzhi` | 按商家、司机、线下渠道生成短信、push、微信群通知和操作说明，并做禁词检查 | “生成商家通知”“写司机 push”“检查禁词” |
| `lx-nongfu` | 农夫协作文档编排：大文档拆分到运营主体、通知填写、按品牌+城市回填大文档 | “跑农夫协作流程”“把大文档拆给各主体填写” |
| `lx-dapanribao` | 按对接人生成运营主体日报和腾讯文档企业版发布计划 | “生成大盘日报”“做今日日报” |
| `lx-haibao` | 根据城市活动 TXT 生成司机活动海报，支持 dry-run 和确认后出图 | “根据这个 TXT 生成海报”“检查海报配置” |
| `lx-init` | 旧初始化兼容入口；新流程优先使用 `tools/fog.py` | “初始化 FOG”“检查配置” |
| `lxx_share` | 共享 Python 基础模块，给其他 Skill 复用，不直接触发 | 不直接使用 |

使用时优先用自然语言告诉 WorkBuddy 目标、文件路径、是否要 dry-run。涉及写入腾讯文档、生成图片、移动文件、回填大文档的动作，默认先预览，确认后再执行。

## 4. 设计原则

- **GitHub 为准**：共享代码、共享 Skill、配置模板以后以仓库 `main` 分支为准。
- **本地配置隔离**：账号、token、个人路径、默认对接人写在 `config/fog_config.yaml`，不写进 Skill。
- **输入输出分离**：每个业务流程尽量使用 `待处理 -> 输出/已处理 + 处理日志`。
- **原表保留**：原始文件不直接覆盖，必要时进入存档或保留备份。
- **写入先预览**：腾讯文档写入、图片生成、批量同步、回填大文档前先 dry-run 或明确确认。
- **品牌城市匹配**：涉及运营主体回填时，必须按品牌+城市定位，不能整表直接覆盖。
- **码表在线化**：共享模板不分发本地码表 Excel，统一通过 `lx_shujuku` 查询公司库 `operator_brand`。
