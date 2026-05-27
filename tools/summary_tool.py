"""
tools/summary_tool.py — 快速摘要 Tool

LangChain Tool：为指定论文生成 200-300 字的可读摘要。
与 extract_tool 不同：摘要是连贯段落，提取是结构化字段。
"""

from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

from config import get_llm
from tools.extract_tool import paper_texts  # 复用同一份论文文本存储

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是学术论文阅读助手。请用 200-300 字的中文段落，为以下论文生成一段通俗易懂的摘要。"
        "摘要应包含：研究背景、核心方法、主要结论。不要使用列表，写成连贯段落。",
    ),
    ("human", "{paper_text}"),
])


@tool
def summary_tool(paper_id: str) -> str:
    """
    为指定论文生成 200-300 字的可读中文摘要。

    :param paper_id: 论文 ID
    """
    if paper_id not in paper_texts:
        return f"错误：找不到论文 {paper_id}，请先上传。"

    text = paper_texts[paper_id]
    truncated = text[:6000] if len(text) > 6000 else text

    llm = get_llm()
    chain = SUMMARY_PROMPT | llm

    try:
        result = chain.invoke({"paper_text": truncated})
        return result.content
    except Exception as e:
        return f"摘要生成失败：{str(e)}"
