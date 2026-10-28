"""
腾讯会议工具主入口（FOG 离线定制版）

与官方原版的差异：
    1. 移除全部版本检查与自动重装逻辑（update_state / local_tools 已删除）
    2. Token 支持三级回落，不再强依赖 shell profile 中的环境变量
    3. 变更类操作加入 preview -> 显式确认 -> 读回 三段门禁（FOG 治理要求 R3）

Token 解析优先级：
    1. config/fog_config.yaml 的 lx_txhuiyi.token（FOG 工作区标准位置）
    2. 环境变量 TENCENT_MEETING_TOKEN（临时覆盖）
    3. 本 Skill 目录内的 token.env（脱离 FOG 工作区的兜底）

调用方式：
    python3 tencent_meeting.py tools/list
    python3 tencent_meeting.py tools/call '{"name":"get_meeting","arguments":{...}}'

    变更类工具分两段执行：
    python3 tencent_meeting.py tools/call '<params>'              # 预览，输出 preview_hash，不发起请求
    python3 tencent_meeting.py tools/call '<params>' --confirmed --preview-hash <hash>   # 真正执行并读回
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mcp_proxy import McpProxy
from utils import get_os_name

# Skill 根目录（scripts 的上级目录）
SKILL_DIR = Path(__file__).parent.parent.absolute()

# FOG 配置文件相对工作区根的路径
FOG_CONFIG_RELATIVE = Path("config") / "fog_config.yaml"

# FOG 配置中 Token 所在的 YAML 层级（沿用 FOG 按 skill 名分节的约定）
FOG_TOKEN_SECTION = "lx_txhuiyi"
FOG_TOKEN_KEY = "token"

# Skill 内 Token 文件
SKILL_TOKEN_FILE = SKILL_DIR / "token.env"

# 离线版硬拦截：服务端仍会暴露这些版本工具，客户端一律拒绝，避免绕过 SKILL.md 装回官方版
BLOCKED_TOOLS = frozenset(
    {
        "check_skill_version",
        "get_skill_update_preference",
        "set_skill_update_preference",
    }
)

# 变更类工具：会改变腾讯会议云端状态，必须走 preview -> 确认 -> 读回
WRITE_TOOLS = frozenset(
    {
        "schedule_meeting",
        "update_meeting",
        "cancel_meeting",
        "manage_waiting_room",
        "meeting_invitees_add",
        "meeting_invitees_remove",
        "meeting_invitees_replace",
        "meeting_control_call",
        "meeting_control_kick",
        "apply_record_permission_commit",
        "submit_feedback",
    }
)

# 变更类工具执行后用于读回核验的查询工具；无稳定读回目标的记为 None
READBACK_TOOLS = {
    "schedule_meeting": "get_meeting",
    "update_meeting": "get_meeting",
    "cancel_meeting": "get_meeting",
    "manage_waiting_room": "get_waiting_room",
    "meeting_invitees_add": "get_meeting_invitees",
    "meeting_invitees_remove": "get_meeting_invitees",
    "meeting_invitees_replace": "get_meeting_invitees",
    "meeting_control_call": None,
    "meeting_control_kick": None,
    "apply_record_permission_commit": None,
    "submit_feedback": None,
}

# 读回时可从原始参数复用的键（按优先级取第一个存在的）
READBACK_ARG_KEYS = {
    "get_meeting": ("meeting_id", "meeting_code"),
    "get_waiting_room": ("meeting_id", "meeting_code"),
    "get_meeting_invitees": ("meeting_id", "meeting_code"),
}


# 服务端端点与版本标识内置在脚本里。
# 原因：分发工具把名为 config.json 的文件列入禁止名单（默认视作本机个人配置），
# 而本技能只需两个不含凭证的公开常量，内联后即可自包含分发，不再依赖外部配置文件。
DEFAULT_BASE_URL = "https://mcp.meeting.tencent.com/mcp/wemeet-open/v1"
SKILL_VERSION = "v1.0.15"


def load_config() -> Dict[str, Any]:
    """
    返回连接配置。

    以内置常量为准；若本地存在 config.json 则允许覆盖（便于本机临时改端点），
    但该文件不参与分发，缺失时不影响运行。
    """
    config: Dict[str, Any] = {"name": "lx-txhuiyi", "version": SKILL_VERSION, "baseUrl": DEFAULT_BASE_URL}

    config_file = SKILL_DIR / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[警告] config.json 读取失败，使用内置配置: {e}", file=sys.stderr)

    return config


def _find_fog_config() -> Optional[Path]:
    """
    从当前工作目录向上查找 FOG 配置文件。

    FOG 工作区根目录下有 config/fog_config.yaml；
    Bash 工具的工作目录通常是工作区根，用户在子目录执行时也能向上命中。
    """
    try:
        current = Path.cwd().absolute()
    except OSError:
        return None

    for base in [current, *current.parents]:
        candidate = base / FOG_CONFIG_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def _clean_scalar(raw_value: str) -> str:
    """
    把配置里的标量清洗成纯凭证值。

    需要同时处理两种情况：
        1. 引号包裹的值，取配对引号内的内容
        2. 行尾注释（如 `token: "xxx"  # 1Password: 未托管`），必须剥离
    否则注释里的中文会被当成 Token 的一部分，导致 HTTP header 编码失败。
    """
    text = raw_value.strip()
    if not text:
        return ""

    if text[0] in "\"'":
        quote = text[0]
        end = text.find(quote, 1)
        inner = text[1:end] if end != -1 else text[1:]
        return inner.strip()

    # 无引号时，YAML 规范里注释以「空白 + #」开始
    return re.split(r"\s+#", text, maxsplit=1)[0].strip()


def _read_fog_config_token(config_path: Path) -> str:
    """
    从 fog_config.yaml 提取 lx_txhuiyi.token。

    刻意不引入 PyYAML：技能依赖越少越稳，且这里只需读一个两层的标量值。
    解析规则保守——只认顶格 section 加缩进一层内的 token 键，遇到同级新 section 即停止。
    """
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""

    in_section = False
    section_indent = 0

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if not in_section:
            # 只认顶格的映射节点。enabled_skills 下的同名开关（如 lx_txhuiyi: true）
            # 缩进后 stripped 与顶层键同名，必须靠 indent==0 与行内值双重排除。
            if indent == 0 and stripped.startswith(f"{FOG_TOKEN_SECTION}:"):
                inline_value = stripped.split(":", 1)[1].strip()
                if inline_value:
                    continue
                in_section = True
                section_indent = indent
            continue

        # 出现同级或更外层的新键，说明已离开目标 section
        if indent <= section_indent:
            break

        if stripped.startswith(f"{FOG_TOKEN_KEY}:"):
            return _clean_scalar(stripped.split(":", 1)[1])

    return ""


def _read_skill_token_env() -> str:
    """从 Skill 目录内的 token.env 提取 Token（形如 export TENCENT_MEETING_TOKEN="xxx"）"""
    if not SKILL_TOKEN_FILE.is_file():
        return ""

    try:
        lines = SKILL_TOKEN_FILE.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if "TENCENT_MEETING_TOKEN" not in line:
            continue

        _, _, rhs = line.partition("=")
        value = _clean_scalar(rhs)
        # 空值与变量引用不视为已配置
        if value and not value.startswith("$"):
            return value

    return ""


def resolve_token() -> Tuple[str, str]:
    """
    按优先级解析 Token。

    Returns:
        (token, 来源描述)；未找到时 token 为空字符串
    """
    fog_config = _find_fog_config()
    if fog_config is not None:
        token = _read_fog_config_token(fog_config)
        if token:
            return token, str(fog_config)

    token = os.environ.get("TENCENT_MEETING_TOKEN", "").strip()
    if token:
        return token, "环境变量 TENCENT_MEETING_TOKEN"

    token = _read_skill_token_env()
    if token:
        return token, str(SKILL_TOKEN_FILE)

    return "", ""


def compute_preview_hash(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    计算预览绑定哈希。

    绑定 tool 与完整参数，参数顺序无关；用户确认后若参数变化，哈希不匹配即拒绝执行。
    """
    payload = json.dumps(
        {"tool": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def render_preview(tool_name: str, arguments: Dict[str, Any], preview_hash: str) -> str:
    """渲染变更操作的预览文本，供用户确认"""
    lines = [
        f"[预览] 变更类操作未执行：{tool_name}",
        f"目标参数: {json.dumps(arguments, ensure_ascii=False, sort_keys=True)}",
        f"preview_hash: {preview_hash}",
        "",
        "确认后执行：",
        f"  python3 scripts/tencent_meeting.py tools/call '<上述JSON>' --confirmed --preview-hash {preview_hash}",
        "参数若有任何变化，preview_hash 会失效，需要重新预览。",
    ]
    return "\n".join(lines)


def render_result(method: str, result: Dict[str, Any]) -> Tuple[int, str]:
    """把 MCP 响应渲染为文本，返回 (退出码, 文本)"""
    if method == "tools/call" and "result" in result:
        inner = result["result"]
        if "error" in inner:
            error = inner["error"]
            message = error.get("message", json.dumps(error, ensure_ascii=False))
            return 1, f"[错误] {message}"
        if "content" in inner:
            texts = [item.get("text", "") for item in inner["content"] if item.get("type") == "text"]
            return 0, "\n".join(texts)
        return 0, json.dumps(result, ensure_ascii=False, indent=2)

    return 0, json.dumps(result, ensure_ascii=False, indent=2)


def verify_readback(proxy: McpProxy, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, str]:
    """
    变更操作后的读回核验。

    只做程序化可判定的部分：读回接口是否可用、是否返回错误。
    业务字段是否与预期一致，仍由模型按 SKILL.md 规范展示给用户核对。
    """
    key_names = READBACK_ARG_KEYS.get(tool_name, ())
    readback_args: Dict[str, Any] = {}
    for key in key_names:
        if key in arguments:
            readback_args[key] = arguments[key]
            break

    if not readback_args:
        return True, f"跳过：参数中没有可用于 {tool_name} 的读回键（{'/'.join(key_names)}）"

    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": readback_args},
        "id": 1,
    }
    try:
        response = proxy.request(request["method"], request["params"])
    except Exception as e:  # noqa: BLE001 - 读回失败必须显式报告，不能静默通过
        return False, f"失败：读回请求异常 {e}"

    inner = response.get("result") if isinstance(response, dict) else None
    if not isinstance(inner, dict):
        return False, "失败：读回响应结构异常"
    if "error" in inner:
        error = inner.get("error") or {}
        return False, f"失败：读回返回错误 {error.get('message', json.dumps(error, ensure_ascii=False))}"

    return True, f"通过：已用 {tool_name} 读取当前状态，请结合返回内容向用户核对"


def run_request(
    method: str,
    params: Dict[str, Any],
    proxy: McpProxy,
    confirmed: bool = False,
    preview_hash: str = "",
) -> Tuple[int, str]:
    """
    执行一次 MCP 请求，变更类操作先过门禁。

    Returns:
        (退出码, 输出文本)
    """
    tool_name = ""
    arguments: Dict[str, Any] = {}

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}

        # 离线版硬拦截：服务端清单里可能仍有版本工具，这里直接拒绝，不转发请求
        if tool_name in BLOCKED_TOOLS:
            return (
                1,
                f"[错误] {tool_name} 在 FOG 离线定制版中已禁用：本技能不跟随腾讯官方更新，"
                "升级由 FOG 维护者替换目录完成。",
            )

        if tool_name in WRITE_TOOLS:
            expected = compute_preview_hash(tool_name, arguments)

            # 第一段：未确认，只输出预览，不发起任何请求
            if not confirmed:
                return 0, render_preview(tool_name, arguments, expected)

            # 第二段：确认后必须绑定预览哈希
            if not preview_hash:
                return 1, "[错误] 变更类操作必须携带 --preview-hash，先预览再确认"
            if preview_hash != expected:
                return (
                    1,
                    "[错误] preview_hash 与当前参数不匹配，参数可能已变化，请重新预览并确认",
                )

    result = proxy.request(method, params)
    code, text = render_result(method, result)

    if method == "tools/call" and tool_name in WRITE_TOOLS:
        readback_tool = READBACK_TOOLS.get(tool_name)
        if readback_tool:
            ok, detail = verify_readback(proxy, readback_tool, arguments)
            text = f"{text}\n[读回] {detail}"
            if not ok:
                return 1, text
        else:
            text = f"{text}\n[读回] 该操作无稳定读回目标，请按 SKILL.md 规范向用户复核执行结果"

    return code, text


