"""
tools/gap_tool.py — 研究缺口识别 Tool

LangChain Tool：综合多篇论文，主动找出研究空白和未解决问题。
这是最有差异化的功能——Agent 主动分析而不只是总结。
"""

from langchain.tools import tool

from config import get_llm
from prompts.gap_prompt import GAP_PROMPT
from tools.extract_tool import paper_texts
from tools.errors import tool_error_guard


@tool
def gap_tool(paper_ids: str) -> str:
    """
    分析多篇论文，识别研究缺口和未解决的问题。
    paper_ids 格式：用逗号分隔，例如 "paper1,paper2,paper3"

    :param paper_ids: 逗号分隔的论文 ID 字符串
    """
    ids = [pid.strip() for pid in paper_ids.split(",") if pid.strip()]

    if len(ids) < 2:
        return "错误：缺口分析至少需要 2 篇论文。"

    missing = [pid for pid in ids if pid not in paper_texts]
    if missing:
        return f"错误：以下论文未找到，请先上传：{', '.join(missing)}"

    papers_info_parts = []
    for pid in ids:
        text = paper_texts[pid]
        snippet = text[:2000] if len(text) > 2000 else text
        papers_info_parts.append(f"【论文：{pid}】\n{snippet}")

    papers_info = "\n\n".join(papers_info_parts)

    llm = get_llm()
    chain = GAP_PROMPT | llm

    with tool_error_guard("gap_tool"):
        result = chain.invoke({
            "paper_count": len(ids),
            "papers_info": papers_info,
        })
        return result.content
