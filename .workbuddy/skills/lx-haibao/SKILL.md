---
name: lx-haibao
description: 企业版 WorkBuddy 专用司机活动海报生成。用于从城市活动 TXT 生成哈啰、安安用车、蔚蓝滴仕、江南出行等已配置品牌海报；按 check -> dry-run 确认 -> confirmed sample/full generation 三阶段执行，自动按 TXT 文件名识别品牌，通过图片 Provider Adapter 优先调用火山方舟 Seedream，失败后按规则回退 APIMart，并逐张验证二维码。不要使用 Codex image_gen。
---

# lx-haibao 通用海报生成

## 使用场景

当同事要根据城市活动 TXT 生成司机活动海报时，使用本 skill。用户只需要上传 TXT 文件，或提供 TXT 所在目录。

本 skill 是 WorkBuddy 独立包，不依赖原 Codex 项目的 `image_gen`。正式生图通过图片 Provider Adapter 完成，默认优先使用火山方舟 Seedream，连接超时、网络错误、5xx、429 等供应商可用性问题再回退 APIMart。

## 必要环境

管理员或同事需要在项目根配置中填写图片生成配置：

```text
config/fog_config.yaml
```

在 `lx_haibao.image_api` 中填写：

- `provider_primary`：默认 `volcengine_seedream`。
- `provider_fallback`：默认 `apimart`。
- `volcengine_seedream.api_key`：火山方舟 API Key。
- `volcengine_seedream.base_url`：默认 `https://ark.cn-beijing.volces.com/api/v3`。
- `volcengine_seedream.model`：默认 `doubao-seedream-5-0-260128`。
- `volcengine_seedream.size`：默认 `1600x2848`，用于 2K 级 9:16 竖版海报。
- `apimart.api_key`：APIMart API Key，作为 fallback。
- `apimart.base_url`：默认 `https://api.apimart.ai/v1`。
- `apimart.model`：默认 `gpt-image-2`。

不要在 `.workbuddy/skills/lx-haibao/assets/config.yaml` 写新配置；运行时统一读取 `config/fog_config.yaml`。

也兼容旧的环境变量方式：

- `IMAGE_PROVIDER_PRIMARY`
- `IMAGE_PROVIDER_FALLBACK`
- `ARK_API_KEY`
- `ARK_BASE_URL`
- `ARK_IMAGE_MODEL`
- `ARK_IMAGE_SIZE`
- `ARK_RESPONSE_FORMAT`
- `ARK_OUTPUT_FORMAT`
- `ARK_WATERMARK`
- `APIMART_API_KEY`
- `APIMART_BASE_URL`
- `APIMART_IMAGE_MODEL`
- `OPENAI_API_KEY`
- `POSTER_IMAGE_API_BASE_URL`
- `POSTER_IMAGE_MODEL`
- `POSTER_OUTPUT_DIR`

Python 依赖见 `requirements.txt`：`requests`、`Pillow`、`zxing-cpp`、`PyYAML`。

不要把依赖安装到全局 Python。首次使用先运行运行时检查脚本，它会创建或复用本 skill 内的 `.venv`，并把依赖安装到 `.venv`：

```bash
python scripts/check_runtime.py --install
```

Windows 同事也使用同一个脚本。第一次运行时可以用系统已有的 `python` 启动该脚本，但依赖只会安装到 `.workbuddy/skills/lx-haibao/.venv/`，后续应使用脚本输出的 `.venv` Python 命令运行 `run_poster_batch.py`。

先运行健康检查；检查失败时不要生成海报：

```bash
python scripts/check_runtime.py
```

`--check` 只验证依赖、模板示例图、品牌 logo、品牌二维码和源二维码解码，不调用图片 API。

如需检查图片 provider 配置和域名连通性，手动运行：

```bash
<.venv Python> scripts/run_poster_batch.py --check-providers
```

`--check-providers` 只检查配置和 `base_url` 连通性，不调用图片生成接口，不产生生图费用。正式生图时，400、401、403 等参数或鉴权错误不会自动 fallback；连接超时、网络错误、5xx、429、供应商不可用才会尝试下一个 provider。

## 用户流程

1. 用户上传或指定活动 TXT。
2. 运行 `--check`，确认运行环境和素材可用。
3. 运行 dry-run，确认 TXT 文件能被路由到品牌，并展示确认材料：

```bash
<.venv Python> scripts/run_poster_batch.py --dry-run --dir <活动TXT目录>
<.venv Python> scripts/run_poster_batch.py --dry-run --file <单个TXT路径>
```

