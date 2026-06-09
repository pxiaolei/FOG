#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from common import as_list, load_brands, load_templates, resolve_path, route_name, skill_root
from qr_verify import build_result as verify_qr


def _find_skills_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "lxx_share").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


_SKILLS_DIR = _find_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from lxx_share.fog_config import get_section, resolve_project_path as resolve_fog_path  # noqa: E402

logger = logging.getLogger("lx-haibao")


REQUIRED_RUNTIME_MODULES = {
    "requests": "requests",
    "Pillow": "PIL",
    "zxing-cpp": "zxingcpp",
}

COMMON_POSTER_RULES = """用户本次提供的 TXT 中，所有活动模块默认都要展示；"全量活动"属于正常展示模块。
只排除内部属性、历史/过期/已结束/仅供参考/明确标记不展示的内容。
不得引用模板图、旧海报、历史输出或其他品牌活动里的日期、城市、价格、奖励和规则。
TXT 没有的活动模块不展示，不写"无""暂无""无卡券"。
模块标题不展示 1/2/3/4/5/6 等序号徽标，统一使用纯模块标题。
海报文案不得展示"共补""共补免佣""平台共补""是否共补"等内部补贴属性。
卡券按日期展示，每个日期内先分"全天卡"和"时段卡"，时段卡按时间从早到晚。
新人免佣奖只展示免佣天数，不展示适用订单；新人成长奖才展示首单奖励、X天完成X单奖励等任务规则。
二维码必须使用第三张参考图中的品牌真实二维码，保持正方形、清晰、完整、无遮挡、不倾斜、不透视、不裁切、不拉伸、不重绘。
不要生成替代二维码、假二维码、二维码纹理、条形码或抽象扫码图案。"""

CITY_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,12}(?:市|县|区|州|盟)")
SECTION_HEADING_PATTERN = re.compile(r"^【\s*(.+?)\s*】\s*$")
EXCLUDED_SECTION_PATTERNS = (
    ("共补/平台共补", re.compile(r"共补|平台共补|是否共补")),
    ("历史/过期/已结束/仅供参考/明确不展示", re.compile(r"历史|过期|已结束|仅供参考|不展示")),
)
EXCLUDED_LINE_PATTERNS = (
    ("共补/平台共补", re.compile(r"共补|平台共补|是否共补")),
    ("历史/过期/已结束/仅供参考/明确不展示", re.compile(r"历史|过期|已结束|仅供参考|不展示")),
)


def read_text_guess(path: Path) -> str:
    encodings = ("utf-8-sig", "utf-8", "gb18030")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"无法读取 TXT 文件编码：{path}，最后错误：{last_error}")


def collect_input_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for file_arg in args.file or []:
        paths.append(Path(file_arg).expanduser().resolve())
    if args.dir:
        folder = Path(args.dir).expanduser().resolve()
        if not folder.is_dir():
            raise SystemExit(f"ERROR: directory not found: {folder}")
        paths.extend(sorted(folder.glob("*.txt")))
    return paths


def extract_city_from_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "📍" in stripped or "城市" in stripped:
            match = CITY_PATTERN.search(stripped)
            if match:
                return match.group(0)
    match = CITY_PATTERN.search(text)
    return match.group(0) if match else None


def extract_city_from_filename(path: Path, brand: dict[str, Any]) -> str:
    stem = path.stem
    text = stem
    for keyword in sorted((str(item) for item in as_list(brand.get("filename_keywords"))), key=len, reverse=True):
        text = text.replace(keyword, "")
    text = re.sub(r"^[\s_\-—]+|[\s_\-—]+$", "", text)
    parts = [part for part in re.split(r"[\s_\-—]+", text) if part]
    for part in parts:
        if re.search(r"[\u4e00-\u9fff].*(市|县|区|州|盟)$", part):
            return part
    for part in parts:
        if re.search(r"[\u4e00-\u9fff]", part) and not re.search(r"\d{4}", part):
            return part
    return text or stem


