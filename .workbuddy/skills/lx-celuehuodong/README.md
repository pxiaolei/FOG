# 策略活动表工具 (lx-celuehuodong)

`lx-celuehuodong` 负责策略活动表后处理：更新“共补活动”sheet、生成“免佣卡”sheet、更新城市日历，并按品牌生成后台导入文件。

它不负责共补原表拆分、入库和同比分析；这些属于上游内部流程，共享版只消费已入库的共补策略数据。

## 快速开始

```bash
# 预览，不写入
python3 .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --auto

# 确认执行 activity -> card -> calendar
python3 .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --auto --confirmed

# 生成后台导入文件
python3 .workbuddy/skills/lx-celuehuodong/scripts/run_celuehuodong.py --step export --date-range 0615-0617 --confirmed
```

## 目录

```text
lx-celuehuodong/
├── SKILL.md
├── README.md
├── assets/
│   ├── 免佣卡导入模版.xlsx
│   └── 飞涨卡导入模版.xlsx
└── scripts/
    ├── run_celuehuodong.py
    ├── config_loader.py
    ├── update_gongbu_activity.py
    ├── create_mianyongka.py
    ├── update_gongbu_calendar.py
    └── generate_mianyongka_import.py
```

## 配置

配置段为 `lx_celuehuodong`，共享默认值写在 `config/fog_config.yaml.example`，本机覆盖写在 `config/fog_config.yaml` 或 `config/personal_config.yaml`。

关键配置项：

- `strategy_workbook`：城市策略活动表 `.xlsm`
- `import_output_dir`：后台导入文件输出目录
- `gongbu_archive_dir`：共补原表存档目录，用于自动识别日期范围
- `target_cities`：写“共补活动”sheet 的城市范围
- `calendar_cities`：写城市日历的城市范围；为空时兼容旧配置，回退到 `target_cities`
- `cities` / `default`：免佣卡城市、品牌和卡券规则
