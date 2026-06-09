#!/usr/bin/env python3
from __future__ import annotations

import base64
import binascii
import functools
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def _find_skills_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "lxx_share").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


_SKILLS_DIR = _find_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from lxx_share.fog_config import get_section  # noqa: E402


DEFAULT_PROVIDER_PRIMARY = "volcengine_seedream"
DEFAULT_PROVIDER_FALLBACK = "apimart"

DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_ARK_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_ARK_SIZE = "1600x2848"
DEFAULT_ARK_RESPONSE_FORMAT = "url"
DEFAULT_ARK_OUTPUT_FORMAT = "png"

DEFAULT_APIMART_BASE_URL = "https://api.apimart.ai/v1"
DEFAULT_APIMART_MODEL = "gpt-image-2"

TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
NON_FALLBACK_STATUS_CODES = {400, 401, 403}


class ImageProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str = "",
        error_code: str = "",
        request_id: str = "",
        latency_ms: int | None = None,
        fallback_allowed: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.error_code = error_code
        self.request_id = request_id
        self.latency_ms = latency_ms
        self.fallback_allowed = fallback_allowed


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


@functools.lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    section = get_section("lx_haibao", Path(__file__))
    image_api = section.get("image_api")
    if isinstance(image_api, dict):
        return image_api
    return {}


def _provider_config(provider: str) -> dict[str, Any]:
    data = _load_config().get(provider)
    return data if isinstance(data, dict) else {}


def _top_config_value(key: str, env_name: str, default: str = "") -> str:
    config = _load_config()
    value = config.get(key)
    if value not in (None, ""):
        return str(value)
    return os.environ.get(env_name, "") or default


def _provider_value(
    provider: str,
    key: str,
    env_names: list[str],
    default: str = "",
    *,
    legacy_key: str | None = None,
) -> str:
    provider_config = _provider_config(provider)
    value = provider_config.get(key)
    if value not in (None, ""):
        return str(value)

    config = _load_config()
    if legacy_key and provider == "apimart":
        legacy_value = config.get(legacy_key)
        if legacy_value not in (None, ""):
            return str(legacy_value)

    for env_name in env_names:
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value
    return default


def _provider_bool(provider: str, key: str, env_names: list[str], default: bool) -> bool:
    provider_config = _provider_config(provider)
    if key in provider_config:
        return _as_bool(provider_config.get(key), default)
    for env_name in env_names:
        if env_name in os.environ:
            return _as_bool(os.environ.get(env_name), default)
    return default


def _configured_provider_names() -> list[str]:
    primary = _top_config_value("provider_primary", "IMAGE_PROVIDER_PRIMARY", DEFAULT_PROVIDER_PRIMARY).strip()
    fallback = _top_config_value("provider_fallback", "IMAGE_PROVIDER_FALLBACK", DEFAULT_PROVIDER_FALLBACK).strip()
    names: list[str] = []
    for name in (primary, fallback):
        normalized = name.lower()
        if normalized and normalized != "none" and normalized not in names:
            names.append(normalized)
    return names or [DEFAULT_PROVIDER_PRIMARY]


