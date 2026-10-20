"""SQL 只读策略与基础校验。"""

from __future__ import annotations

import re


ALLOWED_COMMANDS = {"select", "show", "describe", "desc", "explain"}
FORBIDDEN_KEYWORDS = {
    "analyze",
    "alter",
    "call",
    "create",
    "delete",
    "drop",
    "dumpfile",
    "grant",
    "handler",
    "into",
    "insert",
    "kill",
    "load",
    "lock",
    "optimize",
    "outfile",
    "repair",
    "rename",
    "replace",
    "revoke",
    "set",
    "truncate",
    "unlock",
    "update",
}

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LIMIT_RE = re.compile(r"\blimit\s+(\d+)(?:\s+offset\s+(\d+))?\b", re.IGNORECASE)
ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


def validate_identifier(name: str, allowed: set[str] | None = None) -> str:
    """校验表名/字段名这类简单标识符。"""
    value = name.strip()
    if not IDENTIFIER_RE.fullmatch(value):
        raise RuntimeError(f"非法表名或标识符: {name}")
    if allowed is not None and value not in allowed:
        raise RuntimeError(f"表不在 schema 白名单中: {value}")
    return value


def validate_limit(limit: int, max_limit: int) -> int:
    """校验 LIMIT 数值。"""
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"非法 LIMIT: {limit}") from exc
    if value <= 0:
        raise RuntimeError("LIMIT 必须大于 0")
    if value > max_limit:
        raise RuntimeError(f"LIMIT 不能超过 {max_limit}")
    return value


def ensure_readonly_sql(
    sql: str,
    default_limit: int,
    max_limit: int,
    allowed_tables: set[str] | None = None,
    append_default_limit: bool = True,
) -> str:
    """
    返回可安全执行的只读 SQL。

    约束：
    - 只允许 SELECT/SHOW/DESCRIBE/DESC/EXPLAIN
    - 禁止多语句和注释
    - 禁止写库/DDL/权限类关键字
    - 可选限制表名必须存在于 schema 白名单
    - 默认给未写顶层 LIMIT 的 SELECT 追加限制
    """
    normalized = _strip_trailing_semicolon(sql)
    masked = _mask_string_literals(normalized).lower()

    if ";" in masked:
        raise RuntimeError("禁止执行多条 SQL 语句")
    if "--" in masked or "/*" in masked or "#" in masked:
        raise RuntimeError("SQL 中不允许包含注释")
    if "`" in normalized:
        raise RuntimeError("SQL 中不允许使用反引号标识符，请使用 schema 白名单中的简单表名")

    match = re.match(r"\s*([A-Za-z]+)\b", masked)
    if not match:
        raise RuntimeError("SQL 为空或无法识别")
    command = match.group(1)
    if command not in ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(ALLOWED_COMMANDS))
        raise RuntimeError(f"只允许只读 SQL: {allowed}")

    forbidden = sorted(
        word for word in FORBIDDEN_KEYWORDS
        if re.search(rf"\b{re.escape(word)}\b", masked)
    )
    if forbidden:
        raise RuntimeError(f"SQL 包含禁止关键字: {', '.join(forbidden)}")

    _validate_table_references(masked, command, allowed_tables)

    if command == "select" and append_default_limit:
        return _ensure_limit(normalized, default_limit, max_limit)
    if command == "select":
        limit = analyze_query_shape(normalized)["top_level_limit"]
        if limit is not None:
            validate_limit(limit, max_limit)
    return normalized


def _strip_trailing_semicolon(sql: str) -> str:
    value = sql.strip()
    while value.endswith(";"):
        value = value[:-1].strip()
    return value


def _ensure_limit(sql: str, default_limit: int, max_limit: int) -> str:
    limit = analyze_query_shape(sql)["top_level_limit"]
    if limit is not None:
        validate_limit(limit, max_limit)
        return sql
    validate_limit(default_limit, max_limit)
    return f"{sql} LIMIT {default_limit}"


def analyze_query_shape(sql: str) -> dict[str, int | bool | None]:
    """分析最外层 SELECT 的限制与排序，不受字符串或子查询干扰。"""
    normalized = _strip_trailing_semicolon(sql)
    masked = _mask_string_literals(normalized)
    top_level = _mask_nested_parentheses(masked)

    if re.search(r"\blimit\s+\d+\s*,", top_level, re.IGNORECASE):
        raise RuntimeError("不支持 LIMIT offset,count；请使用 LIMIT count OFFSET offset")

    match = LIMIT_RE.search(top_level)
    return {
        "top_level_limit": int(match.group(1)) if match else None,
        "top_level_offset": int(match.group(2)) if match and match.group(2) else 0,
        "has_top_level_order_by": bool(ORDER_BY_RE.search(top_level)),
    }