def resolve_city(
    path: Path,
    brand: dict[str, Any],
    *,
    txt_content: str | None = None,
    city_override: str | None = None,
) -> tuple[str, str]:
    if city_override:
        return city_override.strip(), "arg"
    if txt_content:
        city_from_text = extract_city_from_text(txt_content)
        if city_from_text:
            return city_from_text, "txt"
    return extract_city_from_filename(path, brand), "filename"


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)[:80] or "poster"


def import_errors() -> list[str]:
    errors: list[str] = []
    for package, module_name in REQUIRED_RUNTIME_MODULES.items():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - report the exact runtime import failure.
            errors.append(f"{package}: {exc}")
    return errors


def output_dirs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = skill_root()
    config = get_section("lx_haibao", Path(__file__))

    output_value = args.output_dir or os.environ.get("POSTER_OUTPUT_DIR") or config.get("output_dir")
    meta_value = os.environ.get("POSTER_META_DIR") or config.get("meta_dir")
    tmp_value = os.environ.get("POSTER_TMP_DIR") or config.get("tmp_dir")

    output = resolve_fog_path(output_value, Path(__file__)) if output_value else root / "output" / "posters"
    meta = resolve_fog_path(meta_value, Path(__file__)) if meta_value else root / "output" / "meta"
    tmp = resolve_fog_path(tmp_value, Path(__file__)) if tmp_value else root / "output" / "tmp"
    output.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    return output.resolve(), meta.resolve(), tmp.resolve()


def select_template(template_id: str | None = None) -> dict[str, Any]:
    templates = load_templates(skill_root())
    if not templates:
        raise RuntimeError("templates.yaml 中没有可用模板。")
    if template_id:
        for template in templates:
            if template["template_id"] == template_id:
                return template
        available = ", ".join(template["template_id"] for template in templates)
        raise RuntimeError(f"未知模板：{template_id}。可用模板：{available}")
    return templates[0]