def print_usage() -> None:
    """打印使用说明"""
    usage = """
使用说明：
    python3 tencent_meeting.py <method> [params] [--confirmed --preview-hash <hash>]

参数说明：
    method  - JSONRPC2.0协议的method参数（必填）
    params  - JSONRPC2.0协议的params参数（选填，JSON格式字符串）
              当method为tools/call时，params为必填参数

变更类工具（创建/修改/取消会议、受邀人变更、等候室、会中呼叫与踢人、
录制权限提交、反馈上报）必须分两段执行：
    第一段：不带参数，输出预览与 preview_hash，不发起请求
    第二段：--confirmed --preview-hash <hash>，哈希匹配才真正执行并读回

调用示例：
    python3 tencent_meeting.py tools/list
    python3 tencent_meeting.py tools/call '{"name": "get_meeting_by_code", "arguments": {"meeting_code": "904854736"}}'
    python3 tencent_meeting.py tools/call '{"name": "cancel_meeting", "arguments": {"meeting_id": "123"}}'
    python3 tencent_meeting.py tools/call '{"name": "cancel_meeting", "arguments": {"meeting_id": "123"}}' --confirmed --preview-hash abc123
"""
    print(usage)


def parse_flags(argv: list) -> Tuple[bool, bool, str]:
    """解析门禁相关的命令行开关，返回 (confirmed, dry_run, preview_hash)"""
    confirmed = "--confirmed" in argv
    dry_run = "--dry-run" in argv
    preview_hash = ""

    for i, token in enumerate(argv):
        if token == "--preview-hash" and i + 1 < len(argv):
            preview_hash = argv[i + 1]
        elif token.startswith("--preview-hash="):
            preview_hash = token.split("=", 1)[1]

    return confirmed, dry_run, preview_hash