def top_level_order_columns(sql: str) -> list[str]:
    """解析精确分页允许的简单顶层 ORDER BY 字段。"""
    normalized = _strip_trailing_semicolon(sql)
    top_level = _mask_nested_parentheses(_mask_string_literals(normalized))
    match = re.search(r"\border\s+by\s+(.+?)(?:\blimit\b|$)", top_level, re.IGNORECASE)
    if not match:
        return []

    columns: list[str] = []
    for item in match.group(1).split(","):
        item_match = re.fullmatch(
            r"\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)"
            r"(?:\s+(?:asc|desc))?\s*",
            item,
            re.IGNORECASE,
        )
        if not item_match:
            raise RuntimeError(
                "完整查询的 ORDER BY 仅支持简单字段或别名；请先在 SELECT 中定义别名再排序"
            )
        columns.append(item_match.group(1))
    return columns


def _mask_nested_parentheses(sql: str) -> str:
    """保留最外层 SQL，使用空格遮蔽括号及括号内部内容。"""
    chars: list[str] = []
    depth = 0
    for char in sql:
        if char == "(":
            depth += 1
            chars.append(" ")
        elif char == ")":
            depth = max(0, depth - 1)
            chars.append(" ")
        elif depth:
            chars.append(" ")
        else:
            chars.append(char)
    return "".join(chars)


def _validate_table_references(
    masked_sql: str,
    command: str,
    allowed_tables: set[str] | None,
) -> None:
    if allowed_tables is None:
        return

    normalized_allowed = {table.lower() for table in allowed_tables}

    if command == "show":
        _validate_show_sql(masked_sql, normalized_allowed)
        return

    if command in {"describe", "desc"}:
        match = re.match(r"\s*(?:describe|desc)\s+([A-Za-z_][A-Za-z0-9_]*)\b", masked_sql)
        if not match:
            raise RuntimeError("DESCRIBE 语句缺少表名")
        _validate_known_table(match.group(1), normalized_allowed)
        return

    for table_name in _extract_table_references(masked_sql):
        _validate_known_table(table_name, normalized_allowed)


def _validate_show_sql(masked_sql: str, allowed_tables: set[str]) -> None:
    compact = " ".join(masked_sql.split())
    if compact.startswith("show tables") or compact.startswith("show full tables"):
        return

    match = re.match(
        r"show\s+(?:columns|fields)\s+(?:from|in)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        compact,
    )
    if match:
        _validate_known_table(match.group(1), allowed_tables)
        return

    raise RuntimeError("SHOW 仅允许 TABLES 或 COLUMNS/FIELDS 元数据查询")


def _extract_table_references(masked_sql: str) -> list[str]:
    references = [
        match.group(1)
        for match in re.finditer(
            r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            masked_sql,
        )
    ]

    for match in re.finditer(
        r"\bfrom\s+(.+?)(?:\bwhere\b|\bgroup\b|\border\b|\blimit\b|\bhaving\b|\bunion\b|$)",
        masked_sql,
    ):
        segment = match.group(1).strip()
        if segment.startswith("("):
            continue
        references.extend(
            comma_match.group(1)
            for comma_match in re.finditer(r",\s*([A-Za-z_][A-Za-z0-9_]*)\b", segment)
        )

    return references


def _validate_known_table(table_name: str, allowed_tables: set[str]) -> None:
    validate_identifier(table_name)
    if table_name.lower() not in allowed_tables:
        raise RuntimeError(f"表不在 schema 白名单中: {table_name}")


def _mask_string_literals(sql: str) -> str:
    """把字符串字面量替换为空格，避免关键字误判。"""
    chars: list[str] = []
    quote: str | None = None
    escaped = False

    for char in sql:
        if quote:
            if escaped:
                escaped = False
                chars.append(" ")
                continue
            if char == "\\":
                escaped = True
                chars.append(" ")
                continue
            if char == quote:
                quote = None
            chars.append(" ")
            continue

        if char in {"'", '"', "`"}:
            quote = char
            chars.append(" ")
        else:
            chars.append(char)

    return "".join(chars)


# ---- 性能门禁 ----

PERF_GATE_DEFAULTS: dict = {
    "mode": "enforce",
    "gates": {
        "require_where": True,
        "forbid_select_star": True,
        "forbid_column_function": True,
        "explain_before_join_or_agg": True,
    },
    "forbidden_column_functions": [
        "TRIM", "CAST", "CONVERT", "COLLATE", "UPPER", "LOWER",
        "YEAR", "MONTH", "DAY", "DATE", "DATE_FORMAT", "SUBSTRING",
    ],
    "explain": {
        "max_estimated_rows": 100000,
        "forbid_access_types": ["ALL"],
        "forbid_null_key": True,
    },
    "where_exempt_tables": [],
}


def load_perf_gate_config(path: str | None = None) -> dict:
    """读取性能门禁配置；文件缺失或损坏时回退到保守默认值。"""
    import json
    import os

    if path is None:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, "assets", "perf_gate_config.json")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return dict(PERF_GATE_DEFAULTS)

    merged = dict(PERF_GATE_DEFAULTS)
    merged.update(loaded)
    merged["gates"] = {**PERF_GATE_DEFAULTS["gates"], **(loaded.get("gates") or {})}
    merged["explain"] = {**PERF_GATE_DEFAULTS["explain"], **(loaded.get("explain") or {})}
    return merged