def build_rows(paths: list[Path], brands: list[dict[str, Any]], city_override: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    brands_by_id = {str(brand["brand_id"]): brand for brand in brands}
    for path in paths:
        row = route_name(path.name, brands)
        row["path"] = str(path)
        if row["status"] == "supported":
            brand = brands_by_id[str(row["brand_id"])]
            try:
                txt_content = read_text_guess(path)
            except Exception:
                txt_content = None
            row["city"], row["city_source"] = resolve_city(
                path,
                brand,
                txt_content=txt_content,
                city_override=city_override,
            )
            filename_template = brand.get("output", {}).get("filename_template") or "{brand}-{city}-{timestamp}.png"
            row["output_name"] = str(filename_template).format(brand=brand["canonical_name"], city=row["city"], timestamp="YYYYMMDD_HHMMSS")
        rows.append(row)

    sample_by_brand: dict[str, str] = {}
    for row in rows:
        if row["status"] == "supported":
            sample_by_brand.setdefault(str(row["brand_id"]), str(row["path"]))
    for row in rows:
        if row["status"] == "supported":
            sample_path = sample_by_brand[str(row["brand_id"])]
            row["sample_file"] = Path(sample_path).name
            row["is_sample"] = str(row["path"]) == sample_path
    return rows


def reference_paths(brand: dict[str, Any], template: dict[str, Any]) -> list[Path]:
    root = skill_root()
    paths = [
        resolve_path(template["example_path"], root),
        resolve_path(brand.get("assets", {}).get("logo_path", ""), root),
        resolve_path(brand.get("assets", {}).get("qr_path", ""), root),
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError("参考图缺失：" + "；".join(missing))
    return paths


def text_preview(text: str, limit: int = 18) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:limit]


def detect_modules(text: str) -> list[str]:
    modules: list[str] = []
    for label, pattern in (
        ("免佣/飞涨奖", r"免佣|飞涨|流水"),
        ("卡券概览", r"卡券|全天卡|时段卡"),
        ("全量活动", r"全量活动|周卡"),
        ("新人权益", r"新人|成长奖|首单"),
        ("司邀司", r"司邀司|邀请"),
        ("定向活动", r"定向"),
        ("完单奖", r"完单奖"),
    ):
        if re.search(pattern, text):
            modules.append(label)
    return modules


def detect_hidden_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for label, pattern in EXCLUDED_SECTION_PATTERNS:
        if pattern.search(text):
            candidates.append(label)
    return candidates


def split_activity_sections(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    title: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        heading = SECTION_HEADING_PATTERN.match(line.strip())
        if heading:
            if lines:
                sections.append({"title": title, "lines": lines})
            title = heading.group(1).strip()
            lines = [line]
            continue
        lines.append(line)
    if lines:
        sections.append({"title": title, "lines": lines})
    return sections


def filter_display_content(text: str) -> tuple[str, list[str]]:
    display_blocks: list[str] = []
    excluded: list[str] = []
    for section in split_activity_sections(text):
        title = str(section.get("title") or "")
        lines = [str(line) for line in section.get("lines") or []]
        matched_section_exclusion = next(
            (label for label, pattern in EXCLUDED_SECTION_PATTERNS if pattern.search(title)),
            None,
        )
        if matched_section_exclusion:
            excluded.append(f"{title or '未命名段落'}：{matched_section_exclusion}")
            continue

        kept_lines: list[str] = []
        for line in lines:
            matched_line_exclusion = next(
                (label for label, pattern in EXCLUDED_LINE_PATTERNS if pattern.search(line)),
                None,
            )
            if matched_line_exclusion:
                excluded.append(f"{title or '未命名段落'} 行：{matched_line_exclusion}")
                continue
            kept_lines.append(line)
        if any(line.strip() for line in kept_lines):
            display_blocks.append("\n".join(kept_lines).strip("\n"))

    display_text = "\n\n".join(block for block in display_blocks if block)
    return display_text or text, sorted(set(excluded))


def attach_confirmation_materials(rows: list[dict[str, Any]], template: dict[str, Any]) -> None:
    for row in rows:
        if row["status"] != "supported":
            continue
        path = Path(str(row["path"]))
        try:
            text = read_text_guess(path)
        except Exception as exc:  # noqa: BLE001 - expose unreadable TXT instead of guessing.
            row["confirmation_error"] = str(exc)
            continue
        display_text, excluded = filter_display_content(text)
        row["confirmation"] = {
            "brand": row.get("brand", ""),
            "city": row.get("city", ""),
            "city_source": row.get("city_source", ""),
            "template": f"{template['display_name']} ({template['template_id']})",
            "sample_file": row.get("sample_file", ""),
            "is_sample": bool(row.get("is_sample")),
            "output_name": row.get("output_name", ""),
            "txt_char_count": len(text),
            "txt_line_count": len(text.splitlines()),
            "display_char_count": len(display_text),
            "detected_modules": detect_modules(display_text),
            "hidden_candidates": excluded or detect_hidden_candidates(text),
            "txt_preview": text_preview(text),
        }


def compile_prompt(
    *,
    brand: dict[str, Any],
    city: str,
    template: dict[str, Any],
    txt_path: Path,
    txt_content: str,
    excluded_content: list[str] | None = None,
    qr_retry_note: str | None = None,
) -> str:
    brand_name = str(brand.get("canonical_name"))
    style_notes = "\n".join(f"- {item}" for item in as_list(brand.get("style_notes")))
    retry_block = f"\n二维码上次验证失败，必须修正：{qr_retry_note}\n" if qr_retry_note else ""
    return f"""请生成一张竖版司机城市活动海报。

输出目标：
- 品牌：{brand_name}
- 城市：{city}
- 模板：{template['display_name']}（{template['template_id']}）
- 活动 TXT 文件：{txt_path.name}

参考图输入顺序：
1. 模板示例图：只参考版式结构、模块顺序、留白和信息层级，不复制其中的旧内容。
2. 品牌 Logo：必须使用真实 Logo，不要重绘或替换品牌字样。
3. 品牌二维码：必须原样放入海报，保持可扫码。

品牌视觉要求：
{style_notes}

通用内容规则：
{COMMON_POSTER_RULES}
{retry_block}
请从下面"可展示活动内容"中提取活动内容，并尽量覆盖其中所有模块。不要编造城市、日期、金额、奖励、门槛或活动规则。
已排除内容：{"；".join(excluded_content or ["无"])}

可展示活动内容：
<<<TXT
{txt_content}
TXT
>>>
"""


def markdown_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 品牌 | TXT 文件 | 模板 | 输出图路径 | 二维码验证 | 状态 | 失败原因 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {brand} | {txt} | {template} | {path} | {qr} | {status} | {reason} |".format(
                brand=row.get("brand", ""),
                txt=Path(str(row.get("path", row.get("name", "")))).name,
                template=row.get("template", ""),
                path=row.get("output_path", ""),
                qr=row.get("qr_validation", ""),
                status=row.get("run_status", row.get("status", "")),
                reason=row.get("failure_reason", row.get("reason", "")),
            )
        )
    return "\n".join(lines)


