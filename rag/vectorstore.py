"""
rag/vectorstore.py — FAISS 向量库管理（多用户隔离版）

每个会话（session_id）拥有独立的 FAISS 索引，会话 ID 由
config._current_session ContextVar 提供，与论文文本 / 配置 / 记忆的隔离口径一致。
这样 A 用户检索时绝不会召回 B 用户上传的论文。

索引存放在带 TTL 的缓存中（见 session_store），会话闲置超时后随之淘汰，
避免长期运行时内存无上限增长。跨线程访问（/upload 的重活在线程池执行）
由 STORE_LOCK 保护。

Embedding 优先使用与 LLM 相同的 base_url（中转站场景），
若中转站不支持 embedding 接口，则调用方自行降级跳过索引，上传仍然成功。
"""

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from config import _current_session
from session_store import STORE_LOCK, new_session_cache, touch

# session_id -> FAISS；带闲置过期与容量上限
_all_vectorstores = new_session_cache()


def _get_store():
    """读取当前会话的 FAISS 索引；不存在时返回 None（尚未上传论文）。"""
    sid = _current_session.get()
    with STORE_LOCK:
        return touch(_all_vectorstores, sid)


def _set_store(store) -> None:
    sid = _current_session.get()
    with STORE_LOCK:
        _all_vectorstores[sid] = store


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
    将一批 Document 添加到当前会话的 FAISS 索引中。
    返回 True 表示成功；embedding 调用失败时向上抛出，由调用方决定是否降级。

    :param documents: 切分好的 Document 列表
    :param api_key: API Key
    :param base_url: 代理 base_url，为空则用标准 OpenAI
    """
    embeddings = _get_embeddings(api_key, base_url or None)

    store = _get_store()
    if store is None:
        store = FAISS.from_documents(documents, embeddings)
        _set_store(store)
    else:
        store.add_documents(documents)

    return True


def search(query: str, api_key: str, base_url: str = "",
           paper_id: str | None = None, k: int = 5) -> list[Document]:
    """在当前会话的索引内语义检索，返回最相关的 k 个文本块。"""
    store = _get_store()
    if store is None:
        return []

    if paper_id:
        results = store.similarity_search(
            query, k=k, filter={"paper_id": paper_id}
        )
    else:
        results = store.similarity_search(query, k=k)

    return results


def reset() -> None:
    """清空当前会话的向量库。"""
    sid = _current_session.get()
    with STORE_LOCK:
        _all_vectorstores.pop(sid, None)