def _predicate_segment(sql: str) -> str:
    """取 FROM 之后的谓词片段：JOIN ON、WHERE、HAVING；剔除 GROUP BY 与 ORDER BY。"""
    masked = _mask_string_literals(sql)
    match = re.search(r"\bfrom\b", masked, re.IGNORECASE)
    if not match:
        return ""
    tail = masked[match.end():]
    tail = re.sub(r"\border\s+by\b.+?(?=\blimit\b|$)", " ", tail, flags=re.IGNORECASE)
    tail = re.sub(
        r"\bgroup\s+by\b.+?(?=\bhaving\b|\border\b|\blimit\b|$)",
        " ",
        tail,
        flags=re.IGNORECASE,
    )
    return tail


def check_performance_gates(sql: str, config: dict | None = None) -> list[str]:
    """静态性能门禁。返回违规说明列表，空列表表示通过。"""
    cfg = config or load_perf_gate_config()
    gates = cfg.get("gates") or {}
    violations: list[str] = []

    normalized = _strip_trailing_semicolon(sql)
    masked = _mask_string_literals(normalized).lower()
    match = re.match(r"\s*([A-Za-z]+)\b", masked)
    if not match or match.group(1) != "select":
        return violations

    exempt = {table.lower() for table in (cfg.get("where_exempt_tables") or [])}
    tables = [table.lower() for table in _extract_table_references(masked)]

    if gates.get("require_where") and not re.search(r"\bwhere\b", masked):
        if not (tables and exempt and all(table in exempt for table in tables)):
            violations.append(
                "性能门禁 1：查询缺少 WHERE 过滤。"
                "请补充日期范围，或品牌、城市等能缩小业务范围的条件。"
            )

    if gates.get("forbid_select_star"):
        if re.search(r"\bselect\s+\*", masked):
            violations.append("性能门禁 2：禁止 SELECT *。请只写出本次任务需要的列。")
        elif re.search(r"\bselect\b.*?\b[a-z_][a-z0-9_]*\s*\.\s*\*", masked):
            violations.append("性能门禁 2：禁止 SELECT 别名.*。请只写出本次任务需要的列。")

    if gates.get("forbid_column_function"):
        segment = _predicate_segment(normalized)
        upper = segment.upper()
        for func in cfg.get("forbidden_column_functions") or []:
            if re.search(rf"\b{re.escape(str(func).upper())}\s*\(", upper):
                violations.append(
                    f"性能门禁 3：WHERE/JOIN 条件中禁止对字段使用 {str(func).upper()}()，"
                    "会导致索引失效。请改用裸字段比较或半开区间范围条件。"
                )
        if re.search(r"\blike\s+['\"]%", normalized, re.IGNORECASE):
            violations.append(
                "性能门禁 3：禁止前导通配 LIKE '%x'，索引会失效。请改用前缀匹配或等值条件。"
            )

    return violations


def should_run_explain(sql: str, config: dict | None = None) -> bool:
    """含 JOIN 或 GROUP BY 的 SELECT 需要在真实执行前先取执行计划。"""
    cfg = config or load_perf_gate_config()
    if not (cfg.get("gates") or {}).get("explain_before_join_or_agg"):
        return False
    masked = _mask_string_literals(_strip_trailing_semicolon(sql)).lower()
    if not re.match(r"\s*select\b", masked):
        return False
    return bool(re.search(r"\bjoin\b", masked) or re.search(r"\bgroup\s+by\b", masked))


def evaluate_explain_plan(plan_rows: list[dict], config: dict | None = None) -> list[str]:
    """根据 EXPLAIN 结果判断是否放行。返回违规说明列表。"""
    cfg = config or load_perf_gate_config()
    explain_cfg = cfg.get("explain") or {}
    max_rows = int(explain_cfg.get("max_estimated_rows", 100000) or 0)
    forbid_types = {str(t).upper() for t in (explain_cfg.get("forbid_access_types") or [])}
    forbid_null_key = bool(explain_cfg.get("forbid_null_key", True))

    violations: list[str] = []
    for row in plan_rows or []:
        table = str(row.get("table") or "?")
        access = str(row.get("type") or "").upper()
        key = row.get("key")
        try:
            estimated = int(row.get("rows") or 0)
        except (TypeError, ValueError):
            estimated = 0
        if estimated < max_rows:
            continue
        if access in forbid_types:
            violations.append(
                f"性能门禁 4：表 {table} 执行计划为 type={access or 'NULL'}，"
                f"估算扫描 {estimated:,} 行（阈值 {max_rows:,}）。"
            )
        elif forbid_null_key and not key:
            violations.append(
                f"性能门禁 4：表 {table} 执行计划 key=NULL，"
                f"估算扫描 {estimated:,} 行（阈值 {max_rows:,}）。"
            )
    return violations
