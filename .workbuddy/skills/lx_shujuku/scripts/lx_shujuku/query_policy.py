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
LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)


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
) -> str:
    """
    返回可安全执行的只读 SQL。

    约束：
    - 只允许 SELECT/SHOW/DESCRIBE/DESC/EXPLAIN
    - 禁止多语句和注释
    - 禁止写库/DDL/权限类关键字
    - 可选限制表名必须存在于 schema 白名单
    - SELECT 未写 LIMIT 时自动追加默认 LIMIT
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

    if command == "select":
        return _ensure_limit(normalized, default_limit, max_limit)
    return normalized


def _strip_trailing_semicolon(sql: str) -> str:
    value = sql.strip()
    while value.endswith(";"):
        value = value[:-1].strip()
    return value


def _ensure_limit(sql: str, default_limit: int, max_limit: int) -> str:
    limits = [int(match.group(1)) for match in LIMIT_RE.finditer(sql)]
    if limits:
        for limit in limits:
            validate_limit(limit, max_limit)
        return sql
    validate_limit(default_limit, max_limit)
    return f"{sql} LIMIT {default_limit}"


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