def print_dry_run(rows: list[dict[str, Any]], template: dict[str, Any]) -> None:
    logger.info("DRY RUN: no image API will be called.")
    logger.info("Selected template: %s (%s)", template["display_name"], template["template_id"])
    print()
    for row in rows:
        if row["status"] == "supported":
            sample = "sample=yes" if row.get("is_sample") else f"sample={row.get('sample_file')}"
            print(
                f"SUPPORTED  {row['brand']}  {Path(row['path']).name}  "
                f"city={row.get('city')} city_source={row.get('city_source')} keyword={row['matched_keyword']} "
                f"output={row.get('output_name')} {sample}"
            )
        elif row["status"] == "ambiguous":
            matches = ", ".join(f"{item['brand']}({item['keyword']})" for item in row["matches"])
            print(f"AMBIGUOUS  {Path(row['path']).name}  matches={matches}")
        else:
            print(f"UNSUPPORTED  {Path(row['path']).name}  reason={row['reason']}")
    print()
    print("待用户确认清单：")
    print(markdown_summary([{**row, "template": template["display_name"]} for row in rows]))
    print()
    print("确认材料（仅来自真实 TXT 文件，未调用图片 API）：")
    for row in rows:
        if row["status"] != "supported":
            continue
        print()
        print(f"### {row['brand']} / {Path(row['path']).name}")
        if row.get("confirmation_error"):
            print(f"- TXT 读取失败：{row['confirmation_error']}")
            continue
        confirmation = row.get("confirmation", {})
        modules = "、".join(confirmation.get("detected_modules") or ["未命中常见模块关键词"])
        hidden = "、".join(confirmation.get("hidden_candidates") or ["未命中"])
        print(f"- 城市：{confirmation.get('city')}")
        print(f"- 模板：{confirmation.get('template')}")
        print(f"- 样图文件：{confirmation.get('sample_file')}")
        print(f"- 成品命名：{confirmation.get('output_name')}")
        print(f"- 城市来源：{confirmation.get('city_source')}")
        print(f"- 关键词命中模块：{modules}")
        print(f"- 排除候选关键词：{hidden}")
        print(
            f"- TXT 行数/字符数：{confirmation.get('txt_line_count')} 行 / "
            f"{confirmation.get('txt_char_count')} 字符；可展示内容 {confirmation.get('display_char_count')} 字符"
        )
        print("- TXT 预览：")
        for line in confirmation.get("txt_preview") or []:
            print(f"  {line}")
    print()
    print("确认以上内容后，生成样图或批量成品时必须追加 --confirmed。")