def validate_json(params_str: str) -> Dict[str, Any]:
    """校验并解析JSON参数"""
    try:
        params = json.loads(params_str)
        if not isinstance(params, dict):
            raise ValueError("params必须是JSON对象格式")
        return params
    except json.JSONDecodeError as e:
        raise ValueError(f"params参数不是有效的JSON格式: {e}")


def validate_and_fill_client_info(params: Dict[str, Any]) -> Dict[str, Any]:
    """校验并填充 _client_info 中的 os 字段，避免模型凭空编造系统版本"""
    if "arguments" not in params:
        return params

    arguments = params["arguments"]
    if not isinstance(arguments, dict):
        raise ValueError("arguments字段必须是JSON对象格式")

    if "_client_info" not in arguments:
        return params

    client_info = arguments["_client_info"]
    if not isinstance(client_info, dict):
        raise ValueError("_client_info字段必须是JSON对象格式")

    params["arguments"]["_client_info"]["os"] = get_os_name()
    return params


def main() -> None:
    """主函数"""
    argv = sys.argv[1:] if len(sys.argv) > 1 else []
    positional = [a for a in argv if not a.startswith("--")]

    if not positional:
        print("[错误] 缺少method参数\n")
        print_usage()
        sys.exit(1)

    method = positional[0]
    params_str = positional[1] if len(positional) > 1 else ""
    confirmed, dry_run, preview_hash = parse_flags(argv)

    if method == "tools/call" and not params_str:
        print("[错误] method为tools/call时，params参数为必填\n")
        print_usage()
        sys.exit(1)

    if params_str:
        try:
            params = validate_json(params_str)
        except ValueError as e:
            print(f"[错误] 参数错误: {e}\n")
            print_usage()
            sys.exit(1)
    else:
        params = {}

    if method == "tools/call":
        try:
            params = validate_and_fill_client_info(params)
        except ValueError as e:
            print(f"[错误] 参数错误: {e}")
            sys.exit(1)

    # --dry-run 等价于未确认，仅输出预览
    if dry_run:
        confirmed = False

    token, _source = resolve_token()
    if not token:
        print("[错误] 未找到腾讯会议 Token")
        print("请任选一处配置（优先级从高到低）：")
        print("    1. FOG 工作区 config/fog_config.yaml 的 lx_txhuiyi.token")
        print("    2. 环境变量 TENCENT_MEETING_TOKEN")
        print(f"    3. 本 Skill 目录 token.env：{SKILL_TOKEN_FILE}")
        print("Token 获取地址：https://meeting.tencent.com/ai-skill")
        sys.exit(1)

    try:
        config = load_config()
        base_url = config.get("baseUrl", "")
        skill_version = config.get("version", "")

        if not base_url:
            print("[错误] 配置错误: config.json中缺少baseUrl字段")
            sys.exit(1)

        proxy = McpProxy(token, base_url, skill_version)
        code, text = run_request(method, params, proxy, confirmed, preview_hash)
        print(text)
        sys.exit(code)

    except FileNotFoundError as e:
        print(f"[错误] 配置错误: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"[错误] 配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 请求失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
