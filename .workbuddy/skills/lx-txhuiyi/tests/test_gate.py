"""
lx-txhuiyi 门禁测试。

覆盖 FOG 治理要求的三个点：
    1. 未确认的变更操作只输出预览，不发起任何外部请求
    2. 确认后必须携带与当前参数匹配的 preview_hash
    3. 读回失败时停止并返回非零退出码，不谎报成功
"""

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import tencent_meeting as tm  # noqa: E402


class FakeProxy:
    """记录请求的假 MCP 代理，不产生任何网络调用"""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def request(self, method, params=None):
        self.calls.append((method, params))
        name = (params or {}).get("name", "")
        if name in self.responses:
            return self.responses[name]
        return {"result": {"content": [{"type": "text", "text": "ok"}]}}


class TestWriteGate(unittest.TestCase):
    def test_unconfirmed_write_returns_preview_without_request(self):
        """未确认时只输出预览，不得发起请求"""
        proxy = FakeProxy()
        params = {"name": "cancel_meeting", "arguments": {"meeting_id": "123"}}

        code, text = tm.run_request("tools/call", params, proxy)

        self.assertEqual(code, 0)
        self.assertIn("preview_hash", text)
        self.assertIn("预览", text)
        self.assertEqual(proxy.calls, [], "未确认的变更操作不得发起任何请求")

    def test_confirmed_write_requires_matching_preview_hash(self):
        """确认后缺少哈希或哈希不匹配，都必须拒绝执行"""
        proxy = FakeProxy()
        params = {"name": "cancel_meeting", "arguments": {"meeting_id": "123"}}

        code_missing, _ = tm.run_request("tools/call", params, proxy, confirmed=True)
        self.assertEqual(code_missing, 1)

        code_wrong, _ = tm.run_request(
            "tools/call", params, proxy, confirmed=True, preview_hash="deadbeef"
        )
        self.assertEqual(code_wrong, 1)

        self.assertEqual(proxy.calls, [], "哈希校验不通过时不得发起任何请求")

    def test_preview_hash_changes_with_arguments(self):
        """参数变化必须导致哈希变化，防止用旧预览执行新参数"""
        h1 = tm.compute_preview_hash("cancel_meeting", {"meeting_id": "123"})
        h2 = tm.compute_preview_hash("cancel_meeting", {"meeting_id": "456"})
        self.assertNotEqual(h1, h2)

    def test_confirmed_write_with_matching_hash_executes_and_reads_back(self):
        """哈希匹配才执行，并在执行后读回"""
        proxy = FakeProxy()
        params = {"name": "cancel_meeting", "arguments": {"meeting_id": "123"}}
        preview_hash = tm.compute_preview_hash("cancel_meeting", params["arguments"])

        code, text = tm.run_request(
            "tools/call", params, proxy, confirmed=True, preview_hash=preview_hash
        )

        self.assertEqual(code, 0)
        self.assertEqual(len(proxy.calls), 2, "执行后应跟一次读回请求")
        self.assertEqual(proxy.calls[1][1]["name"], "get_meeting")
        self.assertIn("[读回]", text)

    def test_readback_mismatch_stops_execution(self):
        """读回返回错误时必须停止并报错，不得报告成功"""
        proxy = FakeProxy(responses={"get_meeting": {"result": {"error": {"message": "会议不存在"}}}})
        params = {"name": "cancel_meeting", "arguments": {"meeting_id": "123"}}
        preview_hash = tm.compute_preview_hash("cancel_meeting", params["arguments"])

        code, text = tm.run_request(
            "tools/call", params, proxy, confirmed=True, preview_hash=preview_hash
        )

        self.assertEqual(code, 1, "读回失败必须返回非零退出码")
        self.assertIn("失败", text)


class TestReadToolsBypassGate(unittest.TestCase):
    def test_read_tool_executes_directly(self):
        """只读工具不受门禁约束，直接执行且不触发读回"""
        proxy = FakeProxy()
        params = {"name": "get_meeting", "arguments": {"meeting_id": "123"}}

        code, _ = tm.run_request("tools/call", params, proxy)

        self.assertEqual(code, 0)
        self.assertEqual(len(proxy.calls), 1)


class TestTokenResolution(unittest.TestCase):
    def test_empty_token_returns_empty(self):
        """三处都没有值时必须返回空，交由调用方提示配置"""
        original = tm._find_fog_config
        original_env = tm.os.environ.get("TENCENT_MEETING_TOKEN")
        original_file = tm.SKILL_TOKEN_FILE
        try:
            tm._find_fog_config = lambda: None
            tm.os.environ.pop("TENCENT_MEETING_TOKEN", None)
            tm.SKILL_TOKEN_FILE = Path("/nonexistent/token.env")
            self.assertEqual(tm.resolve_token(), ("", ""))
        finally:
            tm._find_fog_config = original
            tm.SKILL_TOKEN_FILE = original_file
            if original_env is not None:
                tm.os.environ["TENCENT_MEETING_TOKEN"] = original_env


class TestFogConfigParsing(unittest.TestCase):
    def test_ignores_enabled_skills_flag_with_same_name(self):
        """enabled_skills 下的同名开关不能被误认为配置节"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "fog_config.yaml"
            cfg.write_text(
                "version: 1\n"
                "enabled_skills:\n"
                "  lx_txhuiyi: true\n"
                "\n"
                "lx_txhuiyi:\n"
                '  token: "FROM_CONFIG_SECTION"\n',
                encoding="utf-8",
            )
            self.assertEqual(tm._read_fog_config_token(cfg), "FROM_CONFIG_SECTION")

    def test_strips_trailing_comment(self):
        """行尾注释不能被当成凭证内容"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "fog_config.yaml"
            cfg.write_text(
                "lx_txhuiyi:\n"
                '  token: "ABC123"  # 1Password: 未托管\n',
                encoding="utf-8",
            )
            self.assertEqual(tm._read_fog_config_token(cfg), "ABC123")

    def test_returns_empty_when_section_missing(self):
        """配置里没有该节时返回空，交由下一级回落处理"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "fog_config.yaml"
            cfg.write_text("enabled_skills:\n  lx_txhuiyi: true\n", encoding="utf-8")
            self.assertEqual(tm._read_fog_config_token(cfg), "")


class TestOfflineBlock(unittest.TestCase):
    def test_version_tools_are_blocked(self):
        """服务端仍暴露版本工具，客户端必须硬拦截，不发出请求"""
        for tool in (
            "check_skill_version",
            "get_skill_update_preference",
            "set_skill_update_preference",
        ):
            proxy = FakeProxy()
            code, text = tm.run_request(
                "tools/call", {"name": tool, "arguments": {}}, proxy, confirmed=True, preview_hash="x"
            )
            self.assertEqual(code, 1, f"{tool} 应被拒绝")
            self.assertIn("已禁用", text)
            self.assertEqual(proxy.calls, [], f"{tool} 不得产生任何请求")


if __name__ == "__main__":
    unittest.main()
