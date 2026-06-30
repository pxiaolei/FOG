# 运行与生成规则

## 配置

运行时统一读取项目根配置：

```text
config/fog_config.yaml
```

`lx_haibao.image_api` 同事共享默认只使用 `kie`。不要把 AIHubMix、APIMart 或 Codex 内置 `builtin_image_gen` 写进共享配置；也不要把新 API Key 写进 `assets/config.yaml`。

常用配置键：

- `providers`
- `provider_primary`
- `provider_fallback`
- `kie.api_key`
- `kie.base_url`
- `kie.upload_base_url`
- `kie.text_model`
- `kie.image_model`
- `kie.aspect_ratio`
- `kie.upload_path`
- `kie.callback_url`

同事共享环境只需要配置 `KIE_API_KEY`。旧的 `POSTER_*` 变量仍可用于轮询间隔、超时等本地运行参数。

异步生图任务默认按慢任务处理：提交后等待 30 秒再查询，每 30 秒轮询一次，最多轮询 40 次，避免 KIE 后台仍在生成时本地过早判定超时。可通过 `POSTER_IMAGE_TASK_INITIAL_DELAY_SECONDS`、`POSTER_IMAGE_TASK_POLL_INTERVAL_SECONDS`、`POSTER_IMAGE_TASK_POLL_ATTEMPTS` 临时覆盖。

## 检查命令

在 `.workbuddy/skills/lx-haibao/` 下运行：

```bash
./check_runtime.sh
./haibao.sh --check
./haibao.sh --check-brand-locks
./haibao.sh --check-providers
```

`--check` 验证依赖、模板示例图、品牌 Logo、品牌二维码和源二维码解码，不调用图片 API。

`--check-brand-locks` 验证品牌模板绑定、真实 Logo/二维码素材、源二维码解码，以及 overlay 坐标是否存在。默认 `hybrid` 模式依赖 `qr_overlay` 贴真实二维码，但不依赖 `logo_overlay`；缺失按实际影响显示 warning 或 error。

`--check-providers` 只检查配置和 base URL 连通性，不调用图片生成接口。

最小真实 provider 生图检查必须显式确认，可能产生费用：

```bash
./haibao.sh --smoke-provider kie --confirmed
```

## 生成流程

1. 用户上传或指定活动 TXT。
2. 运行检查命令。
3. 运行 `--dry-run`，展示品牌、城市、模板、成品命名、模块命中和 TXT 预览。
4. 用户确认 dry-run 后，运行 `--sample-only --confirmed` 生成样图。
5. 用户确认样图后，运行 `--confirmed` 生成成品。
6. 多品牌可使用 `--workers N`，默认顺序执行。

同事 WorkBuddy 环境不依赖 Codex 内置 `image_gen`。如果维护者在个人环境中临时使用内置 `image_gen` 兜底，该能力只能留在个人真实配置或人工流程里，不进入共享配置。

## 内容规则

确认清单必须包含品牌、城市、活动日期、展示模块、不展示内容。

- 活动内容只能来自本次 TXT 和用户确认。
- 活动日期只使用 TXT 中出现的日期。
- 用户本次提供的 TXT 中，所有活动模块默认展示，包括免佣、飞涨、卡券、全量活动、新人权益、成长奖、司邀司。
- 活动模块数量不固定：TXT 有几个活动类型就展示几个；不要为了凑模板预设区块而新增空模块、合成模块或替换模块标题。
- 新增活动类型建议在 TXT 中用 `【活动标题】` 分段，脚本会把分段标题纳入模块数和长海报判断。
- 活动类型较少时，收紧中部活动区，不保留空白预设卡片；活动类型较多时，优先拉长海报和增加活动卡片，不靠压缩字号硬塞内容。
- 日期、星期、时间段、金额、奖励、单量和门槛必须逐字按 TXT 展示；TXT 中已给出星期时，不得自行推算、改写或顺延星期。
- 不展示内部补贴属性、历史/过期/已结束/仅供参考/明确标记不展示的内容。
- 不展示 `共补`、`共补免佣`、`平台共补`、`是否共补`。
- `全量活动` 是正常展示模块，除非用户明确要求不展示。
- 新人免佣奖只展示免佣天数，不展示适用订单。
- 新人成长奖才展示首单奖励、X 天完成 X 单奖励等任务规则。
- 卡券按日期展示，每个日期内区分全天卡和时段卡，时段卡按时间从早到晚。
- 默认 `--size-policy auto`：内容偏多时按模板 `content_sizing.long_size` 生成长海报，优先纵向拉长活动区，不靠压缩字号硬塞内容。需要固定画幅时使用 `--size-policy fixed --size 9:16`。

