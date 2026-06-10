---
name: lx-zhutichaibiao
description: 按运营主体/城市/品牌拆表工具。将待拆表格按公司库 operator_brand 码表中的运营主体、城市、品牌和对接人拆分成多个独立文件，打包输出。支持拆分后发布到腾讯文档在线表格，并生成面向各运营主体的通知消息。触发词：拆主体表、主体拆表、lx-zhutichaibiao、zhutichaibiao、按运营主体拆、按城市拆、按品牌拆、纯品牌拆、生成通知、发消息给各主体。
agent_created: true
---

# 按运营主体/城市/品牌拆表工具

将待拆表格按运营主体、城市或品牌维度拆分，保留原表单元格格式。

## 能力路由

拆分是核心功能，发布和通知是可选分支，可独立触发：

| 用户意图 | 触发词 | 对应阶段 |
|---------|--------|---------|
| 拆分表格 | 拆主体表、主体拆表、lx-zhutichaibiao、zhutichaibiao、按运营主体拆、按城市拆、按品牌拆、纯品牌拆 | **阶段一** |
| 发布到线上 | 发布、发布到腾讯文档、推送到线上 | **阶段二** |
| 生成通知 | 生成通知、发消息给各主体、通知话术 | **阶段三** |

**典型流程**：拆分 →（可选）发布 →（可选）生成通知。但通知也可以不依赖发布，直接用缓存中的链接生成。

## 触发条件

拆分是核心触发条件，发布和通知为可选分支：

- **核心触发**：拆主体表、主体拆表、lx-zhutichaibiao、zhutichaibiao、按运营主体拆、按城市拆、按品牌拆、纯品牌拆
- **独立触发**：发布、发布到腾讯文档、推送到线上（阶段二）
- **独立触发**：生成通知、发消息给各主体、通知话术（阶段三）

拆分完成后，询问用户是否需要执行后续可选步骤：
1. 「是否发布到腾讯文档？」→ 是则进入阶段二
2. 「是否需要生成通知消息？」→ 是则进入阶段三

## 核心功能

### 拆分模式

| 模式 | 匹配条件 | 输出说明 |
|------|---------|---------|
| **运营主体** | 品牌+城市双条件 | 用 (品牌, 城市) 匹配运营主体，一个运营主体一个文件 |
| **城市** | 城市单条件 | 用城市匹配运营主体 |
| **品牌→运营主体** | 品牌单条件 | 用品牌匹配运营主体，一个品牌可能对应多个运营主体 |
| **纯品牌** | 品牌单条件 | 每个品牌独立输出，不映射运营主体 |

### 码表依赖

脚本通过 `lx_shujuku` 查询公司 dataReporting 的 `operator_brand` 表建立品牌+城市→运营主体的映射。运行前需确保 `config/fog_config.yaml` 的 `lx_shujuku.api` 段已配置 dataReporting 账号，并且 `lx_shujuku` 健康检查通过。

---

## 阶段一：拆分

### 步骤 0：检查配置（首次使用）

检查 `config/fog_config.yaml` 是否存在，并确认 `lx_zhutichaibiao` 段已配置。如需交互式补充，可运行：

```bash
python .workbuddy/skills/lx-zhutichaibiao/scripts/split_by_zhuti.py --config
```

配置项包括：项目根目录、默认对接人、工作目录。每个用户维护自己的 `config/fog_config.yaml`，不提交到版本管理。码表来源固定为 `lx_shujuku.operator_brand`。

配置完成后继续后续步骤。

### 步骤 1：检查待拆目录和码表

检查工作目录下的 `输入/` 中是否有 Excel 文件（`.xlsx` / `.xlsm`），并确认 `lx_shujuku` 可从公司库加载 `operator_brand` 码表。任一缺失则报告并终止。

### 步骤 2：询问用户选择

**必须询问以下参数，不能直接执行脚本：**

1. **拆分维度** — 选项：运营主体 / 城市 / 品牌→运营主体 / 纯品牌
2. **对接人范围** — 选项：默认（读取 config 中的"默认对接人"）/ 全部 / 指定对接人
3. **保留 sheet** — 如果用户在指令中已说明，直接使用；否则询问是否有不需要拆分的 sheet

### 步骤 3：执行拆分

运行脚本（在 workspace 根目录下执行，无需 cd 到绝对路径）：

