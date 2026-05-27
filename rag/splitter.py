"""
rag/splitter.py — 文本分块

使用 LangChain 的 RecursiveCharacterTextSplitter 将长文本切分成小块。
这是解决"论文太长放不进 token 窗口"问题的关键步骤。

chunk_size=800：每块约 800 字符，平衡检索精度和上下文完整性
chunk_overlap=100：相邻块有 100 字符重叠，避免关键信息被切断
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


def split_text(text: str, paper_id: str) -> list[Document]:
    """
    将论文全文切分为带元信息的 Document 列表。

    :param text: 论文全文字符串
    :param paper_id: 论文 ID，存入 Document metadata，检索时用于过滤
    :return: LangChain Document 列表
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", ".", " ", ""],  # 优先按段落切，其次按句子
    )

    chunks = splitter.split_text(text)

    # 每个 chunk 打上 paper_id 标签，方便多论文场景下按文章过滤
    documents = [
        Document(page_content=chunk, metadata={"paper_id": paper_id})
        for chunk in chunks
    ]

    return documents
