---
name: lx-nongfu
description: 农夫/运营主体协作文档编排 Skill。用于把线下 Excel 或飞书普通表格大文档按运营主体拆分到各主体的日常信息表，新建填写 sheet，生成运营主体通知，并在主体填写完成后按品牌+城市回填大文档。适用于大文档拆分、农夫协作、运营主体填表、日常信息收集、主体回填、品牌城市回写等场景。
agent_created: true
location: project
---

# lx-nongfu — 农夫协作文档编排

## 定位

`lx-nongfu` 负责把“总部大文档 -> 运营主体填写 -> 回填总部大文档”串成一个受控流程。

它是编排 Skill，不直接重写底层能力：

| 阶段 | 优先调用 |
|---|---|
| 码表与品牌城市归属 | `lx_shujuku.operator_brand` |
| 本地 Excel 拆分 | `lx-zhutichaibiao` |
| 飞书普通表格读写、新建 sheet | `lx-feishudocs` |
| 通知内容 | `lx-tongzhi` |
| 本地/在线表格追加同步 | `lx-biaogetongbu` |
| 在线表格按 key 回填 | `lx-biaogetongbu --online --online-backend feishu --mode update-by-key` |
| 固定台账场景（背审申诉、静默乘客） | `lx-biaogetongbu/scripts/operator_workbook_sync.py` |

## 配置

共享给同事时，个人化信息必须放在 `config/fog_config.yaml` 的 `lx_nongfu` 段，不写进 Skill 文件。

关键配置项：

| 配置项 | 用途 |
|---|---|
| `workspace_dir` | 农夫协作处理目录，默认 `workspace/12农夫协作` |
| `default_contact_persons` | 默认对接人列表；分享模板保持空，由同事自己填 |
| `large_doc.required_key_columns` | 大文档定位键，默认必须是品牌+城市 |
| `large_doc.brand_fields` / `city_fields` | 表头候选名 |
| `large_doc.writeback_update_columns` | 允许回填的大文档列；空值时必须向用户确认 |
| `operator_doc.contact_person_root_folders` | 对接人到其飞书运营主体根文件夹的映射，例如 `雷维亮: https://.../drive/folder/...` |
| `operator_doc.operator_root_folder_url` / `operator_root_folder_token` | 单人使用时的默认运营主体根文件夹；有多人时优先用 `contact_person_root_folders` |
| `operator_doc.operator_folder_name_template` | 运营主体文件夹名模板，默认 `{operator}-运营主体` |
| `operator_doc.target_table_name_template` | 主体目标表名，默认 `{operator}-日常信息` |
| `operator_doc.sheet_name_template` | 新建 sheet 命名，默认 `{date}{topic}` |
| `notification.default_audience` / `default_format` | 默认通知对象和格式 |

飞书账号和 token 不放在本 Skill 配置中，由 WorkBuddy 飞书连接器维护。本项目只使用飞书普通电子表格，不使用 Base/智能表格。

大文档链接通常每次都会变化，不写进共享配置；运行时用 `--source-url` 传入。每位同事相对稳定的是“自己名下运营主体根文件夹”，应写在本地 `config/fog_config.yaml` 的 `lx_nongfu.operator_doc.contact_person_root_folders` 中，模板文件保持空。

## 触发时先确认

除非用户已经明确给出，执行前必须确认：

1. 大文档来源：本地 Excel 路径，或飞书普通表格 URL。
2. 对接人范围：默认配置、全部，或指定中文全名。
3. 新建 sheet 名：例如 `0610日常信息收集`。
4. 运营主体人员要填写哪些列。
5. 回填大文档时允许更新哪些列。
6. 通知对象和格式：默认 `shangjia` + `weixin`。

不要编造品牌、城市、运营主体、链接、截止时间、填写列或回填列。用户未给完整路径时，先动态枚举真实文件。

## 标准流程

### 1. 读取大文档

- 本地 Excel：先枚举文件，再读取表头和 sheet。
- 飞书普通表格：先从 URL 提取 spreadsheet token，再读取 workbook / sheet / range。
- 普通 Word/PDF/飞书文档正文：先说明需要转成结构化表格或明确表格区域，再继续。

