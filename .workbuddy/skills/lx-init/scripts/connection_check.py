"""统一配置检查。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


@dataclass
class CheckItem:
    name: str
    status: str
    message: str


def check_config(config: dict[str, Any], project_root: Path) -> list[CheckItem]:
    """检查统一配置的完整性，不做写入。"""
    items: list[CheckItem] = []
    enabled = config.get("enabled_skills", {})

    if enabled.get("lx_zhutichaibiao") and not enabled.get("lx_shujuku"):
        items.append(CheckItem(
            name="enabled_skills",
            status="error",
            message="lx_zhutichaibiao 依赖 lx_shujuku，请同时启用 lx_shujuku",
        ))

    if enabled.get("lx_dapanribao") and not enabled.get("lx_shujuku"):
        items.append(CheckItem(
            name="enabled_skills.lx_shujuku",
            status="error",
            message="lx_dapanribao 依赖 lx_shujuku 查询日报数据，请同时启用 lx_shujuku",
        ))

    if enabled.get("lx_shujuku"):
        api = config.get("lx_shujuku", {}).get("api", {})
        _required(items, "lx_shujuku.api.base_url", api.get("base_url"), severity="error")
        _required(items, "lx_shujuku.api.username", api.get("username"), severity="error")
        _required(items, "lx_shujuku.api.password", api.get("password"), sensitive=True, severity="error")
    else:
        items.append(CheckItem("lx_shujuku", "skipped", "未启用"))

    if enabled.get("lx_zhutichaibiao"):
        zhutichaibiao = config.get("lx_zhutichaibiao", {})
        _required(items, "lx_zhutichaibiao.work_dir", zhutichaibiao.get("work_dir"), severity="error")
        persons = zhutichaibiao.get("default_persons", [])
        if not persons:
            items.append(CheckItem(
                "lx_zhutichaibiao.default_persons",
                "warning",
                "未配置默认对接人",
            ))
    else:
        items.append(CheckItem("lx_zhutichaibiao", "skipped", "未启用"))

    if enabled.get("lx_dapanribao"):
        dailyreport = config.get("lx_dapanribao", {})
        _required(items, "lx_dapanribao.default_person", dailyreport.get("default_person"))
        _required(items, "lx_dapanribao.output_dir", dailyreport.get("output_dir"))
        _required(items, "lx_dapanribao.publish_backend", dailyreport.get("publish_backend"))
        _required(items, "lx_dapanribao.enterprise_root_folder_url", dailyreport.get("enterprise_root_folder_url"))
        _required(items, "lx_dapanribao.enterprise_root_folder_id", dailyreport.get("enterprise_root_folder_id"))
        _required(items, "lx_dapanribao.report_title_template", dailyreport.get("report_title_template"))
        if not enabled.get("lx_txsaasdocs"):
            _check_lx_txsaasdocs(items, config, required=False)
    else:
        items.append(CheckItem("lx_dapanribao", "skipped", "未启用"))

    if enabled.get("lx_haibao"):
        haibao = config.get("lx_haibao", {})
        image_api = haibao.get("image_api", {}) if isinstance(haibao, dict) else {}
        configured = False
        if isinstance(image_api, dict):
            for provider_name in (
                image_api.get("provider_primary", "volcengine_seedream"),
                image_api.get("provider_fallback", "apimart"),
            ):
                provider = image_api.get(str(provider_name), {})
                if isinstance(provider, dict) and provider.get("api_key"):
                    configured = True
        if os.environ.get("ARK_API_KEY") or os.environ.get("APIMART_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            configured = True
        if configured:
            items.append(CheckItem("lx_haibao.image_api", "ok", "至少一个图片 provider 已配置 API Key"))
        else:
            items.append(CheckItem("lx_haibao.image_api", "warning", "未配置图片 API Key；海报生成不可用"))
    else:
        items.append(CheckItem("lx_haibao", "skipped", "未启用"))

    if enabled.get("lx_txdocs"):
        tdocs = _txdocs_tdocs_config(config)
        _required(items, "lx_txdocs.tdocs.root_folder_id", tdocs.get("root_folder_id"))
        openapi = tdocs.get("openapi", {})
        _required(items, "lx_txdocs.tdocs.openapi.client_id", openapi.get("client_id"))
        _required(items, "lx_txdocs.tdocs.openapi.access_token", openapi.get("access_token"), sensitive=True)
        _required(items, "lx_txdocs.tdocs.openapi.open_id", openapi.get("open_id"))
    else:
        items.append(CheckItem("lx_txdocs", "skipped", "未启用"))

    if enabled.get("lx_txsaasdocs"):
        _check_lx_txsaasdocs(items, config, required=True)
    else:
        items.append(CheckItem("lx_txsaasdocs", "skipped", "未启用"))

    if not items:
        items.append(CheckItem("config", "ok", "配置结构可用"))
    items.extend(_check_sensitive_file_permissions(project_root))
    return items


def has_errors(items: list[CheckItem]) -> bool:
    return any(item.status == "error" for item in items)


def _required(
    items: list[CheckItem],
    name: str,
    value: Any,
    sensitive: bool = False,
    severity: str = "warning",
) -> None:
    if value:
        message = "已配置" if not sensitive else "已配置（不显示）"
        items.append(CheckItem(name, "ok", message))
    else:
        items.append(CheckItem(name, severity, "未配置"))


def _txdocs_tdocs_config(config: dict[str, Any]) -> dict[str, Any]:
    txdocs = config.get("lx_txdocs", {})
    if isinstance(txdocs, dict) and isinstance(txdocs.get("tdocs"), dict):
        return txdocs["tdocs"]
    txwendang = config.get("lx_txwendang", {})
    if isinstance(txwendang, dict) and isinstance(txwendang.get("tdocs"), dict):
        return txwendang["tdocs"]
    return config.get("lx_zhutichaibiao", {}).get("tdocs", {})


def _check_lx_txsaasdocs(items: list[CheckItem], config: dict[str, Any], required: bool) -> None:
    skill_path = Path(__file__).resolve().parents[2] / "lx-txsaasdocs" / "SKILL.md"
    if skill_path.exists():
        items.append(CheckItem("skill.lx-txsaasdocs", "ok", f"已安装: {skill_path}"))
    else:
        severity = "error" if required else "warning"
        items.append(CheckItem("skill.lx-txsaasdocs", severity, f"未找到: {skill_path}"))

    api = config.get("lx_txsaasdocs", {}).get("api", {})
    if not isinstance(api, dict):
        api = {}
    severity = "error" if required else "warning"
    _required(items, "lx_txsaasdocs.api.base_url", api.get("base_url"), severity=severity)
    _required(items, "lx_txsaasdocs.api.token_endpoint", api.get("token_endpoint"), severity=severity)
    _required(items, "lx_txsaasdocs.api.client_id", api.get("client_id"), severity=severity)
    _required(items, "lx_txsaasdocs.api.client_secret", api.get("client_secret"), sensitive=True, severity=severity)


def _check_sensitive_file_permissions(project_root: Path) -> list[CheckItem]:
    """检查敏感配置文件权限，不读取文件内容。"""
    results: list[CheckItem] = []
    paths = [
        project_root / "config" / "fog_config.yaml",
        project_root / "config" / "personal_config.yaml",
    ]
    paths.extend((project_root / ".workbuddy" / "skills").glob("*/assets/*cache*.json"))
    paths.extend((project_root / ".workbuddy" / "skills").glob("*/assets/entity_cache.json"))

    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if not path.exists():
            continue
        mode = path.stat().st_mode & 0o777
        name = f"permissions.{_rel(path, project_root)}"
        if mode & 0o077:
            results.append(CheckItem(
                name=name,
                status="warning",
                message=f"权限 {mode:o} 过宽，建议 chmod 600",
            ))
        else:
            results.append(CheckItem(
                name=name,
                status="ok",
                message=f"权限 {mode:o}",
            ))
    return results


def _rel(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path)
