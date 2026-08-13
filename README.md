# FOG

LXX 出行业务运营自动化 Skill 工作区。

默认使用对象是 Windows 电脑上的国内 WorkBuddy 用户。仓库里的共享 Skill、配置模板和脚本应优先按这个环境理解；维护者在 Codex 或 Mac 本机上的兜底能力不作为同事默认前提。

## 1. 后续更新说明

后续更新以 GitHub 仓库 `pxiaolei/FOG` 的 `main` 分支为准。更新时只同步共享代码、共享 Skill 和配置模板；本地个人配置、业务文件、运行输出和缓存都要保留。

每位同事需要维护自己的真实配置：

- 模板文件：[config/fog_config.yaml.example](https://github.com/pxiaolei/FOG/blob/main/config/fog_config.yaml.example)
- 真实配置：`config/fog_config.yaml`
- 真实配置里填写个人账号、目录、图片 API Key、飞书普通表格偏好等
- `config/fog_config.yaml` 不进入 GitHub

同事更新时直接对 WorkBuddy 说：

```text
使用 lx-update 检查 FOG 更新；如果可以快进，先告诉我远端 commit 和变更文件，等我确认后再更新。
```

也可以手工运行：

```bash
python .workbuddy/skills/lx-update/scripts/update_fog.py check
python .workbuddy/skills/lx-update/scripts/update_fog.py apply --confirmed <check 输出的 remote_commit>
```

`lx-update` 不会自动 stash、reset、合并或覆盖本地配置。检测到未提交改动、分支分叉、未授权远端删除、受保护路径或本地文件冲突时会停止；固定退役清单内的 Skill 删除也会先逐文件展示，只有确认完整远端 commit 后才随 fast-forward 生效。更新后真实配置仍需按提示另行检查，不能把配置改写混进代码更新。

第一次 bootstrap：如果同事当前版本还没有 `lx-update`，先让 WorkBuddy 只读检查 `git status` 和 `origin/main` 差异；工作区不干净就停止，干净且仅可 fast-forward 时，再由同事确认目标 commit 后执行一次 `git fetch` + `git merge --ff-only`。首次拉到 `lx-update` 后，后续不要再使用临时提示词。

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
    ├── 05策略活动/             # 历史业务工作区占位，不代表对应 Skill 仍共享
    ├── 06后台操作/             # SaaS 后台操作材料
    ├── 07共补活动/             # 历史业务工作区占位，不代表对应 Skill 仍共享
    ├── 08端内宣传图/           # 端内宣传物料
    ├── 09端外海报图/           # 端外海报图、活动 TXT、临时图和元数据
    ├── 10表格同步/             # A 表到 B 表同步
    ├── 12农夫协作/             # 大文档拆分、主体填写、品牌城市回填
    │   ├── 待处理/
    │   ├── 输出/
    │   └── 处理日志/
    └── 13月度返点计算/         # 历史业务工作区占位，不代表对应 Skill 仍共享
```

## 3. Skill 说明和使用

| Skill | 大致用途 | 常见说法 |
|---|---|---|
| `lx_shujuku` | 查询公司 dataReporting，只读访问业务表，加载 `operator_brand` 码表 | “查一下数据库”“查活动数据”“看 operator_brand” |
| `lx-zhutichaibiao` | 按运营主体、城市、品牌拆分 Excel，生成各主体文件 | “把这个表按运营主体拆一下”“按城市拆表” |
| `lx-feishudocs` | 飞书云文档普通电子表格后端，创建、读取、写入 Feishu Sheets | “用飞书表格发布”“写入飞书普通表格” |
| `lx-biaogetongbu` | 本地 Excel 或飞书普通表格的 A 表到 B 表同步，支持按 key 回填 | “把 A 表同步到 B 表”“按品牌城市回填大文档” |
| `lx-tongzhi` | 按商家、司机、线下渠道生成短信、push、微信群通知和操作说明，并做禁词检查 | “生成商家通知”“写司机 push”“检查禁词” |
| `lx-nongfu` | 农夫协作文档编排：大文档拆分到运营主体、通知填写、按品牌+城市回填大文档 | “跑农夫协作流程”“把大文档拆给各主体填写” |
| `lx-haibao` | 根据城市活动 TXT 生成司机活动海报，支持 dry-run 和确认后出图 | “根据这个 TXT 生成海报”“检查海报配置” |
| `lx-init` | 旧初始化兼容入口；新流程优先使用 `tools/fog.py` | “初始化 FOG”“检查配置” |
| `lx-update` | 检查并安全快进同事本地 FOG，共享 Skill 与代码随 GitHub 更新 | “检查 FOG 更新”“更新共享 Skill” |
| `lxx_share` | 共享 Python 基础模块，给其他 Skill 复用，不直接触发 | 不直接使用 |

使用时优先用自然语言告诉 WorkBuddy 目标、文件路径、是否要 dry-run。涉及写入飞书普通表格、生成图片、移动文件、回填大文档的动作，默认先预览，确认后再执行。

当前共享仓只保留上表 10 个 Skill。`lx-zhoubao`、`lx-hhbbu`、`lx-dapanribao`、`lx-celuehuodong`、`lx-yuedufandian` 属于维护者私有能力，不在 FOG 提供，也不会从私人源仓再次同步回来。

## 4. 设计原则

- **GitHub 为准**：共享代码、共享 Skill、配置模板以后以仓库 `main` 分支为准。
- **本地配置隔离**：账号、token、个人路径、默认对接人写在 `config/fog_config.yaml`，不写进 Skill。
- **配置模板分离**：共享仓只提交 `config/fog_config.yaml.example` 这类模板；每个人自己的真实配置不提交。
- **Windows 优先**：共享脚本和说明优先考虑 Windows + WorkBuddy，路径示例不要只适用于维护者的 Mac。
- **输入输出分离**：每个业务流程尽量使用 `待处理 -> 输出/已处理 + 处理日志`。
- **原表保留**：原始文件不直接覆盖，必要时进入存档或保留备份。
- **写入先预览**：飞书普通表格写入、图片生成、批量同步、回填大文档前先 dry-run 或明确确认。
- **品牌城市匹配**：涉及运营主体回填时，必须按品牌+城市定位，不能整表直接覆盖。
- **码表在线化**：共享模板不分发本地码表 Excel，统一通过 `lx_shujuku` 查询公司库 `operator_brand`。
