"""
lx_shujuku 公司数据库客户端

提供对 dataReporting 平台数据库的完整访问能力：
- 自动登录鉴权（Token 缓存/过期重登）
- 只读 SQL 查询执行
- 表结构浏览
- 常用业务查询模板

认证流程：
1. POST /dataReporting/user/login → 获取 token
2. 后续请求 Header: token: {token}
3. 返回 401 时自动重新登录
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

from .operator_brand import build_mabiao_mapping, normalize_operator_brand_rows
from .query_policy import ensure_readonly_sql, validate_limit
from .schema import SchemaCatalog

logger = logging.getLogger(__name__)


class DataReportingClient:
    """dataReporting 平台数据库客户端"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[int] = None,
        default_limit: Optional[int] = None,
        max_limit: Optional[int] = None,
    ) -> None:
        """
        初始化客户端。

        优先级：直接传参 > config/fog_config.yaml
        """
        # 解析配置文件
        if config_path is None:
            config_path = self._resolve_config_path()
        try:
            self._config = self._load_config(config_path) if config_path else {}
        except FileNotFoundError:
            logger.warning(f"配置文件未找到: {config_path}，请确认是否已创建")
            self._config = {}

        self.base_url = base_url or self._config.get("base_url", "http://datareporting.sfczhushou.com")
        self.username = username or self._config.get("username", "")
        self.password = password or self._config.get("password", "")
        self.max_limit = _to_positive_int(
            max_limit if max_limit is not None else self._config.get("max_limit", 1000),
            "max_limit",
        )
        self.timeout = _to_positive_int(
            timeout if timeout is not None else self._config.get("timeout", 30),
            "timeout",
        )
        self.default_limit = validate_limit(
            default_limit if default_limit is not None else self._config.get("default_limit", 100),
            self.max_limit,
        )
        self.schema = SchemaCatalog.from_skill_root(self._skill_dir())

        if not self.username or not self.password:
            raise RuntimeError(
                "未配置用户名或密码。请编辑 config/fog_config.yaml 的 lx_shujuku.api 段，"
                "或通过 DataReportingClient(username=..., password=...) 传参。"
            )

        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._token_lifetime: float = 3600.0  # 假设 token 有效期 1 小时

    # ---- 配置加载 ----

    @staticmethod
    def _skill_dir() -> Path:
        """返回 Skill 根目录。"""
        return Path(__file__).resolve().parents[2]

    def _resolve_config_path(self) -> Optional[str]:
        """解析配置路径，使用项目根目录 config/fog_config.yaml。"""
        fog_config_path = self._project_root() / "config" / "fog_config.yaml"
        return str(fog_config_path)

    @staticmethod
    def _project_root() -> Path:
        """返回 FOG 项目根目录。"""
        for candidate in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
            if (candidate / "config" / "fog_config.yaml").exists():
                return candidate
            if (candidate / ".workbuddy").is_dir() and (candidate / "config").is_dir():
                return candidate
        return DataReportingClient._skill_dir().parents[1]

    @staticmethod
    def _load_config(path: str) -> dict:
        """加载 YAML 配置文件（简易解析，无第三方依赖）"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        data = DataReportingClient._parse_simple_yaml(content)
        if "lx_shujuku" in data and isinstance(data["lx_shujuku"], dict):
            section = data["lx_shujuku"]
            api = section.get("api") if isinstance(section.get("api"), dict) else {}
            query = section.get("query") if isinstance(section.get("query"), dict) else {}
            result = {
                "base_url": api.get("base_url", "http://datareporting.sfczhushou.com"),
                "username": api.get("username", ""),
                "password": api.get("password", ""),
            }
            if "timeout" in section:
                result["timeout"] = section["timeout"]
            if "default_limit" in query:
                result["default_limit"] = query["default_limit"]
            if "max_limit" in query:
                result["max_limit"] = query["max_limit"]
            return result
        return data

    @staticmethod
    def _parse_simple_yaml(content: str) -> dict[str, Any]:
        """
        简易 YAML 解析器（仅支持 FOG 配置常用映射格式，不依赖 PyYAML）。
        """
        result: dict[str, Any] = {}
        stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]

        for line in content.split("\n"):
            content_line = _strip_yaml_line_comment(line)
            stripped = content_line.strip()
            # 跳过注释和空行
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("- ") or ":" not in stripped:
                continue

            indent = len(content_line) - len(content_line.lstrip(" "))
            key, value = _split_yaml_key_value(stripped)
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if value == "":
                child: dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child))
            else:
                parent[key] = _parse_yaml_scalar(value)

        # 扁平化处理：如果 api 存在，提取其子属性到顶层
        if "api" in result and isinstance(result["api"], dict):
            api_config = result["api"]
            result["base_url"] = api_config.get("base_url", result.get("base_url"))
            result["username"] = api_config.get("username", result.get("username"))
            result["password"] = api_config.get("password", result.get("password"))

        return result

    # ---- 鉴权 ----

    def login(self) -> str:
        """
        执行登录，获取 Token。

        Returns:
            token 字符串

        Raises:
            RuntimeError: 登录失败时抛出
        """
        url = f"{self.base_url}/dataReporting/user/login"
        payload = json.dumps({
            "username": self.username,
            "password": self.password,
        }).encode("utf-8")

        try:
            resp = self._request(url, payload, use_auth=False)
            data = json.loads(resp)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"登录响应解析失败: {e}") from e

        if data.get("code") != 200:
            raise RuntimeError(f"登录失败: {data.get('message', '未知错误')}")

        token = data.get("data", {}).get("token", "")
        if not token:
            raise RuntimeError("登录成功但未返回 token")

        self._token = token
        self._token_expiry = time.time() + self._token_lifetime
        logger.info("登录成功，Token 已缓存")
        return token

    def ensure_token(self) -> str:
        """确保 token 有效，必要时重新登录"""
        if self._token and time.time() < self._token_expiry:
            return self._token
        return self.login()

    # ---- HTTP 请求 ----

    def _request(
        self, url: str, payload: bytes, use_auth: bool = True
    ) -> bytes:
        """
        发送 HTTP POST 请求。

        Args:
            url: 请求地址
            payload: JSON 请求体（bytes）
            use_auth: 是否携带 token

        Returns:
            响应体 bytes

        Raises:
            RuntimeError: 网络错误或 HTTP 错误时抛出
        """
        headers = {"Content-Type": "application/json"}
        if use_auth:
            headers["token"] = self.ensure_token()

        req = Request(url, data=payload, headers=headers, method="POST")

        # 使用无代理 opener 绕过本地 HTTP 代理（服务器为内网直连）
        opener = build_opener(ProxyHandler({}))

        try:
            with opener.open(req, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as e:
            if e.code == 401 and use_auth:
                # Token 过期，重新登录后重试一次
                logger.warning("Token 过期，重新登录...")
                self._token = None
                self._token_expiry = 0.0
                headers["token"] = self.ensure_token()
                req = Request(url, data=payload, headers=headers, method="POST")
                with opener.open(req, timeout=self.timeout) as response:
                    return response.read()
            raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"网络连接失败: {e.reason}") from e

    # ---- SQL 安全工具 ----

    @staticmethod
    def _esc(value: str) -> str:
        """
        转义 SQL 字符串参数中的特殊字符，防止基础 SQL 注入。

        注意：这是简易转义，生产环境应使用参数化查询。
        本工具仅允许 SELECT 查询，风险可控。
        """
        return value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

    # ---- SQL 查询 ----

    def prepare_sql(self, sql: str, enforce_table_whitelist: bool = True) -> str:
        """执行前标准化并校验 SQL。"""
        allowed_tables = self.schema.table_names if enforce_table_whitelist else None
        return ensure_readonly_sql(
            sql,
            default_limit=self.default_limit,
            max_limit=self.max_limit,
            allowed_tables=allowed_tables,
        )

    def execute(
        self,
        sql: str,
        auto_retry: bool = True,
        enforce_table_whitelist: bool = True,
    ) -> list[dict[str, Any]]:
        """
        执行只读 SQL 查询并返回结果。

        Args:
            sql: SQL 语句，只允许只读语句
            auto_retry: Token 过期时是否自动重试

        Returns:
            查询结果列表，每行为一个 dict

        Raises:
            RuntimeError: 查询失败时抛出
        """
        safe_sql = self.prepare_sql(sql, enforce_table_whitelist=enforce_table_whitelist)
        return self._execute_prepared_sql(safe_sql)

    def execute_audited(
        self,
        sql: str,
        question: str = "",
        metric: str = "",
        enforce_table_whitelist: bool = True,
    ) -> dict[str, Any]:
        """执行查询并返回可用于文档生成的结构化证据包。"""
        tz = timezone(timedelta(hours=8))
        started_at = datetime.now(tz)
        started_monotonic = time.monotonic()
        safe_sql = self.prepare_sql(sql, enforce_table_whitelist=enforce_table_whitelist)
        rows = self._execute_prepared_sql(safe_sql)
        duration_ms = round((time.monotonic() - started_monotonic) * 1000, 3)

        return {
            "type": "lx_shujuku.query_run",
            "version": 1,
            "executed_at": started_at.isoformat(),
            "duration_ms": duration_ms,
            "database": "dataReporting",
            "base_url": self.base_url,
            "question": question,
            "metric": metric,
            "sql": sql,
            "safe_sql": safe_sql,
            "row_count": len(rows),
            "rows": rows,
            "warnings": self._query_warnings(safe_sql),
        }

    def _execute_prepared_sql(self, safe_sql: str) -> list[dict[str, Any]]:
        """执行已经通过只读策略校验的 SQL。"""
        url = f"{self.base_url}/dataReporting/sql-query/execute"
        payload = json.dumps({"sql": safe_sql}).encode("utf-8")

        resp_text = self._request(url, payload).decode("utf-8")
        try:
            data = json.loads(resp_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"查询响应解析失败: {e}\n原始响应: {resp_text[:500]}") from e

        if data.get("code") != 200:
            raise RuntimeError(f"查询失败: {data.get('message', '未知错误')}")

        return data.get("data", [])

    @staticmethod
    def _query_warnings(sql: str) -> list[str]:
        warnings: list[str] = []
        compact = " ".join(sql.lower().split())
        if compact.startswith("select *"):
            warnings.append("查询包含 SELECT *；生成文档时建议只取必要字段")
        return warnings

    def execute_one(self, sql: str) -> Optional[dict[str, Any]]:
        """执行 SQL 并返回单行结果（无结果时返回 None）"""
        rows = self.execute(sql)
        return rows[0] if rows else None

    # ---- 表结构浏览 ----

    def list_tables(self) -> list[dict[str, str]]:
        """
        列出数据库中所有表。

        Returns:
            [{"name": "表名", "comment": "注释"}, ...]
        """
        rows = self.execute("SHOW TABLES")
        result = []
        for row in rows:
            # MySQL: {"Tables_in_datareporting": "xxx", "TABLE_COMMENT": "xxx"}
            table_name = row.get("Tables_in_datareporting", "")
            comment = row.get("TABLE_COMMENT", "")
            result.append({"name": table_name, "comment": comment})
        return result

    def describe(self, table_name: str) -> list[dict[str, Any]]:
        """
        查看表结构。

        Returns:
            [{"field": "字段名", "type": "类型", "null": "YES/NO",
              "key": "PRI/MUL/...", "default": "默认值", "comment": "注释"}, ...]
        """
        safe_table = self.schema.validate_table_name(table_name)
        rows = self.execute(f"DESCRIBE {safe_table}")
        return self._normalize_describe_rows(rows)

    def describe_online(self, table_name: str) -> list[dict[str, Any]]:
        """查看线上表结构，不要求表已存在于本地 schema 白名单。"""
        from .query_policy import validate_identifier

        safe_table = validate_identifier(table_name)
        rows = self.execute(
            f"DESCRIBE {safe_table}",
            enforce_table_whitelist=False,
        )
        return self._normalize_describe_rows(rows)

    @staticmethod
    def _normalize_describe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "field": r.get("Field", ""),
                "type": r.get("Type", ""),
                "null": r.get("Null", ""),
                "key": r.get("Key", ""),
                "default": r.get("Default"),
                "comment": r.get("COLUMN_COMMENT", ""),
            }
            for r in rows
        ]

    def count(self, table_name: str, where: str = "") -> int:
        """查询表记录数"""
        safe_table = self.schema.validate_table_name(table_name)
        sql = f"SELECT COUNT(*) AS cnt FROM {safe_table}"
        if where:
            sql += f" WHERE {where}"
        row = self.execute_one(sql)
        return int(row["cnt"]) if row else 0

    # ---- 常用业务查询模板 ----

    def query_by_brand_date(
        self, table: str, brand: str, date: str, limit: int = 50
    ) -> list[dict]:
        """按品牌和日期查询"""
        safe_table = self.schema.validate_table_name(table)
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM {safe_table} "
            f"WHERE business_name = '{self._esc(brand)}' "
            f"AND DATE(sale_start_time) = '{self._esc(date)}' "
            f"LIMIT {safe_limit}"
        )
        return self.execute(sql)

    def query_by_city_date(
        self, table: str, city: str, date: str, limit: int = 50
    ) -> list[dict]:
        """按城市和日期查询（适用于宏鹄系列表）"""
        safe_table = self.schema.validate_table_name(table)
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM {safe_table} "
            f"WHERE city_name = '{self._esc(city)}' "
            f"AND date_day = '{self._esc(date)}' "
            f"LIMIT {safe_limit}"
        )
        return self.execute(sql)

    def query_activity_by_operator(
        self, operator: str, status: Optional[int] = None, limit: int = 50
    ) -> list[dict]:
        """按运营主体查询活动"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = f"SELECT * FROM activity_data WHERE operator_entity = '{self._esc(operator)}'"
        if status is not None:
            sql += f" AND status = {int(status)}"
        sql += f" LIMIT {safe_limit}"
        return self.execute(sql)

    def query_coupon_by_product(
        self, product_name: str, limit: int = 50
    ) -> list[dict]:
        """按卡券商品名称查询"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM honghu_coupon_marketing_data "
            f"WHERE product_name LIKE '%{self._esc(product_name)}%' "
            f"LIMIT {safe_limit}"
        )
        return self.execute(sql)

    def query_capacity_by_brand_date(
        self, brand: str, date: str, city: str = "", limit: int = 50
    ) -> list[dict]:
        """按品牌和日期查询运力数据"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM honghu_capacity_data "
            f"WHERE brand_name = '{self._esc(brand)}' AND date_day = '{self._esc(date)}'"
        )
        if city:
            sql += f" AND city_name = '{self._esc(city)}'"
        sql += f" LIMIT {safe_limit}"
        return self.execute(sql)

    def query_order_by_brand_date(
        self, brand: str, date: str, limit: int = 50
    ) -> list[dict]:
        """按品牌和日期查询订单数据"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM honghu_order_data "
            f"WHERE brand_name = '{self._esc(brand)}' AND date_day = '{self._esc(date)}' "
            f"LIMIT {safe_limit}"
        )
        return self.execute(sql)

    def query_time_split_by_hour(
        self, brand: str, date: str, city: str = "", limit: int = 50
    ) -> list[dict]:
        """按品牌和日期查询分时明细"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM honghu_time_split_data "
            f"WHERE brand_name = '{self._esc(brand)}' AND date_day = '{self._esc(date)}'"
        )
        if city:
            sql += f" AND city_name = '{self._esc(city)}'"
        sql += f" ORDER BY hour LIMIT {safe_limit}"
        return self.execute(sql)

    def query_driver_real_time(
        self, tenant_name: str, date: str, limit: int = 20
    ) -> list[dict]:
        """按租户和日期查询运力实时数据"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM driver_real_time_data "
            f"WHERE tenant_name = '{self._esc(tenant_name)}' "
            f"AND datae_column_bc7a384cd7_day_real = '{self._esc(date)}' "
            f"LIMIT {safe_limit}"
        )
        return self.execute(sql)

    def query_order_real_time(
        self, tenant_name: str, date: str, limit: int = 20
    ) -> list[dict]:
        """按租户和日期查询订单实时数据"""
        safe_limit = validate_limit(limit, self.max_limit)
        sql = (
            f"SELECT * FROM order_real_time_data "
            f"WHERE tenant_name = '{self._esc(tenant_name)}' "
            f"AND datae_column_b4276e28f8_day_real = '{self._esc(date)}' "
            f"LIMIT {safe_limit}"
        )
        return self.execute(sql)

    def query_operator_brands(self, operator: str) -> list[dict]:
        """兼容旧方法：查询运营主体下的所有品牌-城市组合。"""
        return self.get_operator_brands(operator=operator)

    def get_operator_brands(
        self,
        operator: str = "",
        brand: str = "",
        city: str = "",
        limit: int = 1000,
    ) -> list[dict[str, str]]:
        """查询 operator_brand，并返回稳定的中英文键。"""
        safe_limit = validate_limit(limit, self.max_limit)
        conditions = []
        if operator:
            conditions.append(f"operator_entity = '{self._esc(operator)}'")
        if brand:
            conditions.append(f"brand_name = '{self._esc(brand)}'")
        if city:
            conditions.append(f"city_name = '{self._esc(city)}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            "SELECT operator_entity, brand_name, city_name, contact_person "
            f"FROM operator_brand WHERE {where} "
            f"ORDER BY operator_entity, brand_name, city_name LIMIT {safe_limit}"
        )
        return normalize_operator_brand_rows(self.execute(sql))

    def load_mabiao_mapping(self) -> dict[str, Any]:
        """返回兼容本地 Excel 码表的映射结构。"""
        return build_mabiao_mapping(self.get_operator_brands(limit=self.max_limit))

    def query_tr_config(self, brand: str = "", city: str = "") -> list[dict]:
        """查询品牌城市 TR 配置"""
        conditions = []
        if brand:
            conditions.append(f"brand_name = '{self._esc(brand)}'")
        if city:
            conditions.append(f"city_name = '{self._esc(city)}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        return self.execute(f"SELECT * FROM brand_city_tr_config WHERE {where}")

    # ---- 工具方法 ----

    def health_check(self) -> dict[str, Any]:
        """健康检查：验证连接和认证"""
        try:
            tables = self.list_tables()
            operator_brand_sample = self.get_operator_brands(limit=5)
            return {
                "status": "ok",
                "base_url": self.base_url,
                "table_count": len(tables),
                "tables": [t["name"] for t in tables],
                "operator_brand_sample_count": len(operator_brand_sample),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def export_schema(self) -> dict[str, Any]:
        """
        导出全量数据库 Schema。

        Returns:
            {
                "generated_at": "ISO时间",
                "tables": [
                    {
                        "name": "表名",
                        "comment": "注释",
                        "columns": [...]
                    },
                    ...
                ]
            }
        """
        from datetime import datetime, timezone, timedelta

        tz = timezone(timedelta(hours=8))
        result = {
            "generated_at": datetime.now(tz).isoformat(),
            "database": "dataReporting",
            "tables": [],
        }

        tables = self.list_tables()
        for t in tables:
            columns = self.describe_online(t["name"])
            result["tables"].append({
                "name": t["name"],
                "comment": t["comment"],
                "column_count": len(columns),
                "columns": columns,
            })

        return result


# ---- 便捷工厂函数 ----

def create_client(config_path: Optional[str] = None) -> DataReportingClient:
    """
    创建客户端实例（自动从 config/fog_config.yaml 加载配置）。

    Args:
        config_path: 配置文件路径，为 None 时自动查找

    Returns:
        DataReportingClient 实例
    """
    return DataReportingClient(config_path=config_path)


def _split_yaml_key_value(line: str) -> tuple[str, str]:
    parts = line.split(":", 1)
    key = parts[0].strip()
    value = _strip_inline_comment(parts[1].strip()) if len(parts) > 1 else ""
    return key, value


def _parse_yaml_scalar(value: str) -> Any:
    cleaned = _strip_inline_comment(value).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1]
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    if cleaned.lower() in {"true", "false"}:
        return cleaned.lower() == "true"
    return cleaned


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False

    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#":
            return value[:index].rstrip()

    return value.strip()


def _strip_yaml_line_comment(value: str) -> str:
    quote: str | None = None
    escaped = False

    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#":
            return value[:index].rstrip()

    return value.rstrip()


def _to_positive_int(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} 必须是正整数: {value}") from exc
    if result <= 0:
        raise RuntimeError(f"{name} 必须是正整数: {value}")
    return result
