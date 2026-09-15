"""
tests/test_tool_logic.py — 工具业务逻辑测试（纯逻辑，不连 LLM）

覆盖各工具在调用真实模型之前的业务校验分支：
- 论文数量不足（对比/缺口至少 2 篇）
- 论文 ID 不存在
这些分支决定用户能否得到明确、可纠正的提示，是最该被守住的行为。
每个校验分支都在"论文不存在/数量不足"这类缺陷上失败，属于恢复目标缺陷的负向用例。
"""

from contextvars import copy_context

from config import _current_session
from tools.extract_tool import paper_texts
from tools.compare_tool import compare_tool
from tools.gap_tool import gap_tool
from tools.summary_tool import summary_tool
from tools.extract_tool import extract_tool
from tools.citation_tool import citation_tool


def _run_in_session(session_id: str, fn):
    """在指定 session 上下文中执行，避免污染其他测试的会话数据。"""
    ctx = copy_context()

    def _task():
        _current_session.set(session_id)
        return fn()

    return ctx.run(_task)


class TestCompareValidation:
    """compare_tool 的业务校验：至少 2 篇、论文须存在。"""

    def test_less_than_two_papers_rejected(self):
        def body():
            return compare_tool.invoke({"paper_ids": "only_one"})
        result = _run_in_session("cmp-1", body)
        assert "至少需要 2 篇" in result

    def test_missing_paper_reported(self):
        def body():
            paper_texts["real_paper"] = "一些正文内容"
            return compare_tool.invoke({"paper_ids": "real_paper,ghost_paper"})
        result = _run_in_session("cmp-2", body)
        assert "未找到" in result
        assert "ghost_paper" in result


class TestGapValidation:
    """gap_tool 的业务校验：至少 2 篇、论文须存在。"""

    def test_less_than_two_papers_rejected(self):
        def body():
            return gap_tool.invoke({"paper_ids": "solo"})
        result = _run_in_session("gap-1", body)
        assert "至少需要 2 篇" in result

    def test_missing_paper_reported(self):
        def body():
            paper_texts["p_exists"] = "正文"
            return gap_tool.invoke({"paper_ids": "p_exists,p_missing"})
        result = _run_in_session("gap-2", body)
        assert "未找到" in result
        assert "p_missing" in result


class TestSinglePaperToolsMissing:
    """单篇工具在论文不存在时应返回明确的中文提示，而不是抛异常或空结果。"""

    def test_extract_missing_paper(self):
        def body():
            return extract_tool.invoke({"paper_id": "nope"})
        result = _run_in_session("single-1", body)
        assert "找不到论文" in result

    def test_summary_missing_paper(self):
        def body():
            return summary_tool.invoke({"paper_id": "nope"})
        result = _run_in_session("single-2", body)
        assert "找不到论文" in result

    def test_citation_missing_paper(self):
        def body():
            return citation_tool.invoke({"paper_id": "nope"})
        result = _run_in_session("single-3", body)
        assert "找不到论文" in result
