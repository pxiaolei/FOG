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
| 本地表格追加同步 | `lx-biaogetongbu` |
| 在线表格按 key 回填 | `lx-biaogetongbu --online --online-backend feishu --mode update-by-key` |

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
| `operator_doc.target_table_name_template` | 主体目标表名，默认 `{operator}-日常信息` |
| `operator_doc.sheet_name_template` | 新建 sheet 命名，默认 `{date}{topic}` |
| `notification.default_audience` / `default_format` | 默认通知对象和格式 |

飞书账号和 token 不放在本 Skill 配置中，由 WorkBuddy 飞书连接器维护。本项目只使用飞书普通电子表格，不使用 Base/智能表格。

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

## 当前边界

- 本地 Excel 的追加同步已有 `lx-biaogetongbu` 支持。
- 在线飞书普通表格 A->B 按 key 更新由 `lx-biaogetongbu --online-backend feishu` 处理；写入开始后不自动换后端，失败必须报告真实原因。
- 自动发短信、push、微信消息不属于本 Skill 第一版范围。
