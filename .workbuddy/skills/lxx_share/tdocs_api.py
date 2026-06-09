#!/usr/bin/env python3
"""
腾讯文档 Open API V3 封装模块。

提供 addSheet + updateRange 批量操作能力，
替代 MCP 的 set_range_value（≤133 格即错乱）。

认证：
  - client_id / client_secret：应用级凭证，来自 config/fog_config.yaml
  - access_token / refresh_token / open_id：用户级凭证，每人通过 OAuth 获得
  - Token 自动续期，无需人工干预

使用方式：
  首次授权:  python tdocs_api.py --oauth
  作为模块:  from tdocs_api import add_sheet, write_range, TdocsClient

参考文档：
  https://docs.qq.com/open/document/app/openapi/v3/sheet/batchupdate/update.html
"""

import json
import time
import sys
import hashlib
import webbrowser
import urllib.parse
from pathlib import Path
from typing import Optional, Union

import requests
import yaml

from lxx_share.fog_config import fog_config_path


# ========================================
# 常量
# ========================================

# lxx_share 位于 skills/ 目录下。腾讯文档配置统一归属 config/fog_config.yaml。
FOG_CONFIG_PATH = fog_config_path(Path(__file__))


def _default_config_path() -> Path:
    return FOG_CONFIG_PATH


CONFIG_PATH = _default_config_path()

OAUTH_AUTHORIZE_URL = "https://docs.qq.com/oauth/v2/authorize"
OAUTH_TOKEN_URL = "https://docs.qq.com/oauth/v2/token"
API_BASE = "https://docs.qq.com/openapi/spreadsheet/v3/files"
DRIVE_API_BASE = "https://docs.qq.com/openapi/drive/v2"

DEFAULT_REDIRECT_URI = "https://docs.qq.com"


# ========================================
# 配置管理
# ========================================

def _load_config(config_path: Optional[Path] = None) -> dict:
    """加载腾讯文档配置，从 config/fog_config.yaml 转换为兼容结构。"""
    path = Path(config_path or CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {path}\n"
            f"请在 config/fog_config.yaml 的 lx_txwendang.tdocs 段填写腾讯文档配置。"
        )
    return _tdocs_view_from_fog(_load_yaml_path(path))


