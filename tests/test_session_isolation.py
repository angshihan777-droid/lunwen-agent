"""
tests/test_session_isolation.py — 会话隔离逻辑测试

验证核心设计：不同 session_id 的数据完全独立，互不干扰。
这是多用户并发正确性的保障，不需要 LLM，纯逻辑测试。
"""

import pytest
from contextvars import copy_context

from config import _current_session, update_config, session_config
from tools.extract_tool import _all_paper_texts, _get_texts


# ── 工具函数 ──────────────────────────────────────────────────

def _run_in_session(session_id: str, fn):
    """在指定 session_id 上下文中执行函数，模拟中间件行为。"""
    ctx = copy_context()
    def _task():
        _current_session.set(session_id)
        return fn()
    return ctx.run(_task)


# ── Config 隔离测试 ───────────────────────────────────────────

class TestConfigIsolation:
    """验证 _SessionProxy：不同会话的 API Key 互不干扰。"""

    def test_different_sessions_have_independent_config(self):
        """会话 A 设置的 API Key 不影响会话 B。"""
        def set_session_a():
            update_config("openai", "key-for-A", "", "", "gpt-4o")
            return session_config["llm_api_key"]

        def set_session_b():
            update_config("anthropic", "key-for-B", "", "", "claude-3-5-sonnet-20241022")
            return session_config["llm_api_key"]

        key_a = _run_in_session("session-A", set_session_a)
        key_b = _run_in_session("session-B", set_session_b)

        assert key_a == "key-for-A"
        assert key_b == "key-for-B"
        assert key_a != key_b

    def test_session_config_does_not_leak_across_sessions(self):
        """会话 A 更新配置后，会话 B 读取的仍是自己的旧配置。"""
        # 先建立会话 B 的配置
        _run_in_session("session-leak-B", lambda: update_config("openai", "original-B", "", "", ""))

        # 会话 A 写入新配置
        _run_in_session("session-leak-A", lambda: update_config("openai", "key-A-new", "", "", ""))

        # 会话 B 的配置应该不变
        key_b = _run_in_session("session-leak-B", lambda: session_config["llm_api_key"])
        assert key_b == "original-B", f"配置泄露！B 的 key 变成了 {key_b}"

    def test_provider_isolated_per_session(self):
        """不同会话可以使用不同的 LLM provider。"""
        _run_in_session("s-openai", lambda: update_config("openai", "key1", "", "", "gpt-4o"))
        _run_in_session("s-anthropic", lambda: update_config("anthropic", "key2", "", "", "claude-3-5-sonnet-20241022"))

        p1 = _run_in_session("s-openai", lambda: session_config["llm_provider"])
        p2 = _run_in_session("s-anthropic", lambda: session_config["llm_provider"])

        assert p1 == "openai"
        assert p2 == "anthropic"


# ── Paper Texts 隔离测试 ──────────────────────────────────────

class TestPaperTextsIsolation:
    """验证 _PaperTextsProxy：不同会话的论文列表互不干扰。"""

    def setup_method(self):
        """每个测试前清空测试会话的数据。"""
        for sid in ["pt-session-A", "pt-session-B", "pt-session-copy"]:
            _all_paper_texts.pop(sid, None)

    def test_paper_uploaded_in_session_a_not_visible_in_session_b(self):
        """会话 A 上传的论文，会话 B 看不到。"""
        def upload_to_a():
            texts = _get_texts()
            texts["paper-exclusive-to-A"] = "content of paper A"

        def check_in_b():
            texts = _get_texts()
            return "paper-exclusive-to-A" in texts

        _run_in_session("pt-session-A", upload_to_a)
        visible_in_b = _run_in_session("pt-session-B", check_in_b)

        assert not visible_in_b, "论文从会话 A 泄露到了会话 B！"

    def test_each_session_has_independent_paper_list(self):
        """两个会话各自上传不同论文，列表完全独立。"""
        def upload_a():
            _get_texts()["paper-A1"] = "text A1"
            _get_texts()["paper-A2"] = "text A2"

        def upload_b():
            _get_texts()["paper-B1"] = "text B1"

        _run_in_session("pt-session-A", upload_a)
        _run_in_session("pt-session-B", upload_b)

        keys_a = _run_in_session("pt-session-A", lambda: set(_get_texts().keys()))
        keys_b = _run_in_session("pt-session-B", lambda: set(_get_texts().keys()))

        # 去掉 __default__ 里的 demo 论文，只看会话独有部分
        own_a = {k for k in keys_a if k.startswith("paper-A")}
        own_b = {k for k in keys_b if k.startswith("paper-B")}

        assert own_a == {"paper-A1", "paper-A2"}
        assert own_b == {"paper-B1"}
        assert own_a.isdisjoint(own_b)

    def test_new_session_copies_demo_papers(self):
        """新会话首次访问时，应自动继承 __default__ 中的演示论文。"""
        # 在 __default__ 写入一篇 demo 论文（模拟 startup 逻辑）
        _all_paper_texts.setdefault("__default__", {})["demo_paper"] = "demo content"

        # 全新会话访问时应能看到 demo 论文
        has_demo = _run_in_session(
            "pt-session-copy",
            lambda: "demo_paper" in _get_texts()
        )
        assert has_demo, "新会话应该自动继承演示论文"