def _build_session() -> requests.Session:
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=sorted(TRANSIENT_STATUS_CODES),
        allowed_methods=["POST", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _response_request_id(response: requests.Response | None) -> str:
    if response is None:
        return ""
    for header in ("x-request-id", "x-tt-logid", "x-volc-request-id", "x-ark-request-id", "request-id"):
        value = response.headers.get(header)
        if value:
            return value
    return ""


def _extract_error(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("type") or ""
        message = error.get("message") or ""
        return str(code), str(message)
    if isinstance(error, str):
        return "", error
    code = payload.get("code")
    message = payload.get("message") or payload.get("msg") or ""
    return (str(code) if code not in (None, "") else "", str(message) if message else "")


def _is_transient_code(code: str) -> bool:
    if not code:
        return False
    try:
        return int(code) in TRANSIENT_STATUS_CODES
    except ValueError:
        lowered = code.lower()
        return any(token in lowered for token in ("timeout", "temporar", "unavailable", "rate", "limit", "internal"))


def _fallback_allowed_for_status(status_code: int) -> bool:
    if status_code in NON_FALLBACK_STATUS_CODES:
        return False
    return status_code in TRANSIENT_STATUS_CODES or status_code >= 500


def _http_error(
    provider: str,
    model: str,
    response: requests.Response,
    started: float,
) -> ImageProviderError:
    request_id = _response_request_id(response)
    try:
        payload: Any = response.json()
    except ValueError:
        payload = {}
    payload_code, payload_message = _extract_error(payload)
    error_code = payload_code or str(response.status_code)
    message = payload_message or response.text[:300] or response.reason
    return ImageProviderError(
        f"{provider} HTTP {response.status_code}: {message}",
        provider=provider,
        model=model,
        error_code=error_code,
        request_id=request_id,
        latency_ms=_elapsed_ms(started),
        fallback_allowed=_fallback_allowed_for_status(response.status_code),
    )


def _network_error(provider: str, model: str, exc: Exception, started: float) -> ImageProviderError:
    return ImageProviderError(
        f"{provider} 网络错误：{exc}",
        provider=provider,
        model=model,
        error_code=exc.__class__.__name__,
        latency_ms=_elapsed_ms(started),
        fallback_allowed=True,
    )


def _write_b64_image(b64_json: str, output_path: Path) -> None:
    payload = b64_json
    if "," in payload and payload.strip().lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(f"Base64 图片数据解码失败：{exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def _download(url: str, output_path: Path) -> None:
    timeout = _env_int("POSTER_IMAGE_DOWNLOAD_TIMEOUT_SECONDS", 300)
    retries = _env_int("POSTER_IMAGE_DOWNLOAD_RETRIES", 3)
    delay = _env_int("POSTER_IMAGE_DOWNLOAD_RETRY_DELAY_SECONDS", 2)
    last_error: Exception | None = None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            logger.info("开始下载生成图片：attempt=%d/%d output=%s", attempt + 1, retries, output_path)
            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
            logger.info("图片下载完成：output=%s", output_path)
            return
        except Exception as exc:  # noqa: BLE001 - keep the original download failure.
            last_error = exc
            logger.warning("图片下载第 %d 次重试失败：%s", attempt + 1, exc)
            time.sleep(delay)
    raise RuntimeError(f"图片下载失败：{last_error}")


def image_to_data_url(path: Path) -> str:
    data = path.read_bytes()
    ext = path.suffix.lower().lstrip(".") or "png"
    if ext == "jpg":
        ext = "jpeg"
    return f"data:image/{ext};base64,{base64.b64encode(data).decode('ascii')}"


def _extract_task_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            task_id = item.get("task_id") or item.get("id")
            return str(task_id) if task_id else None
    if isinstance(data, dict):
        task_id = data.get("task_id") or data.get("id")
        return str(task_id) if task_id else None
    return None


def _extract_direct_url(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            url = item.get("url") or item.get("image_url")
            if isinstance(url, list):
                return str(url[0]) if url else None
            return str(url) if url else None
    return None


def _extract_completed_url(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    images = result.get("images")
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if not isinstance(first, dict):
        return None
    url = first.get("url") or first.get("image_url")
    if isinstance(url, list):
        return str(url[0]) if url else None
    return str(url) if url else None


class ImageProvider:
    name = "provider"

    def __init__(self) -> None:
        self.session = _build_session()

    @property
    def api_key(self) -> str:
        raise NotImplementedError

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    @property
    def model(self) -> str:
        raise NotImplementedError

    def generate(
        self,
        *,
        prompt: str,
        reference_images: list[Path],
        output_path: Path,
        size: str,
        resolution: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def health_check(self) -> dict[str, Any]:
        started = time.perf_counter()
        result: dict[str, Any] = {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "reachable": False,
            "http_status": None,
            "latency_ms": None,
            "status": "unknown",
            "error": "",
        }
        try:
            response = self.session.get(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                timeout=_env_int("POSTER_PROVIDER_HEALTH_TIMEOUT_SECONDS", 8),
            )
            result["reachable"] = True
            result["http_status"] = response.status_code
            result["status"] = "ok" if self.api_key else "missing_api_key"
        except requests.exceptions.RequestException as exc:
            result["status"] = "unreachable"
            result["error"] = str(exc)
        result["latency_ms"] = _elapsed_ms(started)
        return result


class VolcengineSeedreamProvider(ImageProvider):
    name = "volcengine_seedream"

    @property
    def api_key(self) -> str:
        return _provider_value(self.name, "api_key", ["ARK_API_KEY"])

    @property
    def base_url(self) -> str:
        return _provider_value(self.name, "base_url", ["ARK_BASE_URL"], DEFAULT_ARK_BASE_URL).rstrip("/")

    @property
    def model(self) -> str:
        return _provider_value(self.name, "model", ["ARK_IMAGE_MODEL"], DEFAULT_ARK_MODEL)

    @property
    def response_format(self) -> str:
        return _provider_value(self.name, "response_format", ["ARK_RESPONSE_FORMAT"], DEFAULT_ARK_RESPONSE_FORMAT)

    @property
    def output_format(self) -> str:
        return _provider_value(self.name, "output_format", ["ARK_OUTPUT_FORMAT"], DEFAULT_ARK_OUTPUT_FORMAT)

    @property
    def watermark(self) -> bool:
        return _provider_bool(self.name, "watermark", ["ARK_WATERMARK"], False)

    def _request_size(self, size: str, resolution: str) -> str:
        configured = _provider_value(self.name, "size", ["ARK_IMAGE_SIZE"])
        if configured:
            return configured
        raw_size = (size or "").strip()
        if raw_size.upper() in {"1K", "2K", "3K", "4K"}:
            return raw_size.upper()
        if "x" in raw_size.lower():
            return raw_size.lower()
        ratio_to_2k = {
            "1:1": "2048x2048",
            "4:3": "2304x1728",
            "3:4": "1728x2304",
            "16:9": "2848x1600",
            "9:16": "1600x2848",
            "3:2": "2496x1664",
            "2:3": "1664x2496",
            "21:9": "3136x1344",
        }
        if raw_size in ratio_to_2k:
            return ratio_to_2k[raw_size]
        if (resolution or "").upper() in {"1K", "2K", "3K", "4K"}:
            return (resolution or "").upper()
        return DEFAULT_ARK_SIZE

    @staticmethod
    def _supports_output_format(model: str) -> bool:
        normalized = model.lower()
        return "5-0" in normalized or "5.0" in normalized

    def generate(
        self,
        *,
        prompt: str,
        reference_images: list[Path],
        output_path: Path,
        size: str,
        resolution: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        model_id = model or self.model
        if not self.api_key:
            raise ImageProviderError(
                "缺少火山方舟 API Key：请配置 ARK_API_KEY 或 config/fog_config.yaml 的 lx_haibao.image_api.volcengine_seedream.api_key。",
                provider=self.name,
                model=model_id,
                error_code="missing_api_key",
                fallback_allowed=True,
            )

        image_urls = [image_to_data_url(path) for path in reference_images if path.is_file()]
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "size": self._request_size(size, resolution),
            "response_format": self.response_format,
            "stream": False,
            "watermark": self.watermark,
            "sequential_image_generation": "disabled",
        }
        if self._supports_output_format(model_id) and self.output_format:
            payload["output_format"] = self.output_format
        if image_urls:
            payload["image"] = image_urls[0] if len(image_urls) == 1 else image_urls

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        started = time.perf_counter()
        response: requests.Response | None = None
        try:
            response = self.session.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=_env_int("POSTER_IMAGE_REQUEST_TIMEOUT_SECONDS", 1200),
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RetryError) as exc:
            raise _network_error(self.name, model_id, exc, started) from exc
        except requests.exceptions.RequestException as exc:
            raise _network_error(self.name, model_id, exc, started) from exc

        if response.status_code >= 400:
            raise _http_error(self.name, model_id, response, started)

        request_id = _response_request_id(response)
        try:
            response_payload = response.json()
        except ValueError as exc:
            raise ImageProviderError(
                f"{self.name} 返回非 JSON 响应：{exc}",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code="invalid_json",
                fallback_allowed=False,
            ) from exc

        payload_error_code, payload_error_message = _extract_error(response_payload)
        if payload_error_code or payload_error_message:
            raise ImageProviderError(
                f"{self.name} 返回错误：{payload_error_message or payload_error_code}",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code=payload_error_code or "provider_error",
                fallback_allowed=_is_transient_code(payload_error_code),
            )

        data = response_payload.get("data")
        if not isinstance(data, list) or not data:
            raise ImageProviderError(
                f"{self.name} 未返回 data[0] 图片信息。",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code="missing_data",
                fallback_allowed=False,
            )

        item = next((entry for entry in data if isinstance(entry, dict) and (entry.get("url") or entry.get("b64_json"))), None)
        if not isinstance(item, dict):
            item_error = next((entry.get("error") for entry in data if isinstance(entry, dict) and entry.get("error")), None)
            code, message = _extract_error({"error": item_error})
            raise ImageProviderError(
                f"{self.name} 未返回图片 URL 或 b64_json：{message or code or data}",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code=code or "missing_image",
                fallback_allowed=_is_transient_code(code),
            )

        remote_url = str(item.get("url") or "")
        b64_json = str(item.get("b64_json") or "")
        try:
            if remote_url:
                _download(remote_url, output_path)
            elif b64_json:
                _write_b64_image(b64_json, output_path)
        except RuntimeError as exc:
            raise ImageProviderError(
                f"{self.name} 图片保存失败：{exc}",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code="image_save_failed",
                fallback_allowed=True,
            ) from exc

        return {
            "status": "success",
            "filepath": str(output_path),
            "url": remote_url or None,
            "task_id": None,
            "provider": self.name,
            "model": model_id,
            "request_id": request_id,
            "latency_ms": _elapsed_ms(started),
            "error_code": "",
            "reference_image_count": len(image_urls),
            "request": {
                "size": payload["size"],
                "response_format": payload["response_format"],
                "stream": payload["stream"],
                "watermark": payload["watermark"],
                "output_format": payload.get("output_format"),
                "model": model_id,
            },
        }


class APIMartProvider(ImageProvider):
    name = "apimart"

    @property
    def api_key(self) -> str:
        return _provider_value(
            self.name,
            "api_key",
            ["APIMART_API_KEY", "OPENAI_API_KEY"],
            legacy_key="api_key",
        )

    @property
    def base_url(self) -> str:
        return _provider_value(
            self.name,
            "base_url",
            ["APIMART_BASE_URL", "POSTER_IMAGE_API_BASE_URL"],
            DEFAULT_APIMART_BASE_URL,
            legacy_key="base_url",
        ).rstrip("/")

    @property
    def model(self) -> str:
        return _provider_value(
            self.name,
            "model",
            ["APIMART_IMAGE_MODEL", "POSTER_IMAGE_MODEL"],
            DEFAULT_APIMART_MODEL,
            legacy_key="model",
        )

    def _provider_payload_error(self, payload: dict[str, Any], model_id: str, started: float) -> ImageProviderError:
        code, message = _extract_error(payload)
        if not code:
            code = "provider_error"
        return ImageProviderError(
            f"{self.name} 返回错误：{message or code}",
            provider=self.name,
            model=model_id,
            error_code=code,
            latency_ms=_elapsed_ms(started),
            fallback_allowed=_is_transient_code(code),
        )

    def generate(
        self,
        *,
        prompt: str,
        reference_images: list[Path],
        output_path: Path,
        size: str,
        resolution: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        model_id = model or self.model
        if not self.api_key:
            raise ImageProviderError(
                "缺少 APIMart API Key：请配置 APIMART_API_KEY、OPENAI_API_KEY 或 config/fog_config.yaml 的 lx_haibao.image_api.apimart.api_key。",
                provider=self.name,
                model=model_id,
                error_code="missing_api_key",
                fallback_allowed=True,
            )

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "resolution": resolution,
        }
        image_urls = [image_to_data_url(path) for path in reference_images if path.is_file()]
        if image_urls:
            payload["image_urls"] = image_urls

        request_timeout = _env_int("POSTER_IMAGE_REQUEST_TIMEOUT_SECONDS", 30)
        logger.info(
            "提交 APIMart 生图请求：model=%s size=%s resolution=%s reference_images=%d timeout=%ss",
            payload["model"],
            size,
            resolution,
            len(image_urls),
            request_timeout,
        )

        started = time.perf_counter()
        response: requests.Response | None = None
        try:
            response = self.session.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=request_timeout,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RetryError) as exc:
            raise _network_error(self.name, model_id, exc, started) from exc
        except requests.exceptions.RequestException as exc:
            raise _network_error(self.name, model_id, exc, started) from exc

        if response.status_code >= 400:
            raise _http_error(self.name, model_id, response, started)

        request_id = _response_request_id(response)
        try:
            submit_payload = response.json()
        except ValueError as exc:
            raise ImageProviderError(
                f"{self.name} 返回非 JSON 响应：{exc}",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code="invalid_json",
                fallback_allowed=False,
            ) from exc

        if submit_payload.get("code", 200) != 200:
            raise self._provider_payload_error(submit_payload, model_id, started)

        direct_url = _extract_direct_url(submit_payload)
        if direct_url:
            try:
                _download(direct_url, output_path)
            except RuntimeError as exc:
                raise ImageProviderError(
                    f"{self.name} 图片下载失败：{exc}",
                    provider=self.name,
                    model=model_id,
                    request_id=request_id,
                    latency_ms=_elapsed_ms(started),
                    error_code="image_download_failed",
                    fallback_allowed=True,
                ) from exc
            return {
                "status": "success",
                "filepath": str(output_path),
                "url": direct_url,
                "task_id": None,
                "provider": self.name,
                "model": model_id,
                "request_id": request_id,
                "latency_ms": _elapsed_ms(started),
                "error_code": "",
                "reference_image_count": len(image_urls),
                "request": {"size": size, "resolution": resolution, "model": model_id},
            }

        task_id = _extract_task_id(submit_payload)
        if not task_id:
            raise ImageProviderError(
                f"{self.name} 未返回 task_id 或图片 URL。",
                provider=self.name,
                model=model_id,
                request_id=request_id,
                latency_ms=_elapsed_ms(started),
                error_code="missing_task_id",
                fallback_allowed=False,
            )

        initial_delay = _env_int("POSTER_IMAGE_TASK_INITIAL_DELAY_SECONDS", 12)
        attempts = _env_int("POSTER_IMAGE_TASK_POLL_ATTEMPTS", 24)
        interval = _env_int("POSTER_IMAGE_TASK_POLL_INTERVAL_SECONDS", 5)
        logger.info(
            "APIMart 任务已提交：task_id=%s initial_delay=%ss poll_attempts=%d poll_interval=%ss",
            task_id,
            initial_delay,
            attempts,
            interval,
        )
        time.sleep(initial_delay)
        for attempt in range(1, attempts + 1):
            try:
                query = self.session.get(f"{self.base_url}/tasks/{task_id}", headers=headers, timeout=request_timeout)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RetryError) as exc:
                raise _network_error(self.name, model_id, exc, started) from exc
            except requests.exceptions.RequestException as exc:
                raise _network_error(self.name, model_id, exc, started) from exc
            if query.status_code >= 400:
                raise _http_error(self.name, model_id, query, started)
            task_request_id = _response_request_id(query) or request_id
            try:
                task_payload = query.json()
            except ValueError as exc:
                raise ImageProviderError(
                    f"{self.name} 任务轮询返回非 JSON 响应：{exc}",
                    provider=self.name,
                    model=model_id,
                    request_id=task_request_id,
                    latency_ms=_elapsed_ms(started),
                    error_code="invalid_task_json",
                    fallback_allowed=False,
                ) from exc
            if task_payload.get("code", 200) != 200:
                logger.info(
                    "APIMart 任务轮询：task_id=%s poll=%d/%d code=%s，继续等待",
                    task_id,
                    attempt,
                    attempts,
                    task_payload.get("code"),
                )
                time.sleep(interval)
                continue
            data = task_payload.get("data") if isinstance(task_payload.get("data"), dict) else {}
            status = str(data.get("status") or "").lower()
            logger.info("APIMart 任务轮询：task_id=%s poll=%d/%d status=%s", task_id, attempt, attempts, status or "unknown")
            if status == "completed":
                image_url = _extract_completed_url(task_payload)
                if not image_url:
                    raise ImageProviderError(
                        f"{self.name} 任务完成，但响应中没有图片 URL。",
                        provider=self.name,
                        model=model_id,
                        request_id=task_request_id,
                        latency_ms=_elapsed_ms(started),
                        error_code="missing_completed_url",
                        fallback_allowed=False,
                    )
                try:
                    _download(image_url, output_path)
                except RuntimeError as exc:
                    raise ImageProviderError(
                        f"{self.name} 图片下载失败：{exc}",
                        provider=self.name,
                        model=model_id,
                        request_id=task_request_id,
                        latency_ms=_elapsed_ms(started),
                        error_code="image_download_failed",
                        fallback_allowed=True,
                    ) from exc
                return {
                    "status": "success",
                    "filepath": str(output_path),
                    "url": image_url,
                    "task_id": task_id,
                    "provider": self.name,
                    "model": model_id,
                    "request_id": task_request_id,
                    "latency_ms": _elapsed_ms(started),
                    "error_code": "",
                    "reference_image_count": len(image_urls),
                    "request": {"size": size, "resolution": resolution, "model": model_id},
                }
            if status == "failed":
                error = data.get("error") or task_payload
                logger.error("APIMart 任务失败：task_id=%s error=%s", task_id, error)
                raise ImageProviderError(
                    json.dumps(error, ensure_ascii=False),
                    provider=self.name,
                    model=model_id,
                    request_id=task_request_id,
                    latency_ms=_elapsed_ms(started),
                    error_code="task_failed",
                    fallback_allowed=False,
                )
            time.sleep(interval)

        raise ImageProviderError(
            f"{self.name} 任务超时：{task_id}",
            provider=self.name,
            model=model_id,
            request_id=request_id,
            latency_ms=_elapsed_ms(started),
            error_code="task_timeout",
            fallback_allowed=True,
        )


def _build_provider(name: str) -> ImageProvider:
    if name == "volcengine_seedream":
        return VolcengineSeedreamProvider()
    if name == "apimart":
        return APIMartProvider()
    raise ImageProviderError(
        f"未知图片 provider：{name}",
        provider=name,
        error_code="unknown_provider",
        fallback_allowed=False,
    )


def _log_provider_event(
    *,
    provider: str,
    model: str,
    request_id: str = "",
    latency_ms: int | None = None,
    error_code: str = "",
    fallback_used: bool = False,
    level: int = logging.INFO,
) -> None:
    fields = {
        "provider": provider,
        "model": model,
        "request_id": request_id,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "fallback_used": fallback_used,
    }
    logger.log(level, "image_provider_event %s", json.dumps(fields, ensure_ascii=False, sort_keys=True))


def _format_provider_errors(errors: list[ImageProviderError]) -> str:
    parts = []
    for error in errors:
        parts.append(
            f"{error.provider}(model={error.model or '-'}, code={error.error_code or '-'}, "
            f"request_id={error.request_id or '-'}): {error}"
        )
    return "图片生成失败：" + "；".join(parts)


def require_api_key() -> str:
    missing: list[str] = []
    for provider_name in _configured_provider_names():
        provider = _build_provider(provider_name)
        if provider.api_key:
            return provider.api_key
        missing.append(provider_name)
    raise RuntimeError(
        "缺少图片生成 API Key："
        "火山方舟请配置 ARK_API_KEY 或 config/fog_config.yaml 的 lx_haibao.image_api.volcengine_seedream.api_key；"
        "APIMart 请配置 APIMART_API_KEY/OPENAI_API_KEY 或 lx_haibao.image_api.apimart.api_key。"
    )


def generate_image(
    *,
    prompt: str,
    reference_images: list[Path],
    output_path: Path,
    size: str = "9:16",
    resolution: str = "2k",
    model: str | None = None,
) -> dict[str, Any]:
    provider_names = _configured_provider_names()
    errors: list[ImageProviderError] = []
    fallback_used = False

    for index, provider_name in enumerate(provider_names):
        provider = _build_provider(provider_name)
        try:
            result = provider.generate(
                prompt=prompt,
                reference_images=reference_images,
                output_path=output_path,
                size=size,
                resolution=resolution,
                model=model,
            )
            result["fallback_used"] = fallback_used
            if fallback_used:
                result["fallback_from"] = [error.provider for error in errors]
            _log_provider_event(
                provider=str(result.get("provider") or provider.name),
                model=str(result.get("model") or provider.model),
                request_id=str(result.get("request_id") or ""),
                latency_ms=int(result["latency_ms"]) if result.get("latency_ms") is not None else None,
                error_code=str(result.get("error_code") or ""),
                fallback_used=fallback_used,
                level=logging.INFO,
            )
            return result
        except ImageProviderError as exc:
            errors.append(exc)
            _log_provider_event(
                provider=exc.provider,
                model=exc.model,
                request_id=exc.request_id,
                latency_ms=exc.latency_ms,
                error_code=exc.error_code,
                fallback_used=fallback_used,
                level=logging.WARNING,
            )
            has_next = index + 1 < len(provider_names)
            if exc.fallback_allowed and has_next:
                fallback_used = True
                logger.warning(
                    "图片 provider 失败，准备 fallback：provider=%s error_code=%s next_provider=%s",
                    exc.provider,
                    exc.error_code,
                    provider_names[index + 1],
                )
                continue
            raise RuntimeError(_format_provider_errors(errors)) from exc

    raise RuntimeError(_format_provider_errors(errors))


def generateImage(prompt: str, options: dict[str, Any]) -> dict[str, Any]:
    return generate_image(
        prompt=prompt,
        reference_images=[Path(path) for path in options.get("reference_images", [])],
        output_path=Path(options["output_path"]),
        size=str(options.get("size", "9:16")),
        resolution=str(options.get("resolution", "2k")),
        model=options.get("model"),
    )


def check_providers() -> dict[str, Any]:
    provider_order = _configured_provider_names()
    providers: list[dict[str, Any]] = []
    for provider_name in ("volcengine_seedream", "apimart"):
        try:
            provider = _build_provider(provider_name)
            item = provider.health_check()
        except ImageProviderError as exc:
            item = {
                "provider": provider_name,
                "model": exc.model,
                "base_url": "",
                "api_key_configured": False,
                "reachable": False,
                "http_status": None,
                "latency_ms": exc.latency_ms,
                "status": "error",
                "error": str(exc),
            }
        item["enabled_order"] = provider_order.index(provider_name) + 1 if provider_name in provider_order else None
        providers.append(item)

    usable = [item for item in providers if item["enabled_order"] and item["api_key_configured"] and item["reachable"]]
    return {
        "ok": bool(usable),
        "primary": provider_order[0] if provider_order else None,
        "fallback": provider_order[1] if len(provider_order) > 1 else None,
        "providers": providers,
        "note": "该检查只做配置和 base_url 连通性检查，不调用图片生成接口，不产生生图费用。",
    }