def run_check(template_id: str | None = None) -> dict[str, Any]:
    root = skill_root()
    errors: list[str] = []
    details: dict[str, Any] = {
        "skill_root": str(root),
        "dependencies": {},
        "templates": [],
        "brands": [],
    }

    for package, module_name in REQUIRED_RUNTIME_MODULES.items():
        try:
            importlib.import_module(module_name)
            details["dependencies"][package] = {"ok": True}
        except Exception as exc:  # noqa: BLE001 - health check reports exact import failure.
            message = str(exc)
            details["dependencies"][package] = {"ok": False, "error": message}
            errors.append(f"依赖不可用：{package}: {message}")

    try:
        templates = load_templates(root)
    except Exception as exc:  # noqa: BLE001 - report invalid template file as a check failure.
        templates = []
        errors.append(f"模板索引读取失败：{exc}")

    if not templates:
        errors.append("templates.yaml 中没有可用模板。")
    for template in templates:
        template_path = resolve_path(template.get("example_path", ""), root)
        item = {
            "template_id": template.get("template_id"),
            "display_name": template.get("display_name"),
            "example_path": str(template_path),
            "ok": template_path.is_file(),
        }
        if not item["ok"]:
            errors.append(f"模板示例图不存在：{template_path}")
        details["templates"].append(item)
    if template_id and not any(template.get("template_id") == template_id for template in templates):
        errors.append(f"指定模板不存在：{template_id}")

    try:
        brands = load_brands(root)
    except Exception as exc:  # noqa: BLE001 - report invalid brand config as a check failure.
        brands = []
        errors.append(f"品牌配置读取失败：{exc}")

    if not brands:
        errors.append("brands/ 中没有可用品牌配置。")
    seen_brand_ids: set[str] = set()
    for brand in brands:
        brand_errors: list[str] = []
        brand_id = str(brand.get("brand_id") or "")
        canonical = str(brand.get("canonical_name") or brand_id)
        if not brand_id:
            brand_errors.append("brand_id 为空")
        elif brand_id in seen_brand_ids:
            brand_errors.append(f"brand_id 重复：{brand_id}")
        seen_brand_ids.add(brand_id)
        if not canonical:
            brand_errors.append("canonical_name 为空")
        if not as_list(brand.get("filename_keywords")):
            brand_errors.append("filename_keywords 为空")

        assets = brand.get("assets", {})
        logo_path = resolve_path(str(assets.get("logo_path") or ""), root)
        qr_path = resolve_path(str(assets.get("qr_path") or ""), root)
        if not logo_path.is_file():
            brand_errors.append(f"logo 不存在：{logo_path}")
        if not qr_path.is_file():
            brand_errors.append(f"二维码不存在：{qr_path}")

        qr_result: dict[str, Any] | None = None
        if qr_path.is_file():
            # 传入 brands 避免重复加载
            qr_result = verify_qr(canonical, qr_path, brands=brands)
            if not qr_result.get("ok"):
                brand_errors.append(
                    "源二维码自检失败："
                    + str(qr_result.get("message") or qr_result.get("error") or "unknown error")
                )

        if brand_errors:
            errors.extend(f"{canonical}: {item}" for item in brand_errors)
        details["brands"].append(
            {
                "brand_id": brand_id,
                "canonical_name": canonical,
                "config_path": brand.get("_config_path"),
                "logo_path": str(logo_path),
                "qr_path": str(qr_path),
                "qr_ok": bool(qr_result and qr_result.get("ok")),
                "errors": brand_errors,
            }
        )

    return {"ok": not errors, "errors": errors, "details": details}


def print_check(result: dict[str, Any]) -> None:
    status = "OK" if result["ok"] else "FAIL"
    details = result["details"]
    print(f"{status}: lx-haibao check")
    print(f"skill_root={details['skill_root']}")
    print()
    print("Dependencies:")
    for package, item in details["dependencies"].items():
        if item["ok"]:
            print(f"- {package}: OK")
        else:
            print(f"- {package}: FAIL ({item['error']})")
    print()
    print("Templates:")
    for template in details["templates"]:
        template_status = "OK" if template["ok"] else "FAIL"
        print(f"- {template['template_id']}: {template_status} {template['example_path']}")
    print()
    print("Brands:")
    for brand in details["brands"]:
        brand_status = "OK" if not brand["errors"] else "FAIL"
        print(f"- {brand['canonical_name']} ({brand['brand_id']}): {brand_status}")
        print(f"  logo={brand['logo_path']}")
        print(f"  qr={brand['qr_path']} qr_ok={brand['qr_ok']}")
        for error in brand["errors"]:
            print(f"  error={error}")
    if result["errors"]:
        print()
        print("Errors:")
        for error in result["errors"]:
            print(f"- {error}")


