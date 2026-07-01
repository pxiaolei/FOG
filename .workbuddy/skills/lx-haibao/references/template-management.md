# 模板与品牌维护

## 目录

- `assets/templates/templates.yaml` 是当前模板池索引。
- `assets/templates/template01.png` 到 `assets/templates/template10.png` 是当前可用模板图。
- `assets/templates/template-candidates-contact-sheet.png` 是当前模板总览图。
- `assets/templates/archive/` 保存历史参考图或未纳入当前模板池的图片。
- `brands/*.yaml` 保存品牌路由、展示名、模板绑定、Logo/二维码路径和校验值。
- `brand-assets/<brand>/logo.png` 和 `brand-assets/<brand>/qr.png` 是品牌真实素材。该目录保持现有结构。

## 当前模板绑定

已绑定：

| 品牌路由 | brand_id | 模板 |
|---|---|---|
| 哈啰、哈啰轻快 | `halo` | `template02` |
| 蔚蓝、蔚蓝滴仕 | `weilan` | `template01` |
| 安安、安安用车 | `anan` | `template03` |
| 旗妙、旗妙出行、旗妙出行极速版 | `qimiaochuxingjisu` | `template06` |
| 易达、易达出行、易达-其他 | `yidahcuxing` | `template10` |
| 江南出行 | `jiangnan` | `template03` |
| 土生途行 | `tusheng` | `template07` |
| 网路优行 | `wangluyouxing` | `template10` |

新出现但暂未接入的素材目录：`renwodache`、`richuchuxing`、`wangluchuxing`、`yidayouxing`。用户明确要求接入前，不要为这些目录创建品牌配置。

## 绑定模板

在对应 `brands/<brand_id>.yaml` 写入：

```yaml
template:
  preferred_template_id: "template02"
```

绑定后必须运行：

```bash
./haibao.sh --check
./haibao.sh --check-brand-locks
```

## 新增品牌

新增品牌时按顺序做：

1. 创建 `brand-assets/<brand_id>/logo.png` 和 `brand-assets/<brand_id>/qr.png`。
2. 解码源二维码，确认唯一 decoded value。
3. 创建 `brands/<brand_id>.yaml`，包含 `brand_id`、`canonical_name`、`aliases`、`filename_keywords`、`assets`、`display`、`output`、`qr_validation`。
4. 在 `brands/brands.yaml` 增加 brand_id。
5. 如已选模板，写入 `template.preferred_template_id`。
6. 运行 `--check` 和 `--check-brand-locks`。
7. 用该品牌真实 TXT 跑 `--dry-run`，确认路由命中。

## 模板规则

- 当前模板命名使用 `template01` 到 `template10`。
- 模板图必须品牌中性，只保留版式结构、信息层级和扫码区位置感，不保留旧品牌、旧二维码或假二维码。
- 模板不要内置大白底扫码卡片；二维码白边和卡片由脚本后处理生成，避免模型把白底当成真实内容放大或错位。
- 默认 `hybrid` 模式依赖 `qr_overlay`，用于把真实二维码贴入模板扫码区；模型不生成二维码。多品牌模板建议使用 `anchor: bottom_right`，让二维码按最终海报右下角几何边距定位。`bottom_right` 默认启用确定性 footer：脚本按 `size_ratio`、`padding_ratio`、`right_margin_ratio`、`bottom_margin_ratio` 和 `footer_height_ratio` 重绘整条底栏，并把真实二维码卡片在 footer 内垂直居中，避免模型生成的扫码框或伪二维码残留。
- 品牌 footer 色优先来自 `brands/<brand_id>.yaml` 的 `display.footer_color`，也可在单个模板 `qr_overlay.footer_color` 临时覆盖；未配置时才从模型生成图底部采样回退。
- 如果模板底部没有安全贴码区，或旧版二维码原本位于顶部，给该模板的 `qr_overlay` 增加 `append_footer_for_qr: true`；脚本会在最终海报底部追加一段同色 footer 后再贴二维码，避免覆盖原活动内容。
- 如模板需要支持内容偏多时自动拉长，配置 `content_sizing.long_size` 和对应阈值；默认策略应优先拉长画幅，不把活动模块硬压进固定高度。
- 如需启用旧版 `--asset-mode overlay`，每张模板只允许一个二维码占位区；`qr_overlay` 使用最终海报宽高比例，`x_ratio` 和 `y_ratio` 表示二维码左上角，`size_ratio` 按宽度计算。
- 模板图改名或移动后，同步更新 `assets/templates/templates.yaml`。
- 模板新增或替换后，重新生成 `assets/templates/template-candidates-contact-sheet.png` 供人工选择。