读取后必须确认大文档存在品牌列和城市列。候选字段来自 `lx_nongfu.large_doc.brand_fields` / `city_fields`。

### 2. 按运营主体拆分

用 `lx_shujuku.operator_brand` 建立 `(品牌, 城市) -> 运营主体` 映射。

拆分预览必须输出：

- 大文档有效行数。
- 可匹配运营主体数。
- 每个运营主体的品牌城市数量和数据行数。
- 未匹配品牌城市清单。

存在未匹配行时，不直接写入飞书表格，先让用户确认处理方式。

### 3. 写入主体日常信息表

目标结构：

```text
{运营主体}-运营主体/
  {运营主体}-日常信息
    {sheet_name}
```

写入前必须 dry-run：

- 确认目标表格来源于 `lx-feishudocs` 飞书普通表格缓存或飞书查询结果。
- 确认将新增的 sheet 名。
- 确认每个主体将写入的行列规模。
- 不覆盖同名 sheet；如同名已存在，先给出重命名或停止选项。

用户确认后再新建 sheet 并写入。

### 4. 生成通知

调用 `lx-tongzhi` 的 `shangjia` 视角生成通知，默认格式为 `weixin`。

通知必须包含：

- 运营主体名称。
- 对应飞书表格链接。
- 需要填写的 sheet 名和字段。
- 截止时间；如果用户未提供，标注为“未提供”，不要编造。
- 回填前请勿改动品牌和城市定位列。

`lx-tongzhi` 第一版只生成内容和校验报告，不自动发送。

### 脚本入口

已提供可复用命令：

```bash
python .workbuddy/skills/lx-nongfu/scripts/run_split_publish.py \
  --source-url "https://xxx.feishu.cn/sheets/..." \
  --contact-person "雷维亮"
```

如果大文档已经由 `lx-zhutichaibiao` 拆好，不需要再从大表链接拆分，直接发布已拆分目录或 zip：

```bash
python3 .workbuddy/skills/lx-nongfu/scripts/run_publish_split_outputs.py \
  "workspace/01主体拆表/输出/20260612_1437_端午策略时段_0618-0621.zip" \
  "workspace/01主体拆表/输出/20260612_1438_26年端午服务费明细.zip" \
  --contact-person "雷维亮"
```

默认 dry-run，只读取已拆分文件、查找各 `{运营主体}-日常信息` 飞书普通表格、检查同名 sheet 冲突；真正写入飞书必须显式加：

```bash
  --confirmed
```

默认是 dry-run，只预览匹配结果、目标表和各运营主体通知内容；真正写入飞书必须显式加：

```bash
  --confirmed
```

关键参数：

| 参数 | 说明 |
|---|---|
| `--source-sheet` | 大文档 sheet 名；不填且只有一个 sheet 时自动使用 |
| `--operator-root-folder-url` / `--operator-root-folder-token` | 临时覆盖配置中的运营主体根文件夹 |
| `--target-sheet-name` | 目标新建 sheet 名；不填时等于大文档 sheet 名 |
| `--header-row` | 品牌/城市表头行；不填时在前 10 行自动识别 |
| `--if-sheet-exists fail\|skip` | 目标表已有同名 sheet 时停止或跳过，默认停止 |
| `--preserve-header-format / --no-preserve-header-format` | 是否复制表头区域样式、合并单元格、行高和列宽，默认复制 |
| `--refresh-existing-header-format` | 配合 `--confirmed --if-sheet-exists skip` 使用；同名 sheet 已存在时只补刷表头格式，不重写数据 |
| `--notification-template` | 面向各运营主体的通知模板；可用 `{operator}`、`{link}`、`{sheet_name}` 等占位 |

脚本输出：

- JSON 执行摘要。
- `workspace/12农夫协作/输出/` 下的摘要 JSON。
- 每个运营主体一段可直接转发的通知 Markdown。

通知正文变化时，不建议写死在配置里。默认由本脚本根据链接生成基础通知；复杂文案应继续走 `lx-tongzhi` 的 `shangjia` + `weixin` 视角生成，再通过 `--notification-template` 或 `--notification-template-file` 传给本脚本。

