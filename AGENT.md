# FOG 项目协作说明

> 目标受众：AI Agent（WorkBuddy / Codex）。本文档是项目的全局上下文入口，Agent 接手任务前应先通读。

---

## 1. 项目概述

FOG 是 LXX 子模块项目，核心业务流程：**数据导入 → 拆表分发 → 报表生成 → 腾讯文档发布**。

关键业务实体：
- **运营主体**（operator_entity）：如"拼哒出行""江豚出行"等
- **品牌**（brand_name）：如"拼哒出行""博约出行""逸乘出行"
- **城市**（city_name）：运营城市名称
- **对接人**（contact_person）：每个品牌-城市组合的负责人，**统一使用中文全名**（如"雷维亮"，不用缩写"LWL"）

码表映射（运营主体↔品牌↔城市↔对接人）唯一来源：公司库 `dataReporting.operator_brand`，通过 `lx_shujuku` 查询。

项目路径：`/Users/bobobobo/Documents/Projects/lxx/p-fog`（本地），模板仓库不包含个人路径。

---

## 2. Skills 清单

| Skill | 职责 | 类型 | 核心依赖 |
|-------|------|------|---------|
| `lx_shujuku` | 公司库只读访问，码表映射，表结构管理 | 基础设施 | 无（纯标准库） |
| `lxx_share` | 共享 Python 库（DB连接/指标计算/Excel工具/腾讯文档API/缓存） | 基础设施 | `lx_shujuku`（码表） |
| `lx-init` | 旧初始化兼容入口；新入口是 `tools/fog.py` | 运维 | 无 |
| `lx-zhutichaibiao` | 按运营主体/城市/品牌拆表，生成各主体 Excel | 数据处理 | `lxx_share`, `lx_shujuku` |
| `lx-txwendang` | 批量发布 Excel 到腾讯文档（Open API V3） | 发布 | `lxx_share`, `lx_shujuku` |
| `lx-biaogetongbu` | A 表到 B 表的登记/汇总同步，覆盖静默乘客、背审、拆表结果同步 | 数据处理 | `openpyxl` |
| `lx-hhdataimport` | hhdata 汇总数据导入（来源 A） | 数据导入 | `lxx_share` |
| `lx-lxdataimport` | lxdata 明细数据导入（来源 B），含邮箱拉取 | 数据导入 | `lxx_share` |
| `lx-dapanribao` | 运营日报生成（17 指标 + 异动检测），生成企业版发布计划 | 报表 | `lxx_share`, `lx_shujuku`, 全局 `tencent-saas-docs` |
| `lx-hhgongbu` | 共补策略处理（拆分→入库→对比→免佣卡更新） | 策略 | `lxx_share`, `lx_shujuku` |

所有 Skill 路径：`.workbuddy/skills/<skill-name>/`，入口文件为各 `SKILL.md`。

---

## 3. 核心工作流

### 3.1 数据处理全链路

```
数据来源 A (hhdata)              数据来源 B (lxdata)
      │                                │
      ▼                                ▼
lx-hhdataimport                  lx-lxdataimport
  (导入 hhdata.fact_daily_metrics)  (导入 lxdata.* 明细表)
      │                                │
      └──────────┬─────────────────────┘
                 ▼
          lx-zhutichaibiao
            (按运营主体拆表)
                 │
                 ▼
          lx-txwendang
         (发布到腾讯文档)
                 │
                 ▼
	          lx-dapanribao
	        (生成日报 / 企业版发布计划)
```

### 3.2 拆表→发布（最常用）

```bash
# 1. 拆表：按运营主体拆分，仅处理对接人雷维亮的数据
python .workbuddy/skills/lx-zhutichaibiao/scripts/split_by_zhuti.py -m 1 -p 雷维亮

# 2. 发布：批量发布拆分结果到腾讯文档
python .workbuddy/skills/lx-txwendang/scripts/publish_excel_folder.py \
  --input-dir workspace/01主体拆表/输出/ --all-sheets
```

### 3.3 日报生成

```bash
python .workbuddy/skills/lx-dapanribao/scripts/main.py --person 雷维亮
python .workbuddy/skills/lx-dapanribao/scripts/main.py --person 雷维亮 --dry-run  # 预览
```

日报实际写入腾讯文档企业版时，使用全局 `tencent-saas-docs` 读取 `dapanribao_publish_plan_{MMDD}.json` 后执行。目标根文件夹和表格命名规则写在 `config/fog_config.yaml` 的 `lx_dapanribao` 段。

### 3.4 共补策略处理

