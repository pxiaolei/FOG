# 按运营主体/城市/品牌拆表工具 (lx-zhutichaibiao)

将 Excel 表格按运营主体、城市或品牌维度拆分，保留原表格式。

## 功能

- **四种拆分模式**：运营主体（品牌+城市双条件）、城市、品牌→运营主体、纯品牌
- **样式保留**：字体、边框、填充、对齐、数字格式、列宽、合并单元格
- **保留 sheet**：指定不拆分的 sheet 完整复制到每个输出文件
- **未匹配报告**：自动输出无法匹配的数据行及原因
- **命令行和交互模式**：支持两种使用方式
- **多人协作**：每个用户独立配置，配置不入 git

## 快速开始

### 1. 安装依赖

```bash
pip install -r scripts/requirements.txt
```

### 2. 首次配置

```bash
python scripts/split_by_zhuti.py --config
```

交互式输入：
- 项目根目录（回车使用当前目录）
- 默认对接人
- 工作目录名称

配置保存在项目根目录 `config/fog_config.yaml` 的 `lx_zhutichaibiao` 段，真实配置包含个人路径信息，**请勿提交到 git**。

### 3. 准备工作目录

```
<工作目录>/
├── 输入/       # 放入待拆分的 Excel 文件
├── 输出/       # 拆分结果 ZIP 输出
└── 原表存档/     # 处理后原表自动移入
```

### 4. 配置公司库码表

拆表码表不再使用本地 Excel 文件，固定从 `lx_shujuku` 查询公司 dataReporting 的 `operator_brand` 表。请先确认：

- `config/fog_config.yaml` 的 `lx_shujuku.api` 段已填写 dataReporting 账号
- `python .workbuddy/skills/lx_shujuku/scripts/db_tools.py health` 可以通过
- `python .workbuddy/skills/lx_shujuku/scripts/db_tools.py operator-brands --limit 5` 可以返回码表数据

### 5. 运行拆分

**交互模式**：
```bash
python scripts/split_by_zhuti.py
```

会依次询问：拆分维度 → 对接人范围 → 保留 sheet

**命令行模式**：
```bash
# 按运营主体拆，只拆雷维亮的
python scripts/split_by_zhuti.py -m 1 -p 雷维亮

# 按品牌拆，全部对接人
python scripts/split_by_zhuti.py -m 3 -p all

# 指定保留 sheet
python scripts/split_by_zhuti.py -m 1 -p 雷维亮 -k "沉默策略活动,策略汇总"
```

## 拆分模式说明

| 模式 | -m | 匹配条件 | 输出 |
|------|----|---------|------|
| 运营主体 | 1 | 品牌+城市双条件 | 运营主体文件 |
| 城市 | 2 | 城市单条件 | 运营主体文件 |
| 品牌→运营主体 | 3 | 品牌单条件 | 运营主体文件 |
| 纯品牌 | 4 | 品牌单条件 | 品牌文件（不映射运营主体） |

## 发布到腾讯文档

拆表完成后，共享给同事的线上协作流程走 `lx-nongfu` / `lx-txsaasdocs` 写腾讯文档企业版。个人版腾讯文档 `lx-txdocs` 只作为本机私有兼容能力，不进入 GitHub 分享模板。

## 团队共享注意事项

- `config/fog_config.yaml` 包含用户个人路径和账号，已在 `.gitignore` 中忽略；每个同事维护自己的根配置
- 码表来源固定为公司库 `operator_brand`，无需复制本地 Excel 码表
- 工作目录也建议使用相对路径，确保团队路径一致
- 如果公司库码表更新，所有同事下次运行拆表时自动使用最新数据