## Logo 与二维码

默认链路是 `--asset-mode hybrid`：生图脚本把模板示例图和品牌真实 Logo 传给当前图片 provider，由模型生成海报主体和自然品牌露出；二维码不交给模型生成，后续由脚本贴入真实二维码并验真。

- 默认参考图顺序固定为：模板图、品牌 Logo。
- Logo 从 `brand-assets/<brand>/logo.png` 读取，必须自然融入顶部品牌区。
- 二维码从 `brand-assets/<brand>/qr.png` 读取，按模板 `qr_overlay` 生成紧凑白边二维码卡片后贴入，必须保持正方形、清晰、完整、可扫码。多品牌模板优先使用 `anchor: bottom_right`，按最终海报右下角几何边距锚定二维码；贴码前会检查底部 footer 高度，若 footer 高度不足以容纳二维码卡片，会先向下补同色 footer，再贴入二维码，避免二维码压到上方活动卡片或超出 footer。贴码前会清理右下角二维码安全区，避免模型在该区域生成的 footer 图标、卖点文案或装饰被真实二维码卡片遮挡。对底部没有安全贴码区的模板，可配置 `append_footer_for_qr: true`，脚本会直接追加一段二维码 footer，避免覆盖原内容。
- 源二维码必须可解码。
- 海报二维码必须可解码。
- 海报二维码内容必须与品牌源二维码完全一致。
- 验证失败时废弃该图，在同一 provider 上重试，最多按 `--max-retries` 控制。
- `--asset-mode integrated` 会把模板、Logo、二维码三图都交给模型融合，适合内部对比，不作为同事默认链路。
- `--asset-mode overlay` 会让模型只看模板，再由脚本贴入 Logo 和二维码，仅用于临时兜底。

## 输出

默认运行产物在项目根的 `workspace/09端外海报图/` 下：

- 图片：`workspace/09端外海报图/产出图/`，保存最终通过二维码验证的海报 PNG。
- 元数据：`workspace/09端外海报图/元数据/`，保存每次生成的 JSON 记录，包括 TXT 路径、品牌、城市、模板、asset_mode、prompt、reference_images、provider 结果和二维码验证结果。
- 临时图：`workspace/09端外海报图/临时图/`，保存生成过程中的中间图片；成功后会移动到 `产出图/`，失败后通常会清理。
- 运行日志：`workspace/09端外海报图/处理日志/YYYYMMDD.log`，保存当天运行日志。

这些目录是运行产物，不应打进分享包。

用户给活动文本有两种方式：

- 直接把 TXT 内容发给 Codex，由 Codex 写入临时 TXT 后跑 `--dry-run --file`。
- 把 `.txt` 文件放进项目根的 `workspace/09端外海报图/活动TXT/`，然后运行 `--dry-run --file <TXT路径>` 或 `--dry-run --dir workspace/09端外海报图/活动TXT`。

`workspace/09端外海报图/临时图/` 只用于临时试跑或一次性材料；正式要批量处理的活动 TXT 优先放 `workspace/09端外海报图/活动TXT/`。

最终汇总表字段固定为：

| 品牌 | TXT 文件 | 模板 | 输出图路径 | 二维码验证 | 状态 | 失败原因 |
|---|---|---|---|---|---|---|

unsupported 和 ambiguous 文件也要列入汇总，并说明真实原因。