```bash
python .workbuddy/skills/lx-hhgongbu/scripts/run_allgongbu.py --person 雷维亮
```

---

## 4. 目录结构

```
FOG/
├── config/                     # 配置：fog_config.yaml（统一真实配置）
│   └── 码表/                   # [废弃] 旧本地码表，已迁移到 lx_shujuku
├── workspace/                  # 业务数据（不入 git）
│   ├── 01主体拆表/             # 输入/ → 输出/ → 原表存档/ + 处理日志/
│   ├── 02数据导入/             # 待处理/ → 已处理/ + 处理日志/
│   ├── 03数据报表/             # 日报/ 周报/ 月报/ 其他/
│   ├── 04数据分析/             # 探索分析
│   ├── 05策略活动/             # 策略活动表/ 竞品策略/ 导入后台表格/
│   ├── 07共补活动/             # 待处理/ → 已处理/ + 处理日志/
│   ├── 10表格同步/             # 待处理/ → 输出/ + 处理日志/
│   └── 11价格监控/             # 价格跟踪
├── .workbuddy/skills/          # 所有 Skill（见 §2）
├── tools/                      # 安装/检查脚本（.ps1 + .py）
├── docs/                       # 项目文档
└── zip/                        # 模板打包分发
```

Pipeline 场景（拆表/导入/共补）统一约定：`待处理 → 已处理 + 处理日志`，原表进存档永不被覆盖。

---

## 5. 编码规范

### 5.1 Python 运行时
- 版本：3.13+（managed runtime：`~/.workbuddy/binaries/python/versions/3.13.12/bin/python3`）
- 依赖隔离：所有 `pip install` 在 venv 内执行，禁止全局安装
- Skill 脚本路径初始化：使用内联 `_find_skills_dir()` 函数，向上查找含 `lxx_share/` 的目录

### 5.2 代码风格
- Import 顺序：标准库 → 第三方库 → 项目内模块，各组之间空一行
- 类型注解：函数签名必须标注参数和返回类型
- 字符串：统一双引号
- 中文注释：允许且鼓励，业务逻辑用中文说明意图

### 5.3 命名约定
| 类别 | 规范 | 示例 |
|------|------|------|
| 目录 | 两位数字前缀 + 中文名 | `01主体拆表`, `03数据报表` |
| Python 文件 | snake_case | `data_loader.py`, `report_builder.py` |
| Python 类 | PascalCase | `DatabaseConnector` |
| 配置文件 | 小写 + 下划线 | `fog_config.yaml`, `entity_cache.json` |
| 处理日志 | `{YYYYMMDD}_{HHMMSS}_{skill名}_{描述}.md` | `20260605_120000_lx-zhutichaibiao_处理日志.md` |
| Skill 名 | 小写 + 连字符 | `lx-dapanribao`；底层模块用下划线 `lxx_share` |

### 5.4 新增/分享 Skill 的配置规则

- 准备给同事使用的 Skill 不得硬编码个人账号、真实 token、固定本机路径或个人默认对接人；必须从 `config/fog_config.yaml`、环境变量或运行参数读取。
- 新增配置项时同步更新 `config/fog_config.yaml.example`、`docs/模板更新与配置策略.md`、`tools/fog.py` 检查逻辑；不得新增面向同事的 per-Skill `assets/config.yaml` 配置入口。
- 进入模板分发的 Skill 必须加入 `config/template_manifest.yaml` 的 `managed_dirs`；真实配置、缓存、证据包和业务输出必须留在 `protected_paths`。
- 不分享给同事的内部 Skill 不写入 `config/fog_config.yaml.example`；本地个人配置统一放在 `config/personal_config.yaml`，并保持 gitignored。
- 有写入外部系统或会产生费用的 Skill 必须提供 `--dry-run` 或显式确认参数，默认先预览。

---

## 6. 腾讯文档发布机制

- 个人版/旧路径：拆表发布仍可使用 `lx-txwendang` / `lxx_share.tdocs_api`
- 企业版日报：`lx-dapanribao` 依赖全局 `tencent-saas-docs`
- 企业版日报根文件夹：`https://efe3f9566e.docs.qq.com/desktop/mydoc/folder/TlznihwNLTGuzisgAg`
- 企业版日报目标表格：各运营主体文件夹中的 `{运营主体}-大盘数据日报`
- 拆表发布目标结构：`根文件夹/ → {运营主体}-运营主体/ → {运营主体}-日常信息/`
- 企业版日报发布目标结构：`企业版根文件夹/ → {运营主体}-运营主体/ → {运营主体}-大盘数据日报`
- 缓存文件（含 file_id/folder_id）不入版本控制：
  - `lx-zhutichaibiao/assets/entity_cache.json` — 运营主体文件夹
  - `lx-dapanribao/assets/dailyreport_cache.json` — 日报表格