### 5. 回填大文档

回填必须按品牌+城市定位，不允许整表覆盖。

回填预览必须输出：

- 来源：每个运营主体的填写 sheet。
- 定位键：品牌+城市。
- 允许更新列。
- 将更新的单元格列表或行列坐标摘要。
- 未匹配主体填写行。
- 大文档中重复品牌城市键。
- 主体 sheet 中重复品牌城市键。

只有用户确认后才写回大文档。写回后必须再次读取对应范围验证。

已提供独立回填命令：

```bash
python .workbuddy/skills/lx-nongfu/scripts/run_writeback.py \
  --master-url "https://xxx.feishu.cn/sheets/..." \
  --contact-person "雷维亮" \
  --sheet-name "0610飞涨卡资源位&触达配置" \
  --operator "方舟行武汉" \
  --update-columns "首页侧边栏bannerID,首页开屏ID,短信ID,PushID"
```

默认 dry-run；真实写回必须加 `--confirmed`。批量回填可用 `--all-operators`。

回填字段每次活动可能变化，因此优先通过 `--update-columns` 指定。`config/fog_config.yaml` 中的 `large_doc.writeback_update_columns` 只作为可选默认值；如果命令行没传且配置为空，脚本必须停止并要求指定字段，不猜测字段。

默认不会用主体表空值覆盖大文档已有值；确实需要清空时才使用 `--allow-empty-overwrite`。

### 6. 增量同步资源位 ID

当运营主体逐步填写资源位 ID（如首页 banner/横栏/开屏/侧边栏 banner ID），需要持续同步到大文档时使用：

```bash
python .workbuddy/skills/lx-nongfu/scripts/sync_ids_incremental.py \
  --master-url "https://xxx.feishu.cn/sheets/..." \
  --topic-sheet-name "0624飞涨卡资源位&触达配置" \
  --contact-person "雷维亮"
```

**工作原理：**

1. 首次运行时创建快照（`workspace/12农夫协作/缓存/id_sync_{对接人}_{topic}.json`），记录每个运营主体 sheet 中每个品牌城市行当前的 ID 值。
2. 后续运行时，重新读取运营主体 sheet 的最新状态，与快照比对：
   - **从空变成有值** → 检出为「新增 ID」，预览后确认写入大文档
   - **已有值不变** → 跳过
   - **尚未填写** → 报告但不同步
3. 写入大文档前会校验目标单元格是否已有值（避免覆盖手动填入的 ID）。
4. 写入成功后更新快照。

默认 dry-run（预览）。真正写入必须加 `--confirmed`。

**列布局自动识别：** 脚本会检测运营主体 sheet 的结构：
- 布局 A：D=对接同学, E-H=ID（适用于 LX、哈啰文山、小象快跑、逸乘金华）
- 布局 B：D-G=ID（其他运营主体）

**关键参数：**

| 参数 | 说明 |
|---|---|
| `--master-url` | 飞书大文档 URL（必传） |
| `--master-sheet` | 大文档 sheet 名；URL 含 `?sheet=xxx` 时自动使用 |
| `--topic-sheet-name` | 运营主体日常信息中对应 topic 的 sheet 名（必传） |
| `--contact-person` | 对接人中文名（必传） |
| `--confirmed` | 实际写入；不加时只预览 |

**输出：**
- 终端文本预览报告（stderr 为进度日志，stdout 为 Markdown 报告）
- JSON 摘要文件（`workspace/12农夫协作/输出/`）

## 当前边界

- `lx-nongfu` 只负责活动型“大文档拆分到日常信息表、生成通知、活动字段回填”的编排。
- 背审申诉、静默乘客这类固定台账同步放在 `lx-biaogetongbu`，用 `operator_workbook_sync.py --scenario beishen_shensu|jingmo_chengke` 执行。
- 本地 Excel 和在线飞书普通表格的追加/按 key 更新由 `lx-biaogetongbu` 处理；写入开始后不自动换后端，失败必须报告真实原因。
- 自动发短信、push、微信消息不属于本 Skill 第一版范围。