def print_provider_check(result: dict[str, Any]) -> None:
    status = "OK" if result["ok"] else "FAIL"
    print(f"{status}: lx-haibao image providers")
    print(f"primary={result.get('primary') or ''}")
    print(f"fallback={result.get('fallback') or ''}")
    print(result.get("note") or "")
    print()
    print("| Provider | Order | Model | API Key | Reachable | HTTP | Latency ms | Status | Error |")
    print("|---|---:|---|---|---|---:|---:|---|---|")
    for item in result["providers"]:
        api_key = "configured" if item.get("api_key_configured") else "missing"
        reachable = "yes" if item.get("reachable") else "no"
        order = item.get("enabled_order") or ""
        http_status = item.get("http_status") or ""
        latency_ms = item.get("latency_ms") if item.get("latency_ms") is not None else ""
        print(
            "| {provider} | {order} | {model} | {api_key} | {reachable} | {http_status} | {latency_ms} | {status} | {error} |".format(
                provider=item.get("provider") or "",
                order=order,
                model=item.get("model") or "",
                api_key=api_key,
                reachable=reachable,
                http_status=http_status,
                latency_ms=latency_ms,
                status=item.get("status") or "",
                error=str(item.get("error") or "").replace("|", "/"),
            )
        )


def save_metadata(meta_dir: Path, payload: dict[str, Any]) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = safe_filename(str(payload.get("txt_file") or "poster"))
    path = meta_dir / f"{ts}_{stem}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def generate_one(
    *,
    row: dict[str, Any],
    brand: dict[str, Any],
    template: dict[str, Any],
    output_dir: Path,
    meta_dir: Path,
    tmp_dir: Path,
    sample_only: bool,
    max_retries: int,
    size: str,
    resolution: str,
    skip_qr: bool = False,
    brands: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from image2_client import generate_image

    txt_path = Path(str(row["path"]))
    txt_content = read_text_guess(txt_path)
    display_content, excluded_content = filter_display_content(txt_content)
    city, city_source = resolve_city(txt_path, brand, txt_content=txt_content)
    if row.get("city"):
        city = str(row["city"])
        city_source = str(row.get("city_source") or city_source)
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_template = brand.get("output", {}).get("filename_template") or "{brand}-{city}-{timestamp}.png"
    output_name = str(filename_template).format(brand=brand["canonical_name"], city=city, timestamp=file_ts)
    if sample_only:
        output_name = output_name.replace(".png", "-sample.png")
    final_path = output_dir / output_name
    refs = reference_paths(brand, template)

    qr_retry_note: str | None = None
    last_failure = ""
    for attempt in range(max_retries + 1):
        logger.info(
            "开始生成海报：品牌=%s 城市=%s 城市来源=%s TXT=%s 尝试=%d/%d",
            brand["canonical_name"],
            city,
            city_source,
            txt_path.name,
            attempt + 1,
            max_retries + 1,
        )
        prompt = compile_prompt(
            brand=brand,
            city=city,
            template=template,
            txt_path=txt_path,
            txt_content=display_content,
            excluded_content=excluded_content,
            qr_retry_note=qr_retry_note,
        )
        tmp_path = tmp_dir / f"{safe_filename(brand['brand_id'])}_{safe_filename(city)}_{attempt + 1}.png"
        try:
            api_result = generate_image(
                prompt=prompt,
                reference_images=refs,
                output_path=tmp_path,
                size=size,
                resolution=resolution,
            )
            if skip_qr:
                qr_result = {"ok": True, "brand": brand["canonical_name"], "skipped": True, "message": "QR validation skipped (--skip-qr)."}
            else:
                # 传入 brands 避免每次验证都重新加载
                qr_result = verify_qr(str(brand["canonical_name"]), tmp_path, brands=brands)
            meta_path = save_metadata(
                meta_dir,
                {
                    "txt_file": str(txt_path),
                    "brand": brand["canonical_name"],
                    "city": city,
                    "city_source": city_source,
                    "template": template,
                    "attempt": attempt + 1,
                    "display_content": display_content,
                    "excluded_content": excluded_content,
                    "prompt": prompt,
                    "reference_images": [str(path) for path in refs],
                    "api_result": api_result,
                    "qr_result": qr_result,
                    "final_path": str(final_path),
                },
            )
            if qr_result.get("ok"):
                final_path.parent.mkdir(parents=True, exist_ok=True)
                if final_path.exists():
                    final_path.unlink()
                shutil.move(str(tmp_path), str(final_path))
                return {
                    **row,
                    "template": template["display_name"],
                    "output_path": str(final_path),
                    "qr_validation": "通过",
                    "run_status": "完成",
                    "failure_reason": "",
                    "metadata_path": str(meta_path),
                }
            last_failure = str(qr_result.get("message") or qr_result.get("error") or "二维码验证失败")
            qr_retry_note = last_failure + "。请确保第三张参考图中的二维码被完整、清晰、无变形地放入海报。"
            logger.warning("品牌 %s 城市 %s 第 %d 次尝试 QR 验证失败：%s", brand["canonical_name"], city, attempt + 1, last_failure)
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception as exc:  # noqa: BLE001 - summarize per-file failures without stopping other brands.
            last_failure = str(exc)
            logger.error("品牌 %s 城市 %s 生成失败：%s", brand["canonical_name"], city, exc)
            if tmp_path.exists():
                tmp_path.unlink()
            break

    return {
        **row,
        "template": template["display_name"],
        "output_path": "",
        "qr_validation": "未通过",
        "run_status": "失败",
        "failure_reason": last_failure,
    }