- 大表注意：`add_sheet` 的 `column_count` 使用实际数据列数，不用固定值 26，避免 API 格子数超限
- 链接输出格式：`https://docs.qq.com/doc/XXXXX?_fid=<file_id>`

---

## 7. 数据库协作（lx_shujuku）

### 7.1 数据源

公司库 `dataReporting`（HTTP API，非直连 MySQL），共 13 张业务表。

入口：
```bash
cd /path/to/p-fog
WB_PYTHON=~/.workbuddy/binaries/python/versions/3.13.12/bin/python3
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py
```

### 7.2 常用命令

```bash
# 健康检查
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py health

# 列出所有表 / 查看表结构
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py list-tables
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py describe honghu_order_data

# 查询码表
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py operator-brands --brand "拼哒出行"
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py mabiao

# 执行 SQL（只读）
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py query "SELECT ... LIMIT 100"

# 带证据包查询
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py query "SELECT ..." \
  --audit --question "业务问题" --metric metric_id

# 指标口径目录
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py metrics
```

### 7.3 关键表

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `operator_brand` | 品牌-城市-运营主体码表 | `operator_entity`, `brand_name`, `city_name`, `contact_person` |
| `honghu_order_data` | 品牌按日期完单数据 | `brand_name`, `date_day`, `city_name`, `completed_order_count` |
| `order_real_time_data` | 租户实时累计订单 | `tenant_name`, `datae_column_*`, `cal_*` |
| `driver_real_time_data` | 租户实时运力数据 | 同 order 结构 |
| `activity_data` | 活动数据 | `brand_name`, `activity_id` |
| `card_data` | 卡券数据 | `brand_name`, `product_name` |
| `time_split_data` | 分时明细 | `brand_name`, `date_day`, `hour_range` |

完单量汇总必须用 `SUM(completed_order_count)` 而非 `COUNT(*)`。查询前先用 `operator_brand` 确认品牌名是否存在于库中。

### 7.4 SQL 安全策略

- 只允许：`SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`
- 禁止：写操作、DDL、多条 SQL 拼接、注释 SQL
- 查询明细必须加 `LIMIT`，聚合查询也建议加合理上限
- 表名必须在 `assets/schema.json` 白名单中
- 真实配置统一在 `config/fog_config.yaml`（含个人账号）中，已 gitignored，禁止分享

### 7.5 数据字典维护

Schema 快照：`.workbuddy/skills/lx_shujuku/assets/schema.json`
可读版：`.workbuddy/skills/lx_shujuku/references/table_catalog.md`
指标口径：`.workbuddy/skills/lx_shujuku/references/metrics_catalog.json`

发现线上结构不一致时：
```bash
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py schema-diff    # 预览差异
"$WB_PYTHON" .workbuddy/skills/lx_shujuku/scripts/db_tools.py refresh-schema --yes  # 确认刷新（自动备份）
```

### 7.6 查询结果输出要求

最终回复必须包含：查询口径、使用表名、实际结果、失败真实原因、必要交叉验证。不得补造数据、不得输出凭证。

---

## 8. 数据安全

- API 凭证统一在 `config/fog_config.yaml`（gitignored），禁止硬编码
- 缓存文件（`entity_cache.json`, `dailyreport_cache.json`）含 file_id，不入版本控制
- 敏感字段（手机号、身份证号）输出时脱敏
- 对外文档不粘贴敏感明细，只引用必要汇总
- 数据库操作全程只读，证据包保存在 `assets/query_runs/`（不分享）

---

## 9. 常见问题速查

| 问题 | 答案 |
|------|------|
| 对接人用缩写还是全名？ | **中文全名**（如"雷维亮"），公司库 contact_person 字段存储全名 |
| `--person LWL` 为什么不生效？ | 数据库无缩写，已全量修正为中文名 |
| 码表从哪来？ | `lx_shujuku` → `operator_brand` 表，不读本地 Excel |
| 拆表大文件发布失败？ | 检查 `add_sheet` 的 `column_count`，用实际列数不用固定 26 |
| 腾讯文档链接怎么拼接？ | `https://docs.qq.com/doc/XXXXX?_fid=<file_id>` |
| 如何新增 Skill？ | 必须含 SKILL.md + scripts/ + assets/；公共能力抽到 lxx_share |