dry-run 会读取真实 TXT，输出品牌、城市、模板、样图文件、成品命名、模块关键词命中和 TXT 预览。不要编造 TXT 中没有的城市、日期、金额、奖励或规则。

4. 用户确认 dry-run 内容后，先生成每个品牌的样图，必须追加 `--confirmed`：

```bash
<.venv Python> scripts/run_poster_batch.py --sample-only --confirmed --dir <活动TXT目录>
<.venv Python> scripts/run_poster_batch.py --sample-only --confirmed --file <单个TXT路径>
```

5. 用户确认样图风格后，生成批量成品，也必须追加 `--confirmed`：

```bash
<.venv Python> scripts/run_poster_batch.py --confirmed --dir <活动TXT目录>
<.venv Python> scripts/run_poster_batch.py --confirmed --file <单个TXT路径>
```

多品牌并行生成可使用 `--workers N`（默认 1，顺序执行）：

```bash
<.venv Python> scripts/run_poster_batch.py --confirmed --workers 3 --dir <活动TXT目录>
```

6. 最终回复必须给用户展示脚本输出的汇总表。

未传 `--confirmed` 时，样图和批量生成必须拒绝执行。缺少图片生成 API Key、缺少 Python 依赖、二维码验证失败或 TXT 文件不存在时，停止并报告真实错误。

## 品牌和素材

品牌按 TXT 文件名识别：

- 文件名包含 `哈啰轻快` 或 `哈啰`：品牌为 `哈啰`。
- 文件名包含 `安安用车` 或 `安安`：品牌为 `安安用车`。
- 文件名包含 `蔚蓝滴仕` 或 `蔚蓝`：品牌为 `蔚蓝滴仕`。
- 文件名包含 `江南出行` 或 `江南`：品牌为 `江南出行`。

品牌 Logo、二维码和模板图都在本 skill 包内。不要要求普通用户上传 Logo 或二维码，除非管理员要维护品牌配置。

## 内容确认规则

确认清单必须包含：

| 项目 | 内容 |
|---|---|
| 品牌 | 从文件名路由结果读取 |
| 城市 | 优先从 `--city` 参数读取，其次从 TXT 内容读取，最后从 TXT 文件名兜底 |
| 活动日期 | 只使用 TXT 中出现的日期 |
| 展示模块 | 用户本次提供的 TXT 中，所有活动模块默认都需要体现在海报，包括免佣、飞涨、卡券、全量活动、新人权益、成长奖、司邀司等模块 |
| 不展示内容 | 内部补贴属性、历史/过期/已结束/仅供参考/明确标记不展示的内容 |

规则：

- 活动内容只能来自本次 TXT 和用户确认。
- TXT 没有的模块不展示，不补“暂无”。
- 不展示 `共补`、`共补免佣`、`平台共补`、`是否共补`。
- `全量活动` 是正常展示模块，除非用户明确要求不展示。
- 定向活动、完单奖等活动模块默认展示，除非用户明确要求不展示，或 TXT 标记为历史/过期/已结束/仅供参考。
- 新人免佣奖只展示免佣天数，不展示适用订单。
- 新人成长奖才展示首单奖励、X天完成X单奖励等任务规则。
- 卡券按日期展示，每个日期内区分全天卡和时段卡。

## 生图和二维码规则

生图脚本会把三类参考图传给当前图片 provider：

1. 模板示例图：只作为版式参考。
2. 品牌 Logo：必须真实使用，不重绘。
3. 品牌二维码：必须原样放入海报。

每张样图和最终图都会调用包内二维码验证逻辑：

- 源二维码必须可解码。
- 海报二维码必须可解码。
- 海报二维码内容必须与品牌源二维码完全一致。
- 验证失败时废弃该图，并最多重试 2 次。
- 重试后仍失败，停止该品牌并报告失败原因。

## 输出

默认输出：

- 图片：`output/posters/`
- 元数据：`output/meta/`
- 临时图：`output/tmp/`
- 运行日志：`output/logs/YYYYMMDD.log`

这些目录是运行产物，不应打进分享包；脚本会在正式生成时自动创建。

最终汇总表字段固定为：

| 品牌 | TXT 文件 | 模板 | 输出图路径 | 二维码验证 | 状态 | 失败原因 |
|---|---|---|---|---|---|---|

unsupported 和 ambiguous 文件也要列入汇总，并说明原因。