def main() -> int:
    # 配置 logging：控制台输出 + 文件日志
    log_dir = skill_root() / "output" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(log_dir / f"{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"),
        ],
    )

    parser = argparse.ArgumentParser(description="WorkBuddy poster batch generator using configured image providers.")
    parser.add_argument("--check", action="store_true", help="Validate dependencies, brand assets, templates, and source QR codes without generating images.")
    parser.add_argument("--check-providers", action="store_true", help="Check image provider config and base_url connectivity without generating images.")
    parser.add_argument("--dir", help="Directory containing activity TXT files.")
    parser.add_argument("--file", action="append", help="Single activity TXT path. Can be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Route files and preview confirmation table without calling image API.")
    parser.add_argument("--confirmed", action="store_true", help="Required for sample or final image generation after the user confirms dry-run content.")
    parser.add_argument("--sample-only", action="store_true", help="Generate only the first routed TXT per brand.")
    parser.add_argument("--template", help="Template id from templates.yaml. Defaults to the first template.")
    parser.add_argument("--city", help="Override city name for all input TXT files. Default: parse from TXT content, then filename.")
    parser.add_argument("--output-dir", help="Override poster output directory.")
    parser.add_argument("--size", default=os.environ.get("POSTER_IMAGE_SIZE", "9:16"), help="Business size/aspect value. Seedream maps 9:16 to a 2K portrait pixel size by default.")
    parser.add_argument("--resolution", default=os.environ.get("POSTER_IMAGE_RESOLUTION", "2k"), help="APIMart resolution value; Seedream uses it only when --size is a resolution value.")
    parser.add_argument("--max-retries", type=int, default=2, help="QR failure retries per poster.")
    parser.add_argument("--skip-qr", action="store_true", help="Skip QR code validation (for environments without zxingcpp).")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers for brand generation (default: 1, sequential).")
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    args = parser.parse_args()

    if args.check:
        result = run_check(args.template)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_check(result)
        return 0 if result["ok"] else 1

    if args.check_providers:
        from image2_client import check_providers

        result = check_providers()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_provider_check(result)
        return 0 if result["ok"] else 1

    paths = collect_input_paths(args)
    if not paths:
        logger.error("未提供输入文件，请使用 --file 或 --dir")
        return 1
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        logger.error("TXT 文件不存在：%s", "；".join(missing))
        return 1

    brands = load_brands(skill_root())
    template = select_template(args.template)
    rows = build_rows(paths, brands, city_override=args.city)
    brands_by_id = {str(brand["brand_id"]): brand for brand in brands}

    if args.dry_run:
        attach_confirmation_materials(rows, template)
        if args.json:
            print(json.dumps({"dry_run": True, "template": template, "routes": rows}, ensure_ascii=False, indent=2))
        else:
            print_dry_run(rows, template)
        return 0

    if not args.confirmed:
        logger.error("图片生成需要 --confirmed。请先运行 --dry-run，确认 TXT 内容后，再追加 --confirmed。")
        return 2

    dependency_errors = import_errors()
    if dependency_errors and not args.skip_qr:
        logger.error("运行时依赖不可用：%s", "；".join(dependency_errors))
        return 1
    if dependency_errors and args.skip_qr:
        zxing_errors = [e for e in dependency_errors if "zxing" in e.lower()]
        other_errors = [e for e in dependency_errors if "zxing" not in e.lower()]
        if other_errors:
            logger.error("运行时依赖不可用：%s", "；".join(other_errors))
            return 1
        logger.warning("跳过 QR 验证 (--skip-qr)；zxing-cpp 不可用：%s", zxing_errors[0])

    from image2_client import require_api_key

    try:
        require_api_key()
    except RuntimeError as exc:
        logger.error("%s；未调用图片 API。", exc)
        return 1

    output_dir, meta_dir, tmp_dir = output_dirs(args)

    # 筛选需要生成的行
    gen_rows: list[dict[str, Any]] = []
    skip_rows: list[dict[str, Any]] = []
    for row in rows:
        if row["status"] != "supported":
            skip_rows.append(
                {
                    **row,
                    "template": "",
                    "output_path": "",
                    "qr_validation": "",
                    "run_status": "未生成",
                    "failure_reason": row.get("reason", ""),
                }
            )
            continue
        if args.sample_only and not row.get("is_sample"):
            skip_rows.append(
                {
                    **row,
                    "template": template["display_name"],
                    "output_path": "",
                    "qr_validation": "",
                    "run_status": "跳过",
                    "failure_reason": "sample-only 模式只生成每个品牌第一个 TXT",
                }
            )
            continue
        gen_rows.append(row)

    # 按品牌分组，同品牌保持顺序，不同品牌可并行
    workers = max(1, args.workers)
    results: list[dict[str, Any]] = list(skip_rows)

    if workers > 1 and len(gen_rows) > 1:
        logger.info("使用 %d 个并行 worker 生成 %d 张海报", workers, len(gen_rows))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for row in gen_rows:
                brand = brands_by_id[str(row["brand_id"])]
                future = pool.submit(
                    generate_one,
                    row=row,
                    brand=brand,
                    template=template,
                    output_dir=output_dir,
                    meta_dir=meta_dir,
                    tmp_dir=tmp_dir,
                    sample_only=args.sample_only,
                    max_retries=args.max_retries,
                    size=args.size,
                    resolution=args.resolution,
                    skip_qr=args.skip_qr,
                    brands=brands,
                )
                futures[future] = row
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001 - don't let one failure kill the batch.
                    row = futures[future]
                    logger.error("并行生成异常：%s", exc)
                    results.append({
                        **row,
                        "template": template["display_name"],
                        "output_path": "",
                        "qr_validation": "",
                        "run_status": "失败",
                        "failure_reason": str(exc),
                    })
    else:
        for row in gen_rows:
            brand = brands_by_id[str(row["brand_id"])]
            results.append(
                generate_one(
                    row=row,
                    brand=brand,
                    template=template,
                    output_dir=output_dir,
                    meta_dir=meta_dir,
                    tmp_dir=tmp_dir,
                    sample_only=args.sample_only,
                    max_retries=args.max_retries,
                    size=args.size,
                    resolution=args.resolution,
                    skip_qr=args.skip_qr,
                    brands=brands,
                )
            )

    if args.json:
        print(json.dumps({"dry_run": False, "template": template, "results": results}, ensure_ascii=False, indent=2))
    else:
        print(markdown_summary(results))
    return 1 if any(row.get("run_status") == "失败" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