def _load_yaml_path(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _save_config(config: dict, config_path: Optional[Path] = None):
    """保存腾讯文档配置；fog_config.yaml 会写回 lx_txwendang.tdocs 段。"""
    path = Path(config_path or CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    fog_config = _load_yaml_path(path) if path.exists() else {}
    txwendang = fog_config.setdefault("lx_txwendang", {})
    if not isinstance(txwendang, dict):
        txwendang = {}
        fog_config["lx_txwendang"] = txwendang
    tdocs = txwendang.setdefault("tdocs", {})
    if not isinstance(tdocs, dict):
        tdocs = {}
        txwendang["tdocs"] = tdocs
    tdocs["root_folder_id"] = config.get("腾讯文档根文件夹", "")
    tdocs["openapi"] = dict(config.get("腾讯文档OpenAPI", {}) or {})
    _save_yaml_path(path, fog_config)


def _save_yaml_path(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _tdocs_view_from_fog(fog_config: dict) -> dict:
    txwendang = fog_config.get("lx_txwendang", {})
    if not isinstance(txwendang, dict):
        txwendang = {}
    tdocs = txwendang.get("tdocs", {})
    if not isinstance(tdocs, dict):
        tdocs = {}
    openapi = tdocs.get("openapi", {})
    if not isinstance(openapi, dict):
        openapi = {}
    return {
        "腾讯文档根文件夹": tdocs.get("root_folder_id", ""),
        "腾讯文档OpenAPI": {
            "client_id": openapi.get("client_id", ""),
            "client_secret": openapi.get("client_secret", ""),
            "access_token": openapi.get("access_token", ""),
            "refresh_token": openapi.get("refresh_token", ""),
            "open_id": openapi.get("open_id", ""),
        },
    }


def _get_oauth_config(config_path: Optional[Path] = None) -> dict:
    """从腾讯文档配置中提取 OpenAPI 认证信息。"""
    config = _load_config(config_path)
    oauth = config.get("腾讯文档OpenAPI", {})
    if not isinstance(oauth, dict):
        oauth = {}
    return {
        "client_id": oauth.get("client_id", ""),
        "client_secret": oauth.get("client_secret", ""),
        "access_token": oauth.get("access_token", ""),
        "refresh_token": oauth.get("refresh_token", ""),
        "open_id": oauth.get("open_id", ""),
    }


def _save_oauth_config(creds: dict, config_path: Optional[Path] = None):
    """写入 OpenAPI 认证信息。"""
    config = _load_config(config_path)
    config["腾讯文档OpenAPI"] = {
        "client_id": creds.get("client_id", ""),
        "client_secret": creds.get("client_secret", ""),
        "access_token": creds.get("access_token", ""),
        "refresh_token": creds.get("refresh_token", ""),
        "open_id": creds.get("open_id", ""),
    }
    _save_config(config, config_path)


# ========================================
# OAuth 授权流程（首次使用）
# ========================================

def oauth_flow(interactive: bool = True, config_path: Optional[Path] = None):
    """
    交互式 OAuth 授权向导。

    步骤：
      1. 让用户填写 client_id / client_secret（如已填写则跳过）
      2. 在浏览器中打开授权页面
      3. 用户授权后，浏览器跳转到 docs.qq.com，URL 中含有 code
      4. 用户复制跳转后的完整 URL，粘贴回终端
      5. 用 code 换取 access_token + refresh_token + open_id
      6. 保存到 config/fog_config.yaml
    """
    print("\n" + "=" * 60)
    print("腾讯文档 Open API - OAuth 授权向导")
    print("=" * 60)

    path = Path(config_path or CONFIG_PATH)
    creds = _get_oauth_config(path)

    # 步骤 1: 检查 client_id / client_secret
    if not creds["client_id"] or not creds["client_secret"]:
        print("\n[1/4] 请先获取应用凭证（Client ID / Client Secret）：")
        print("  1. 打开 https://docs.qq.com/open/developers/")
        print("  2. 注册成为开发者")
        print("  3. 创建第三方应用，等待审核通过")
        print("  4. 在应用详情页获取 Client ID 和 Client Secret")

        if interactive:
            client_id = input("\n请输入 Client ID: ").strip()
            client_secret = input("请输入 Client Secret: ").strip()
        else:
            print("\n非交互模式，请在 config/fog_config.yaml 中手动填写 client_id 和 client_secret")
            return None

        if not client_id or not client_secret:
            print("❌ Client ID 和 Client Secret 不能为空")
            return None

        creds["client_id"] = client_id
        creds["client_secret"] = client_secret
        _save_oauth_config(creds, path)
        print("✅ 应用凭证已保存")

    # 步骤 2: 构建授权 URL 并在浏览器中打开
    state = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
    params = {
        "client_id": creds["client_id"],
        "redirect_uri": DEFAULT_REDIRECT_URI,
        "response_type": "code",
        "scope": "scope.sheet.editable",
        "state": state,
    }
    auth_url = f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    print("\n[2/4] 正在打开授权页面...")
    print(f"  如果浏览器未自动打开，请手动访问：")
    print(f"\n  {auth_url}\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # 步骤 3: 获取授权码
    print("[3/4] 授权完成后，浏览器会跳转到 docs.qq.com")
    print("  请复制跳转后的完整 URL，粘贴到下方：")
    print("  （URL 示例: https://docs.qq.com/?code=XXXX&state=XXXX）")

    if interactive:
        redirect_url = input("\n请粘贴重定向 URL: ").strip()
    else:
        print("  非交互模式，跳过")
        return None

    if not redirect_url:
        print("❌ 未输入 URL，授权取消")
        return None

    # 从 URL 中提取 code
    parsed = urllib.parse.urlparse(redirect_url)
    query = urllib.parse.parse_qs(parsed.query)
    code = query.get("code", [None])[0]

    if not code:
        print("❌ 未能从 URL 中提取授权码 (code)")
        print(f"  解析结果: {parsed.query}")
        return None

    print(f"  ✅ 已提取授权码: {code[:20]}...")

    # 步骤 4: 用 code 换取 token
    print("\n[4/4] 正在换取 Access Token...")
    token_params = {
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "redirect_uri": DEFAULT_REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
    }

    try:
        resp = requests.get(OAUTH_TOKEN_URL, params=token_params, timeout=15)
        if resp.status_code == 401:
            print("❌ 授权码无效或已过期（有效期仅 5 分钟），请重新授权")
            return None
        resp.raise_for_status()
        token_data = resp.json()

        creds["access_token"] = token_data.get("access_token", "")
        creds["refresh_token"] = token_data.get("refresh_token", "")
        creds["open_id"] = token_data.get("user_id", "")
        creds["expires_in"] = token_data.get("expires_in", 2592000)
        creds["_token_obtained_at"] = int(time.time())

        _save_oauth_config(creds, path)

        print(f"  ✅ 授权成功！")
        print(f"  Access Token: {creds['access_token'][:20]}...")
        print(f"  Open ID: {creds['open_id']}")
        print(f"  有效期: {creds['expires_in']} 秒（约 {creds['expires_in'] // 86400} 天）")
        print(f"\n配置已保存到: {path}")

        return creds

    except requests.RequestException as e:
        print(f"❌ 请求失败: {e}")
        return None


# ========================================
# API 客户端
# ========================================

class TdocsClient:
    """腾讯文档 Open API V3 客户端。

    自动管理 Token 续期。多用户共享同一实例时注意线程安全。
    """

    def __init__(self, config_path: Optional[Union[Path, str]] = None):
        self.config_path = Path(config_path).expanduser() if config_path else CONFIG_PATH
        creds = _get_oauth_config(self.config_path)
        self.client_id = creds["client_id"]
        self.client_secret = creds["client_secret"]
        self.access_token = creds["access_token"]
        self.refresh_token = creds.get("refresh_token", "")
        self.open_id = creds["open_id"]

    def _check_creds(self):
        """检查凭证是否已配置。

        简化授权模式下只需 client_id + access_token + open_id。
        client_secret 和 refresh_token 为标准 OAuth 所需，简化模式不需要。
        """
        if not self.client_id:
            raise RuntimeError(
                "未配置腾讯文档 Open API 凭证 (client_id)。\n"
            "请在 config/fog_config.yaml 的 lx_txwendang.tdocs.openapi 段填写 client_id、access_token、open_id。\n"
                "获取方式：访问腾讯文档开放平台获取应用ID和Token。"
            )
        if not self.access_token or not self.open_id:
            raise RuntimeError(
                "未配置 access_token 或 open_id。\n"
                "请在 config/fog_config.yaml 的 lx_txwendang.tdocs.openapi 段填写所有必填字段。"
            )

    def _refresh_access_token(self):
        """使用 refresh_token 刷新 access_token。

        简化授权模式（无 refresh_token）下无法自动续期，直接报错提示用户重新授权。
        """
        if not self.refresh_token:
            raise RuntimeError(
                "Token 已过期且无 refresh_token（当前为简化授权模式）。\n"
                "请重新获取 access_token 并更新 config/fog_config.yaml 中的 lx_txwendang.tdocs.openapi.access_token。"
            )

        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }

        try:
            resp = requests.get(OAUTH_TOKEN_URL, params=params, timeout=15)
            resp.raise_for_status()
            token_data = resp.json()

            self.access_token = token_data.get("access_token", "")
            new_refresh = token_data.get("refresh_token", "")
            if new_refresh:
                self.refresh_token = new_refresh

            # 持久化
            creds = _get_oauth_config(self.config_path)
            creds["access_token"] = self.access_token
            creds["refresh_token"] = self.refresh_token
            creds["_token_obtained_at"] = int(time.time())
            _save_oauth_config(creds, self.config_path)

            print("[Token] 已自动续期")

        except requests.RequestException as e:
            raise RuntimeError(f"Token 续期失败: {e}")

    def _request(self, method: str, path: str, data: Optional[dict] = None,
                 retry_on_401: bool = True) -> dict:
        """发送 API 请求，自动处理 401 续期。"""
        self._check_creds()

        url = f"{API_BASE}/{path}"
        headers = {
            "Access-Token": self.access_token,
            "Client-Id": self.client_id,
            "Open-Id": self.open_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            if method == "POST":
                resp = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "GET":
                resp = requests.get(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            # Token 过期 → 自动续期后重试一次
            if resp.status_code == 401 and retry_on_401:
                self._refresh_access_token()
                headers["Access-Token"] = self.access_token
                return self._request(method, path, data, retry_on_401=False)

            # 频率限制
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 3))
                print(f"[API] 频率限制，等待 {retry_after}s 后重试...")
                time.sleep(retry_after)
                return self._request(method, path, data, retry_on_401=False)

            resp_data = resp.json()

            # V3 API 无顶层的 code 字段，直接检查响应
            # 响应中有 "responses" 数组即表示成功
            if "responses" not in resp_data and "code" in resp_data and resp_data.get("code") != 0:
                raise RuntimeError(
                    f"API 返回错误: code={resp_data.get('code')}, "
                    f"message={resp_data.get('message', 'unknown')}"
                )

            return resp_data

        except requests.RequestException as e:
            raise RuntimeError(f"API 请求失败: {e}")

    def add_sheet(self, file_id: str, title: str,
                  row_count: int = 200, column_count: int = 20) -> str:
        """
        在已有表格中创建新 sheet。

        Args:
            file_id: 表格文档 ID
            title: sheet 名称（≤31 字符）
            row_count: 初始行数（≤10000，默认 200）
            column_count: 初始列数（≤200，默认 20）

        Returns:
            str: 新 sheet 的 sheetId

        Raises:
            RuntimeError: API 调用失败
        """
        request_body = {
            "requests": [
                {
                    "addSheetRequest": {
                        "title": title[:31],
                        "rowCount": min(row_count, 10000),
                        "columnCount": min(column_count, 200),
                    }
                }
            ]
        }

        resp = self._request("POST", f"{file_id}/batchUpdate", request_body)
        # V3 响应直接在顶层，无 data 包装
        response_data = resp.get("responses", [{}])[0]
        add_resp = response_data.get("addSheetResponse", {})
        sheet_id = add_resp.get("properties", {}).get("sheetId", "")

        if not sheet_id:
            raise RuntimeError(f"addSheet 失败: {resp}")

        return sheet_id

    def delete_sheet(self, file_id: str, sheet_id: str):
        """
        删除指定 sheet。

        Args:
            file_id: 表格文档 ID
            sheet_id: 要删除的 sheet ID
        """
        request_body = {
            "requests": [
                {"deleteSheetRequest": {"sheetId": sheet_id}}
            ]
        }
        return self._request("POST", f"{file_id}/batchUpdate", request_body)

    def get_sheet_ids(self, file_id: str) -> dict[str, str]:
        """
        获取表格中所有 sheet 的名称 → ID 映射。

        Returns:
            dict: {"0527": "abc123", "工作表1": "BB08J2", ...}
        """
        resp = self._request("GET", f"{file_id}")
        props = resp.get("properties", [])
        return {p["title"]: p["sheetId"] for p in props}

    def write_range(self, file_id: str, sheet_id: str,
                    data: list, start_row: int = 0, start_col: int = 0) -> dict:
        """
        批量写入单元格数据。

        Args:
            file_id: 表格文档 ID
            sheet_id: 目标 sheet ID
            data: 二维数组 data[row][col]，每个元素为字符串或数字
            start_row: 起始行索引（0-based）
            start_col: 起始列索引（0-based）

        Returns:
            dict: API 原始响应

        Raises:
            RuntimeError: API 调用失败或数据量超限
        """
        rows = len(data)
        cols = max(len(row) for row in data) if data else 0

        if rows > 1000:
            raise ValueError(f"行数 {rows} 超过单次上限 1000")
        if cols > 200:
            raise ValueError(f"列数 {cols} 超过单次上限 200")
        if rows * cols > 10000:
            raise ValueError(f"单元格总数 {rows * cols} 超过单次上限 10000")

        # 构造 GridData 的 rows 数组
        # CellData 格式: {"cellValue": {"text": "..."}} 或 {"cellValue": {"number": 123}}
        grid_rows = []
        for data_row in data:
            cell_values = []
            for cell in data_row:
                if cell is None:
                    cell_values.append({"cellValue": {"text": ""}})
                elif isinstance(cell, (int, float)):
                    cell_values.append({"cellValue": {"number": cell}})
                else:
                    cell_values.append({"cellValue": {"text": str(cell)}})
            grid_rows.append({"values": cell_values})

        request_body = {
            "requests": [
                {
                    "updateRangeRequest": {
                        "sheetId": sheet_id,
                        "gridData": {
                            "startRow": start_row,
                            "startColumn": start_col,
                            "rows": grid_rows,
                        }
                    }
                }
            ]
        }

        return self._request("POST", f"{file_id}/batchUpdate", request_body)

    def write_range_auto(self, file_id: str, sheet_id: str,
                         data: list, start_row: int = 0, start_col: int = 0):
        """
        批量写入单元格数据（自动分批，突破 1000 行限制）。

        将大数据拆分成多个 updateRangeRequest，每批最多 1000 行。
        """
        batch_size = 1000  # 单次最大行数
        total_rows = len(data)
        written = 0

        for batch_start in range(0, total_rows, batch_size):
            batch_end = min(batch_start + batch_size, total_rows)
            batch_data = data[batch_start:batch_end]

            self.write_range(
                file_id, sheet_id,
                batch_data,
                start_row=start_row + batch_start,
                start_col=start_col,
            )

            written += len(batch_data)
            if total_rows > batch_size:
                print(f"  写入进度: {written}/{total_rows} 行")

        return written

    def batch_merge_cells(self, file_id: str, sheet_id: str,
                          merges: list[dict]) -> dict:
        """
        批量合并单元格。

        Args:
            file_id: 表格文档 ID
            sheet_id: 目标 sheet ID
            merges: 合并区域列表，每个元素为:
                    {"start_row": 0, "end_row": 1, "start_col": 0, "end_col": 1}

        Returns:
            dict: API 响应
        """
        requests = []
        for m in merges:
            requests.append({
                "mergeCellsRequest": {
                    "sheetId": sheet_id,
                    "range": {
                        "startRowIndex": m["start_row"],
                        "endRowIndex": m["end_row"] + 1,  # V3: end is exclusive
                        "startColumnIndex": m["start_col"],
                        "endColumnIndex": m["end_col"] + 1,
                    },
                    "mergeType": "MERGE_ALL",
                }
            })

        request_body = {"requests": requests}
        return self._request("POST", f"{file_id}/batchUpdate", request_body)

    def _drive_request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        """发送 Drive API 请求（用于文件创建/管理等操作）。

        Drive V2 使用 form-urlencoded 而非 JSON，返回格式也不同于 V3。
        """
        self._check_creds()

        url = f"{DRIVE_API_BASE}/{path}"
        headers = {
            "Access-Token": self.access_token,
            "Client-Id": self.client_id,
            "Open-Id": self.open_id,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            if method == "POST":
                resp = requests.post(url, headers=headers, data=data, timeout=30)
            elif method == "GET":
                resp = requests.get(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            if resp.status_code == 401:
                self._refresh_access_token()
                headers["Access-Token"] = self.access_token
                return self._drive_request(method, path, data)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 3))
                print(f"[API] 频率限制，等待 {retry_after}s 后重试...")
                time.sleep(retry_after)
                return self._drive_request(method, path, data)

            result = resp.json()

            # V2 响应格式: {"ret": 0, "msg": "Succeed", "data": {...}}
            if result.get("ret") != 0:
                raise RuntimeError(
                    f"Drive API 返回错误: ret={result.get('ret')}, "
                    f"msg={result.get('msg', 'unknown')}"
                )

            return result

        except requests.RequestException as e:
            raise RuntimeError(f"Drive API 请求失败: {e}")

    def create_spreadsheet(self, name: str, folder_id: str = "") -> dict:
        """
        在指定文件夹中创建新的在线表格（Drive V2 API）。

        Args:
            name: 表格文件名
            folder_id: 目标文件夹 ID，空字符串表示根目录

        Returns:
            dict: {"file_id": "...", "url": "...", "name": "..."}

        Raises:
            RuntimeError: API 调用失败
        """
        # V2 使用 form-encoded 参数
        request_data = {
            "title": name,
            "type": "sheet",
        }
        if folder_id:
            request_data["folderID"] = folder_id

        resp = self._drive_request("POST", "files", request_data)

        data = resp.get("data", {})
        file_id = data.get("ID", "")
        url = data.get("url", "")

        if not file_id:
            raise RuntimeError(f"创建表格失败: {resp}")

        return {
            "file_id": file_id,
            "url": url,
            "name": name,
            "folder_id": folder_id,
        }


# ========================================
# 便捷函数（模块级 API，兼容旧代码风格）
# ========================================

_client: Optional[TdocsClient] = None


def _get_client() -> TdocsClient:
    """获取或创建全局客户端实例。"""
    global _client
    if _client is None:
        _client = TdocsClient()
    return _client


def add_sheet(file_id: str, title: str,
              row_count: int = 200, column_count: int = 20) -> str:
    """在已有表格中创建新 sheet（模块级便捷函数）。"""
    return _get_client().add_sheet(file_id, title, row_count, column_count)


def write_range(file_id: str, sheet_id: str,
                data: list, start_row: int = 0, start_col: int = 0) -> dict:
    """批量写入单元格数据（模块级便捷函数）。"""
    return _get_client().write_range(file_id, sheet_id, data, start_row, start_col)


def write_range_auto(file_id: str, sheet_id: str,
                     data: list, start_row: int = 0, start_col: int = 0):
    """批量写入单元格数据，自动分批（模块级便捷函数）。"""
    return _get_client().write_range_auto(file_id, sheet_id, data, start_row, start_col)


def create_spreadsheet(name: str, folder_id: str = "") -> dict:
    """在指定文件夹中创建新的在线表格（模块级便捷函数）。"""
    return _get_client().create_spreadsheet(name, folder_id)


def delete_sheet(file_id: str, sheet_id: str):
    """删除指定 sheet（模块级便捷函数）。"""
    return _get_client().delete_sheet(file_id, sheet_id)


def get_sheet_ids(file_id: str) -> dict[str, str]:
    """获取表格中所有 sheet 的名称→ID 映射（模块级便捷函数）。"""
    return _get_client().get_sheet_ids(file_id)


# ========================================
# 简化版设置向导（同事接入用，无需 OAuth code 交换）
# ========================================

def setup_simple(interactive: bool = True, config_path: Optional[Path] = None):
    """
    简化版设置向导。

    适用于腾讯文档开放平台「应用详情页」直接生成的 Token（JWT 格式）。
    不需要 client_secret、不需要 OAuth code 交换流程。

    同事接入流程：
      1. 打开腾讯文档开放平台 → 应用详情页
      2. 用自己账号生成 access_token 和 open_id
      3. 粘贴到此处
    """
    print("\n" + "=" * 60)
    print("腾讯文档 Open API - 简化设置向导")
    print("=" * 60)

    path = Path(config_path or CONFIG_PATH)
    creds = _get_oauth_config(path)

    # 检查 client_id
    if not creds["client_id"]:
        print("\n⚠️  client_id 未配置")
        print("  请联系团队管理员获取应用 ID，或直接编辑 config/fog_config.yaml")
        if interactive:
            client_id = input("\n请输入 client_id（回车跳过）: ").strip()
            if client_id:
                creds["client_id"] = client_id
        if not creds["client_id"]:
            print("跳过，请手动编辑 config/fog_config.yaml 中的 client_id")
            return None
    else:
        print(f"\nclient_id: {creds['client_id']}")

    print("\n--- 请获取你的 Token ---")
    print("  1. 打开 腾讯文档开放平台 → 你的应用详情页")
    print("  2. 用你自己的腾讯文档账号扫码/登录")
    print("  3. 页面会显示 access_token 和 open_id（或 user_id）")
    print("  4. 将它们粘贴到下方")

    if interactive:
        access_token = input("\naccess_token: ").strip()
        open_id = input("open_id (或 user_id): ").strip()
    else:
        print("\n非交互模式，跳过")
        return None

    if not access_token or not open_id:
        print("❌ access_token 和 open_id 不能为空")
        return None

    creds["access_token"] = access_token
    creds["open_id"] = open_id

    _save_oauth_config(creds, path)

    print(f"\n✅ 设置完成！")
    print(f"  access_token: {access_token[:20]}...")
    print(f"  open_id: {open_id}")
    print(f"\n配置已保存到: {path}")

    # 快速验证
    print("\n正在验证 Token 有效性...")
    try:
        client = TdocsClient(config_path=path)
        client._check_creds()
        # 尝试一个简单的 API 调用验证
        headers = {
            "Access-Token": access_token,
            "Client-Id": creds["client_id"],
            "Open-Id": open_id,
            "Content-Type": "application/json",
        }
        # 用文件夹列表接口做轻量验证
        root_folder = _load_config(path).get("腾讯文档根文件夹", "")
        if root_folder:
            resp = requests.get(
                f"https://docs.qq.com/openapi/drive/v2/folders/{root_folder}/children",
                headers=headers, timeout=10
            )
            if resp.status_code == 200:
                print("✅ Token 验证通过！可以正常调用 API")
            else:
                print(f"⚠️  Token 验证返回 {resp.status_code}，请检查是否正确")
        else:
            print("  跳过验证（未配置根文件夹）")
    except Exception as e:
        print(f"⚠️  验证失败: {e}")
        print("  Token 可能无效，请重新获取")

    return creds


# ========================================
# CLI 入口
# ========================================

def main():
    """CLI 入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="腾讯文档 Open API V3 工具")
    parser.add_argument("--config", help="指定配置路径；默认读取 config/fog_config.yaml")
    parser.add_argument("--setup", action="store_true",
                        help="简化设置向导（同事接入推荐，2分钟完成）")
    parser.add_argument("--oauth", action="store_true",
                        help="标准 OAuth 授权向导（需 client_secret）")
    parser.add_argument("--verify", action="store_true",
                        help="验证当前 Token 是否有效")
    args = parser.parse_args()
    config_path = Path(args.config).expanduser() if args.config else None

    if args.setup:
        result = setup_simple(interactive=True, config_path=config_path)
        if result:
            print("\n✅ 设置完成")
        else:
            print("\n❌ 设置失败或被取消")
            sys.exit(1)

    elif args.oauth:
        result = oauth_flow(interactive=True, config_path=config_path)
        if result:
            print("\n✅ OAuth 授权完成")
        else:
            print("\n❌ OAuth 授权失败或取消")
            sys.exit(1)

    elif args.verify:
        try:
            client = TdocsClient(config_path=config_path)
            client._check_creds()
            print("✅ Token 配置完整")
            creds = _get_oauth_config(config_path)
            print(f"  client_id: {creds['client_id']}")
            print(f"  access_token: {creds['access_token'][:20]}...")
            print(f"  open_id: {creds['open_id']}")
        except Exception as e:
            print(f"❌ {e}")
            sys.exit(1)

    else:
        print("腾讯文档 Open API V3 工具\n")
        print("同事首次接入(推荐): python tdocs_api.py --setup")
        print("标准 OAuth 授权:     python tdocs_api.py --oauth")
        print("验证 Token:          python tdocs_api.py --verify")
        print("\n作为模块使用：")
        print("  from tdocs_api import add_sheet, write_range, TdocsClient")
        print("  client = TdocsClient()")
        print("  sheet_id = client.add_sheet('file_id', '我的Sheet')")
        print("  client.write_range('file_id', sheet_id, [['A1', 'B1'], ['A2', 'B2']])")


if __name__ == "__main__":
    main()