```bash
python .workbuddy/skills/lx-zhutichaibiao/scripts/split_by_zhuti.py -m <mode> -p <person> [-k <keep_sheets>]
```

参数说明：
- `-m`: 1=运营主体, 2=城市, 3=品牌→运营主体, 4=纯品牌
- `-p`: `all` 或逗号分隔的对接人中文名（如 `雷维亮`）
- `-k`: 逗号分隔的保留 sheet 名称（可选）

**注意**：如果缺少 `--mode` 或 `--person`，脚本会进入交互模式。应尽可能提供这些参数以非交互方式执行。

### 步骤 4：展示结果

报告拆分结果：
- 输出 ZIP 包路径
- 分文件数量和总数据行数
- 未匹配数据数量和原因
- 未匹配报告路径

### 步骤 5：处理日志
拆分完成后自动在 `工作目录/处理日志/` 生成 Markdown 格式的处理日志，记录：
- 处理时间和拆分模式
- 每个源文件的输出 ZIP、原表存档路径
- 各运营主体/品牌的数据行数
- 未匹配行数
- 汇总统计

### 步骤 6：询问后续操作

拆分完成后，**必须逐个询问**用户是否需要执行后续可选步骤：

1. 「拆分完成。是否发布到腾讯文档在线表格？」→ 确认后进入阶段二
2. 「是否需要生成面向各运营主体的通知消息？」→ 确认后进入阶段三

用户可能只需要其中一项，或两项都不需要。

---

## 阶段二：发布到腾讯文档（可选，可独立触发）

触发词：发布、发布到腾讯文档、推送到线上。

此阶段调用 **`lx-txdocs`**，将本地拆分结果写入个人版腾讯文档在线表格。`scripts/publish_to_tdocs.py` 仅作为旧命令兼容入口，实际逻辑在 `lx-txdocs/scripts/publish_excel_folder.py`。

### 前置条件

- **Open API 凭证已配置**（`config/fog_config.yaml` 的 `lx_txdocs.tdocs.openapi` 段，或运行 `lx-txdocs/scripts/tdocs_api.py --setup` 写入根配置）
- **实体缓存已建立**（`lx-txdocs/assets/entity_cache.json`）— 首次使用由管理员或已授权 API 查询后写入，后续自动读取
- `config/fog_config.yaml` 中已配置 `lx_txdocs.tdocs.root_folder_id`

### 发布流程（一条命令）

#### 步骤 1：预览

```bash
python .workbuddy/skills/lx-txdocs/scripts/publish_excel_folder.py \
  <输出目录> --sheet-name <Sheet名称> --dry-run
```

展示每个运营主体的目标表格、数据行数，等待用户确认。

#### 步骤 2：执行发布

```bash
python .workbuddy/skills/lx-txdocs/scripts/publish_excel_folder.py \
  <输出目录> --sheet-name <Sheet名称>
```

**注意**：`--sheet-name` 为必填参数，示例中的 `0529司机明细` 仅为历史参考。实际使用时应根据拆分场景指定有意义的 Sheet 名称（如 `0601司机明细`、`0530城市数据` 等）。

脚本自动完成：读取本地 Excel → `add_sheet` → `write_range_auto` → 输出 sheet_id 列表。

### 错误处理

- **Open API 凭证未配置**：提示运行 `lx-txdocs/scripts/tdocs_api.py --setup`
- **实体缓存缺失**：提示运行 `publish_excel_folder.py --refresh-cache`，然后通过腾讯文档页面或已授权 API 查询补充
- **写入中途失败**：已完成的 sheet 不回滚，脚本输出各实体状态汇总

---
## 阶段三：生成通知消息（可选，可独立触发）

触发词：生成通知、发消息给各主体、通知话术。

不依赖阶段一或阶段二。可直接读取 `lx-txdocs/assets/entity_cache.json` 中的链接和各主体的数据行数来生成。

发布完成后，用户通常需要将数据链接发送给各运营主体/商家。此阶段将平台发给内部的通知话术，转换为面向每个运营主体的个性化消息。

### 触发方式

1. **跟在阶段一/二后面**：拆分或发布完成后，用户提供平台原话
2. **独立触发**：用户随时说「生成通知」并提供平台原话，无需先拆分

### 消息转换规则

