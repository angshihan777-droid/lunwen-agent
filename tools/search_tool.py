"""
tools/search_tool.py — RAG 语义检索 Tool

LangChain Tool：在已上传论文的 FAISS 向量库中进行语义检索。
这是多轮问答（F4）的核心支撑，解决论文太长放不进上下文的问题。
"""

from langchain.tools import tool

from config import session_config
import rag.vectorstore as vs
from tools.errors import log_tool_failure


@tool
def search_tool(query: str, paper_id: str = "") -> str:
    """
    在论文内容中语义搜索相关段落，返回最相关的 5 个文本块。
    paper_id 不为空时只搜该论文，为空时搜索当前会话的所有论文。

    :param query: 检索问题或关键词
    :param paper_id: 论文 ID（可选，为空则搜索当前会话所有已上传论文）
    """
    api_key = session_config["llm_api_key"]
    if not api_key:
        return "错误：API Key 未设置。"

    try:
        results = vs.search(
            query=query,
            api_key=api_key,
            paper_id=paper_id if paper_id else None,
            k=5,
        )
    except Exception as e:
        # embedding/检索等系统故障：记完整日志，返回可读提示
        return log_tool_failure("search_tool", e)

    if not results:
        return "未找到相关内容，请确认论文已上传。"

    # 将检索结果拼接成字符串返回给 Agent
    passages = []
    for i, doc in enumerate(results, 1):
        pid = doc.metadata.get("paper_id", "未知")
        passages.append(f"[段落 {i}（来自 {pid}）]\n{doc.page_content}")

    return "\n\n---\n\n".join(passages)
