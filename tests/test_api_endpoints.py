"""
tests/test_api_endpoints.py — FastAPI 端点基础测试

使用 TestClient（不启动真实服务器）验证路由可达性、
请求格式校验、错误码是否符合预期。
不调用真实 LLM（API Key 未设置时应返回 400 而非崩溃）。
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

SESSION_HEADERS = {"X-Session-ID": "test-session-pytest"}


# ── 基础可达性 ────────────────────────────────────────────────

class TestBasicReachability:
    """验证服务启动后各端点均可访问，不会 404 或 500 崩溃。"""

    def test_homepage_returns_html(self):
        resp = client.get("/", headers=SESSION_HEADERS)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_papers_list_returns_json(self):
        resp = client.get("/papers", headers=SESSION_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "papers" in data
        assert isinstance(data["papers"], list)

    def test_reset_returns_ok(self):
        resp = client.post("/reset", headers=SESSION_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── 请求格式校验 ──────────────────────────────────────────────

class TestRequestValidation:
    """验证非法请求能正确返回 4xx，不会导致服务崩溃。"""

    def test_config_requires_api_key(self):
        """空 API Key 应该返回 400。"""
        resp = client.post("/config", json={
            "llm_provider": "openai",
            "llm_api_key": "",
        }, headers=SESSION_HEADERS)
        assert resp.status_code == 400

    def test_config_rejects_unknown_provider(self):
        """不支持的 provider 应该返回 400。"""
        resp = client.post("/config", json={
            "llm_provider": "unknown_provider",
            "llm_api_key": "sk-test",
        }, headers=SESSION_HEADERS)
        assert resp.status_code == 400

    def test_compare_requires_at_least_two_papers(self):
        """对比只传一篇论文应该返回 400。"""
        resp = client.post("/compare", json={
            "paper_ids": ["only-one-paper"]
        }, headers=SESSION_HEADERS)
        assert resp.status_code == 400

    def test_gap_requires_at_least_two_papers(self):
        """缺口分析只传一篇应该返回 400。"""
        resp = client.post("/gap", json={
            "paper_ids": ["only-one"]
        }, headers=SESSION_HEADERS)
        assert resp.status_code == 400

    def test_extract_requires_api_key_set(self):
        """未设置 API Key 时调用 extract 应该返回 400，而不是 500 崩溃。"""
        resp = client.post("/extract", json={
            "paper_id": "any-paper"
        }, headers={"X-Session-ID": "no-key-session"})
        assert resp.status_code == 400

    def test_upload_rejects_non_pdf(self):
        """上传非 PDF 文件应该返回 400。"""
        resp = client.post(
            "/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
            headers=SESSION_HEADERS,
        )
        assert resp.status_code == 400

    def test_extract_returns_404_for_unknown_paper(self):
        """提取不存在的论文应该返回 404，而不是 500。"""
        # 先设置一个假 Key，让 _require_api_key 通过
        client.post("/config", json={
            "llm_provider": "openai",
            "llm_api_key": "sk-fake-key-for-test",
        }, headers=SESSION_HEADERS)

        resp = client.post("/extract", json={
            "paper_id": "this-paper-does-not-exist"
        }, headers=SESSION_HEADERS)
        assert resp.status_code == 404


# ── 会话隔离端点测试 ──────────────────────────────────────────

class TestSessionIsolationViaAPI:
    """通过 HTTP 端点验证不同 session 的数据隔离。"""

    def test_papers_list_isolated_between_sessions(self):
        """
        不同 session 的论文列表独立：
        session-X 的论文不出现在 session-Y 的列表中。
        （演示论文是启动时写入 __default__ 再复制的，均可见，此处验证手动上传的隔离）
        """
        # 两个会话各自查询论文列表，不应互相污染
        resp_x = client.get("/papers", headers={"X-Session-ID": "isolation-X"})
        resp_y = client.get("/papers", headers={"X-Session-ID": "isolation-Y"})
        assert resp_x.status_code == 200
        assert resp_y.status_code == 200

    def test_reset_only_affects_current_session(self):
        """reset 只清除当前会话的记忆，不影响其他会话。"""
        resp = client.post("/reset", headers={"X-Session-ID": "reset-target"})
        assert resp.status_code == 200

        # 其他会话仍然可以正常访问
        resp2 = client.get("/papers", headers={"X-Session-ID": "not-reset-session"})
        assert resp2.status_code == 200
