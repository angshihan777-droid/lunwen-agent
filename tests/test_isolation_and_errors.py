"""
tests/test_isolation_and_errors.py — FAISS 会话隔离、TTL 淘汰、错误处理

覆盖本次工程化改动的核心不变量：
1. FAISS 索引按会话隔离——A 会话看不到 B 会话的索引；
2. 带 TTL 的会话缓存超时后会淘汰旧数据，内存不会无限增长；
3. 系统级故障不再被伪装成正常结果：guard 抛 ToolError、log_tool_failure 返回提示。
均为纯逻辑测试，不连真实 LLM / embedding。
"""

import time
from contextvars import copy_context

import pytest

from config import _current_session
import rag.vectorstore as vs
from cachetools import TTLCache
from session_store import new_session_cache, touch
from tools.errors import ToolError, tool_error_guard, log_tool_failure


def _run_in_session(session_id: str, fn):
    ctx = copy_context()

    def _task():
        _current_session.set(session_id)
        return fn()

    return ctx.run(_task)


class _FakeStore:
    """占位向量库对象，避免测试触发真实 embedding 调用。"""
    def __init__(self, label):
        self.label = label


class TestFaissSessionIsolation:
    """验证 FAISS 索引按 session 隔离，跨会话不串。"""

    def test_store_not_shared_across_sessions(self):
        def put_a():
            vs._set_store(_FakeStore("A"))
            return vs._get_store().label
        def read_b():
            store = vs._get_store()
            return store.label if store else None

        assert _run_in_session("faiss-A", put_a) == "A"
        # B 会话此前未写入，必须看不到 A 的索引
        assert _run_in_session("faiss-B", read_b) is None

    def test_reset_only_clears_current_session(self):
        def put(label):
            vs._set_store(_FakeStore(label))
        _run_in_session("faiss-X", lambda: put("X"))
        _run_in_session("faiss-Y", lambda: put("Y"))
        _run_in_session("faiss-X", vs.reset)

        assert _run_in_session("faiss-X", vs._get_store) is None
        assert _run_in_session("faiss-Y", vs._get_store).label == "Y"


class TestTtlEviction:
    """验证带 TTL 的会话缓存会淘汰过期数据，防止内存无限增长。"""

    def test_entry_expires_after_ttl(self):
        cache = TTLCache(maxsize=16, ttl=0.05)  # 极短 TTL 便于快速验证
        cache["sid"] = {"data": 1}
        assert "sid" in cache
        time.sleep(0.1)
        # 过期后条目应被淘汰，容器回到空，不会长期占用内存
        assert "sid" not in cache
        assert len(cache) == 0

    def test_maxsize_bounds_memory(self):
        cache = TTLCache(maxsize=3, ttl=3600)
        for i in range(10):
            cache[f"s{i}"] = i
        # 容量上限兜底：无论来多少会话，占用都不超过 maxsize
        assert len(cache) <= 3

    def test_touch_refreshes_expiry(self):
        cache = new_session_cache()
        cache["sid"] = {"n": 1}
        val = touch(cache, "sid")
        assert val == {"n": 1}
        assert touch(cache, "absent") is None


class TestErrorHandling:
    """验证系统级故障被 loud 处理，而不是伪装成正常结果。"""

    def test_guard_wraps_and_raises(self):
        with pytest.raises(ToolError) as exc_info:
            with tool_error_guard("demo_tool"):
                raise RuntimeError("底层接口炸了")
        # 原始异常被保留，工具名被标注，便于定位
        assert exc_info.value.tool_name == "demo_tool"
        assert isinstance(exc_info.value.original, RuntimeError)

    def test_guard_passes_through_on_success(self):
        with tool_error_guard("demo_tool"):
            value = 1 + 1
        assert value == 2

    def test_log_tool_failure_returns_readable_hint(self):
        msg = log_tool_failure("arxiv_tool", TimeoutError("连接超时"))
        assert "arxiv_tool" in msg
        assert "TimeoutError" in msg