对每个运营主体，以平台原话为模板，做以下转换：

1. **不遗漏平台信息**：平台原话中的所有关键信息（背景、截止时间、注意事项等）必须保留，不可删减
2. **转换视角**：「内部协调」口吻 → 「对商家/品牌通知」口吻
   - 「辛苦大家同步确认招商」→ 「需要贵方招商确认」
   - 「请按照同步的司机明细给商家去提报」→ 「请按照同步的司机去提报」
3. **附加文档链接**：从 `lx-txdocs/assets/entity_cache.json` 读取该主体的在线表格 URL
4. **以运营主体名称开头**：明确标识这是发给哪个主体的
5. **人数按需添加**：仅在平台原话提及数量或有助于说明范围时附加，不做固定模板

### 数据来源

- 各运营主体的文档链接和名称：`lx-txdocs/assets/entity_cache.json`

### 消息示例

**平台原话：**
```
⚠️重要：二次分配信息同步
5月先锋司机选拔二次分配活动已下发，辛苦大家同步确认招商；
商家可提报司机明细如下，为避免重复提报，请按照同步的司机明细给商家去提报。
注：新司机体系1期4城及2期2城涉及司机不参与2次分配
招商&提报时间节奏：今晚22点前截止招商，明晚16点前截止提报司机明细
```

**转换后（拼哒出行为例）：**
```
【 拼哒出行 】
⚠️重要：6月生效先锋司机二次分配信息同步

5月先锋司机选拔6月生效，二次分配活动已下发，需要招商。

可提报司机明细见文档：https://docs.qq.com/sheet/DRk1NT2hUbHZzT3R4

为避免重复提报，请按照同步的司机去提报。
注：新司机体系1期4城及2期2城涉及司机不参与2次分配
招商&提报时间节奏：今晚22点前截止招商，明晚16点前截止提报司机明细
```

---
## 目录结构

```
lx-zhutichaibiao/
├── SKILL.md                       # 此文件
├── README.md                      # 使用说明
├── scripts/
│   ├── split_by_zhuti.py          # 独立拆分脚本
│   ├── publish_to_tdocs.py        # 兼容入口，实际调用 lx-txdocs
│   ├── tdocs_api.py               # 兼容入口，实际调用 lxx_share.tdocs_api
│   └── requirements.txt           # Python 依赖
└── assets/                        # 历史目录；新配置不放这里
```

## 脚本依赖

- Python 3.7+
- openpyxl >= 3.0.0
- pyyaml >= 5.4.0
- requests >= 2.25.0（tdocs_api.py 依赖）

## 注意事项

- 列检测和对接人筛选函数（`find_column`/`detect_columns`/`filter_by_person`）从 `lxx_share.excel_utils` 导入，不再内联
- 码表映射从 `lx_shujuku.load_mabiao_mapping()` 加载，不再读取本地 Excel 码表
- 不使用 `echo` 管道跳过交互确认
- 不在未确认时移动原表或写入腾讯文档
- `config/fog_config.yaml` 包含用户个人路径和账号，**不应提交到 git**
- 个人版腾讯文档凭证、根文件夹和实体缓存归属 `lx-txdocs`
- 码表来源固定为公司库 `operator_brand`，确保每位用户已配置自己的 dataReporting 账号
- 多人共用项目时，确保工作目录（`输入/`、`输出/`、`原表存档/`）在同一位置，建议使用项目相对路径

## 跨 Skill 数据依赖

腾讯文档目标缓存归属 `lx-txdocs/assets/entity_cache.json`，本 Skill 只读取或通过 `lx-txdocs` 使用：

| 消费方 | 依赖字段 | 用途 |
|--------|----------|------|
| `lx-zhutichaibiao` | `file_id`, `url` | 发布拆分结果、生成通知 |
| `lx-dapanribao` | `folder_id` | 创建日报表格时指定父文件夹 |

**约束**：
- 修改 `entity_cache.json` 结构或路径时，需同步检查 `lx-txdocs` 和本文件
- `entity_cache.json` 使用 `schema_version: 1` + `entities` 格式；旧扁平格式仅过渡兼容
- `lx-dapanribao` 的表格 `file_id` 独立存储在 `lx-dapanribao/assets/dailyreport_cache.json`，不与 `entity_cache.json` 混用
