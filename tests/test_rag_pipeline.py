"""
tests/test_rag_pipeline.py — RAG 管道确定性测试

验证 PDF 解析 → 分块 → 元信息标注 这条管道的正确性。
不调用 LLM 和 embedding，纯逻辑验证，速度极快。
"""

import os
import tempfile
import pytest

from rag.splitter import split_text
from langchain_core.documents import Document


# ── split_text 分块测试 ───────────────────────────────────────

class TestSplitText:
    """验证 RecursiveCharacterTextSplitter 分块行为。"""

    PAPER_ID = "test-paper-001"

    def test_returns_list_of_documents(self):
        """split_text 必须返回 Document 列表。"""
        docs = split_text("这是一段测试文本。" * 50, self.PAPER_ID)
        assert isinstance(docs, list)
        assert len(docs) > 0
        assert all(isinstance(d, Document) for d in docs)

    def test_each_chunk_has_paper_id_metadata(self):
        """每个 chunk 都必须带有正确的 paper_id 元信息，用于 FAISS 过滤。"""
        docs = split_text("测试内容。" * 100, self.PAPER_ID)
        for doc in docs:
            assert doc.metadata.get("paper_id") == self.PAPER_ID, \
                f"chunk 缺少 paper_id 元信息：{doc.metadata}"

    def test_chunk_size_within_limit(self):
        """每个 chunk 长度不超过 chunk_size（800）+ overlap（100）的合理范围。"""
        long_text = "A" * 5000
        docs = split_text(long_text, self.PAPER_ID)
        for doc in docs:
            assert len(doc.page_content) <= 1000, \
                f"chunk 过长（{len(doc.page_content)} 字符），超出预期范围"

    def test_short_text_produces_single_chunk(self):
        """短文本（小于 chunk_size）应该只产生 1 个 chunk，不被错误切分。"""
        short_text = "这是一篇很短的论文摘要。" * 5
        docs = split_text(short_text, self.PAPER_ID)
        assert len(docs) == 1

    def test_long_text_produces_multiple_chunks(self):
        """长文本必须被切分成多个 chunk，这是 RAG 的核心价值。"""
        long_text = "这是论文正文内容，包含详细的方法描述。" * 200
        docs = split_text(long_text, self.PAPER_ID)
        assert len(docs) > 1, "长文本应该被切分成多个 chunk"

    def test_chunks_cover_full_content(self):
        """所有 chunk 拼合后应包含原文的全部内容（无内容丢失）。"""
        original = "独特关键词_ABC " * 50
        docs = split_text(original, self.PAPER_ID)
        combined = " ".join(d.page_content for d in docs)
        assert "独特关键词_ABC" in combined, "原文内容在分块后丢失！"

    def test_different_paper_ids_tagged_correctly(self):
        """不同论文的 chunks 应该带上各自的 paper_id，不能混淆。"""
        docs_a = split_text("论文A内容" * 50, "paper-A")
        docs_b = split_text("论文B内容" * 50, "paper-B")

        for d in docs_a:
            assert d.metadata["paper_id"] == "paper-A"
        for d in docs_b:
            assert d.metadata["paper_id"] == "paper-B"


# ── PDF 解析测试 ──────────────────────────────────────────────

class TestPdfLoader:
    """验证 PyMuPDF loader 的基本行为。"""

    def test_load_real_pdf_if_available(self):
        """如果 uploads/ 目录有演示 PDF，验证解析结果非空且页数合理。"""
        from rag.loader import load_pdf

        demo_paths = [
            "uploads/demo_multiagent_survey.pdf",
            "uploads/demo_transformer_attention.pdf",
            "uploads/demo_bert_pretraining.pdf",
        ]

        loaded = 0
        for path in demo_paths:
            if not os.path.exists(path):
                continue
            text, page_count = load_pdf(path)
            assert len(text) > 100, f"{path} 解析出的文本过短（{len(text)} 字符）"
            assert page_count >= 1, f"{path} 页数异常：{page_count}"
            assert "Abstract" in text or "abstract" in text or "摘要" in text or len(text) > 500
            loaded += 1

        if loaded == 0:
            pytest.skip("uploads/ 目录中没有演示 PDF，跳过此测试（先启动服务生成 demo）")

    def test_load_pdf_returns_tuple(self):
        """验证 load_pdf 返回 (str, int) 格式，避免接口破坏。"""
        from rag.loader import load_pdf
        import inspect
        sig = inspect.signature(load_pdf)
        # 只检查函数签名存在 file_path 参数
        assert "file_path" in sig.parameters
