"""Contract-first import validation helpers.

The validators in this module read project-local contracts from
``contracts/schema`` and do not query runtime mapping tables.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional


def find_project_root(start: Optional[Path] = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for parent in [current, *current.parents]:
        if (parent / "contracts" / "schema" / "contract-index.json").exists():
            return parent
    raise FileNotFoundError("未找到 contracts/schema/contract-index.json")


class ContractValidator:
    """Validate input headers and target write columns against contracts."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or find_project_root()
        self.schema_dir = self.project_root / "contracts" / "schema"
        self.index = self._load_json(self.schema_dir / "contract-index.json")
        self._source_by_target: dict[str, dict[str, Any]] = {}
        self._source_path_by_target: dict[str, str] = {}
        self._table_by_name: dict[str, dict[str, Any]] = {}
        self._table_path_by_name: dict[str, str] = {}
        self._load_contracts()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_contracts(self) -> None:
        for rel_path in self.index.get("files", []):
            path = self.project_root / rel_path
            if not path.exists():
                continue
            data = self._load_json(path)
            if data.get("contract_type") == "source_file_template":
                target = data.get("target_table")
                if target:
                    self._source_by_target[target] = data
                    self._source_path_by_target[target] = rel_path
            elif data.get("contract_type") == "physical_table_schema":
                table = data.get("table")
                if table:
                    self._table_by_name[table] = data
                    self._table_path_by_name[table] = rel_path

    def source_contract(self, target_table: str) -> dict[str, Any]:
        try:
            return self._source_by_target[target_table]
        except KeyError as exc:
            raise KeyError(f"未找到目标表 {target_table} 的 source contract") from exc

    def table_contract(self, target_table: str) -> dict[str, Any]:
        try:
            return self._table_by_name[target_table]
        except KeyError as exc:
            raise KeyError(f"未找到目标表 {target_table} 的 physical table contract") from exc

    def _header_versions(self, contract: dict[str, Any]) -> list[dict[str, Any]]:
        versions: list[dict[str, Any]] = []
        for item in contract.get("accepted_header_versions", []) or []:
            headers = item.get("headers")
            if headers:
                versions.append({
                    "name": item.get("name", "accepted"),
                    "headers": list(headers),
                    "canonical_headers": list(item.get("canonical_headers") or headers),
                    "column_aliases": dict(item.get("column_aliases") or {}),
                    "fill_missing_headers": list(item.get("fill_missing_headers") or []),
                    "decision": item.get("decision"),
                    "decision_basis": item.get("decision_basis"),
                })
        for item in contract.get("template_versions", []) or []:
            headers = item.get("headers")
            if headers:
                versions.append({
                    "name": item.get("name", "template"),
                    "headers": list(headers),
                    "canonical_headers": list(item.get("canonical_headers") or headers),
                    "column_aliases": dict(item.get("column_aliases") or {}),
                    "fill_missing_headers": list(item.get("fill_missing_headers") or []),
                    "decision": item.get("decision"),
                    "decision_basis": item.get("decision_basis"),
                })
        if contract.get("expected_headers"):
            headers = list(contract["expected_headers"])
            versions.append({
                "name": "expected_headers",
                "headers": headers,
                "canonical_headers": headers,
                "column_aliases": {},
                "fill_missing_headers": [],
            })
        if contract.get("importer_expected_headers"):
            headers = list(contract["importer_expected_headers"])
            versions.append({
                "name": "importer_expected_headers",
                "headers": headers,
                "canonical_headers": headers,
                "column_aliases": {},
                "fill_missing_headers": [],
            })
        return versions

    @staticmethod
    def _order_mismatches(expected: list[str], actual: list[str]) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        actual_positions = {name: index for index, name in enumerate(actual)}
        for expected_index, field in enumerate(expected):
            if field not in actual_positions:
                continue
            actual_index = actual_positions[field]
            if actual_index != expected_index:
                mismatches.append({
                    "field": field,
                    "expected_position": expected_index + 1,
                    "actual_position": actual_index + 1,
                })
        return mismatches

    @staticmethod
    def _message_parts(report: dict[str, Any]) -> list[str]:
        parts = []
        if report.get("missing_fields"):
            parts.append(f"缺失字段: {report['missing_fields']}")
        if report.get("extra_fields"):
            parts.append(f"新增字段: {report['extra_fields']}")
        if report.get("order_mismatches"):
            parts.append(f"顺序差异: {len(report['order_mismatches'])} 个")
        if report.get("target_missing_columns"):
            parts.append(f"目标表缺失字段: {report['target_missing_columns']}")
        return parts

    def validate_headers(
        self,
        target_table: str,
        actual_headers: Iterable[Any],
        file_name: str = "",
        data_type: str = "",
    ) -> dict[str, Any]:
        contract = self.source_contract(target_table)
        actual = [str(header) for header in actual_headers]
        versions = self._header_versions(contract)
        if not versions:
            return {
                "pass": False,
                "target_table": target_table,
                "file": file_name,
                "data_type": data_type,
                "message": f"{target_table} 的 source contract 未定义可校验表头",
            }

        for version in versions:
            if actual == version["headers"]:
                return {
                    "pass": True,
                    "target_table": target_table,
                    "file": file_name,
                    "data_type": data_type,
                    "accepted_version": version["name"],
                    "actual_headers": actual,
                    "canonical_headers": version.get("canonical_headers", version["headers"]),
                    "column_aliases": version.get("column_aliases", {}),
                    "fill_missing_headers": version.get("fill_missing_headers", []),
                    "decision": version.get("decision"),
                    "decision_basis": version.get("decision_basis"),
                    "message": "输入表头符合契约",
                }

        expected = versions[0]["headers"]
        report = {
            "pass": False,
            "target_table": target_table,
            "file": file_name,
            "data_type": data_type,
            "source_contract": self._source_path_by_target.get(target_table),
            "source_status": contract.get("status"),
            "header_policy": contract.get("header_policy"),
            "accepted_versions": [version["name"] for version in versions],
            "expected_headers": expected,
            "actual_headers": actual,
            "missing_fields": [field for field in expected if field not in actual],
            "extra_fields": [field for field in actual if field not in expected],
            "order_mismatches": self._order_mismatches(expected, actual),
            "recommendation": "新增显式模板版本或要求上游统一模板后再导入",
        }
        detail = "；".join(self._message_parts(report)) or "表头顺序或内容不一致"
        report["message"] = f"输入表头不符合契约: {detail}"
        return report

    def validate_target_columns(
        self,
        target_table: str,
        write_columns: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        source_contract = self.source_contract(target_table)
        table_contract = self.table_contract(target_table)
        expected_columns = list(write_columns or source_contract.get("insert_columns") or [])
        actual_columns = [col["name"] for col in table_contract.get("columns", [])]
        missing = [column for column in expected_columns if column not in set(actual_columns)]
        report = {
            "pass": not missing,
            "target_table": target_table,
            "source_contract": self._source_path_by_target.get(target_table),
            "table_contract": self._table_path_by_name.get(target_table),
            "write_columns": expected_columns,
            "target_columns": actual_columns,
            "target_missing_columns": missing,
        }
        if missing:
            report["message"] = f"目标表字段不符合契约: 缺失字段 {missing}"
        else:
            report["message"] = "目标表写入字段符合契约"
        return report

    def validate_dataframe(
        self,
        target_table: str,
        actual_headers: Iterable[Any],
        file_name: str = "",
        data_type: str = "",
        write_columns: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        header_report = self.validate_headers(target_table, actual_headers, file_name, data_type)
        target_report = self.validate_target_columns(target_table, write_columns)
        passed = header_report["pass"] and target_report["pass"]
        report = {
            "pass": passed,
            "target_table": target_table,
            "file": file_name,
            "data_type": data_type,
            "header": header_report,
            "target": target_report,
            "missing_fields": header_report.get("missing_fields", []),
            "extra_fields": header_report.get("extra_fields", []),
            "order_mismatches": header_report.get("order_mismatches", []),
            "target_missing_columns": target_report.get("target_missing_columns", []),
        }
        if passed:
            report["message"] = "契约校验通过"
        else:
            detail = "；".join(self._message_parts(report)) or "契约不匹配"
            report["message"] = f"契约校验失败: {detail}"
        return report


def format_contract_report(report: dict[str, Any]) -> str:
    lines = [
        f"文件: {report.get('file') or '/'}",
        f"数据类型: {report.get('data_type') or '/'}",
        f"目标表: {report.get('target_table') or '/'}",
        f"结果: {'通过' if report.get('pass') else '失败'}",
        f"说明: {report.get('message') or '/'}",
    ]
    if report.get("missing_fields"):
        lines.append(f"缺失字段: {report['missing_fields']}")
    if report.get("extra_fields"):
        lines.append(f"新增字段: {report['extra_fields']}")
    if report.get("order_mismatches"):
        preview = report["order_mismatches"][:10]
        lines.append(f"顺序差异: {preview}")
    if report.get("target_missing_columns"):
        lines.append(f"目标表缺失字段: {report['target_missing_columns']}")
    if report.get("accepted_version"):
        lines.append(f"模板版本: {report['accepted_version']}")
    if report.get("fill_missing_headers"):
        lines.append(f"补齐空字段: {report['fill_missing_headers']}")
    if report.get("column_aliases"):
        lines.append(f"字段归一: {report['column_aliases']}")
    header = report.get("header") or {}
    target = report.get("target") or {}
    source_contract = report.get("source_contract") or header.get("source_contract")
    table_contract = report.get("table_contract") or target.get("table_contract")
    if source_contract:
        lines.append(f"输入契约: {source_contract}")
    if table_contract:
        lines.append(f"目标表契约: {table_contract}")
    recommendation = header.get("recommendation") or report.get("recommendation")
    if recommendation:
        lines.append(f"建议: {recommendation}")
    return "\n".join(lines)


__all__ = ["ContractValidator", "find_project_root", "format_contract_report"]
