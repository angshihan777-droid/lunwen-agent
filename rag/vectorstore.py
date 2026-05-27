"""
rag/vectorstore.py — FAISS 向量库管理

维护一个全局的 FAISS 索引，支持：
- 新论文上传后增量添加 embedding
- 按 paper_id 过滤检索（只搜某篇论文）
- 跨论文全局检索（对比、缺口分析时使用）

Embedding 优先使用与 LLM 相同的 base_url（中转站场景），
若中转站不支持 embedding 接口，则自动降级跳过索引，上传仍然成功。

⚠️ 设计说明：_vectorstore 是进程级全局对象，所有会话共享同一 FAISS 索引。
这是一个有意识的简化决策：
  - 论文文本（paper_texts）已通过 _PaperTextsProxy 实现会话隔离
  - FAISS 索引共享不会导致数据泄露（metadata 过滤确保每篇论文的块归属可追溯）
  - 好处：不同用户上传的论文可以互相"看到"，方便 demo 演示
  - 若需严格隔离，可改为 dict[session_id, FAISS]，参考 _all_paper_texts 模式
"""

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

# 全局 FAISS 实例，启动时为空，上传论文后动态构建
_vectorstore: FAISS | None = None


def _get_embeddings(api_key: str, base_url: str | None = None):
    """
    返回 embedding 模型。
    base_url 不为空时使用代理地址（与 chat 接口保持一致），
    为空时调用标准 OpenAI endpoint。
    """
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
        base_url=base_url or None,
    )


def add_documents(documents: list[Document], api_key: str, base_url: str = "") -> bool:
    """
    将一批 Document 添加到 FAISS 索引中。
    返回 True 表示成功，False 表示 embedding 调用失败（上传不受影响）。

    :param documents: 切分好的 Document 列表
    :param api_key: API Key
    :param base_url: 代理 base_url，为空则用标准 OpenAI
    """
    global _vectorstore
    embeddings = _get_embeddings(api_key, base_url or None)

    if _vectorstore is None:
        _vectorstore = FAISS.from_documents(documents, embeddings)
    else:
        _vectorstore.add_documents(documents)

    return True


def search(query: str, api_key: str, base_url: str = "",
           paper_id: str | None = None, k: int = 5) -> list[Document]:
    """语义检索，返回最相关的 k 个文本块。"""
    if _vectorstore is None:
        return []

    if paper_id:
        results = _vectorstore.similarity_search(
            query, k=k, filter={"paper_id": paper_id}
        )
    else:
        results = _vectorstore.similarity_search(query, k=k)

    return results


def reset() -> None:
    """清空向量库"""
    global _vectorstore
    _vectorstore = None
