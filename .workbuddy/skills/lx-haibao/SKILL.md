---
name: lx-haibao
description: 企业版 WorkBuddy 专用司机活动海报生成。用于从城市活动 TXT 生成已配置品牌的司机活动海报；按 check、dry-run、confirmed sample/full generation 执行；自动按 TXT 文件名识别品牌；图片 Provider 优先 KIE，供应商可用性问题才回退 AIHubMix、APIMart；默认 hybrid 模式把模板图和真实 Logo 传给模型生成海报主体，再由脚本贴入真实二维码并逐张验证。
---

# lx-haibao

从城市活动 TXT 生成端外司机活动海报。只使用真实 TXT、品牌配置、模板图、Logo 和二维码素材；不要编造城市、日期、金额、奖励、文件路径或验证结果。

## 快速流程

先进入 skill 目录：

```bash
cd .workbuddy/skills/lx-haibao
```

首次或依赖异常时安装运行环境：

```bash
./check_runtime.sh --install
```

每次生成前先检查：

```bash
./check_runtime.sh
./haibao.sh --check
./haibao.sh --check-brand-locks
```

读取真实 TXT 做 dry-run：

```bash
./haibao.sh --dry-run --file <单个TXT路径>
./haibao.sh --dry-run --dir <活动TXT目录>
```

用户确认 dry-run 内容后，才允许生成：

```bash
./haibao.sh --sample-only --confirmed --file <单个TXT路径>
./haibao.sh --confirmed --file <单个TXT路径>
```

Windows 使用同名 `.cmd` 入口：`check_runtime.cmd`、`haibao.cmd`。

## 必守规则

- 未传 `--confirmed` 时，不生成样图或成品。
- 普通用户不要使用 `--template` 覆盖模板；管理员临时测试模板时必须同时追加 `--admin-template-override`。
- 默认资产模式为 `hybrid`：模型必须按“模板图 -> 真实 Logo”的参考图顺序生成海报主体，二维码由脚本贴入真实素材并验真。
- 二维码验证失败时废弃该图，在同一 provider 上按二维码原样使用要求重试；只有连接超时、网络错误、5xx、429 等供应商可用性问题才 fallback。
- `--asset-mode integrated` 仅用于内部对比，让模型同时参考模板、Logo、二维码；`--asset-mode overlay` 是旧版脚本贴 Logo/二维码兜底，不作为默认正式链路。
- TXT 是活动内容真源；TXT 没有的模块不展示，不写“暂无”。
- 最终回复必须展示脚本输出的汇总表，以及二维码验证结果。

## 资源结构

- `scripts/`：确定性运行脚本。优先调用入口脚本，不要重写批处理逻辑。
- `brands/`：品牌路由、展示名、模板绑定和素材配置。
- `brand-assets/`：保持现有结构，存放每个品牌的 `logo.png` 和 `qr.png`。
- `assets/templates/`：当前品牌中性模板图和 `templates.yaml` 模板索引。
- `assets/runtime/requirements.txt`：本 skill 的 Python 依赖清单。
- `assets/templates/archive/`：历史参考图或未纳入当前模板池的图片。
- `references/runtime.md`：运行环境、provider、内容确认、二维码、输出规则。
- `references/template-management.md`：模板命名、品牌绑定、待接入品牌和维护步骤。

维护环境、provider 或生成流程时，先读 `references/runtime.md`。维护模板、品牌配置或新增品牌时，先读 `references/template-management.md`。
