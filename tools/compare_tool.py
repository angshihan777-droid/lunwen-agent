"""
tools/compare_tool.py — 论文对比 Tool

LangChain Tool：对比多篇论文，输出 Markdown 表格。
输入：逗号分隔的 paper_id 列表
输出：Markdown 格式的对比表格
"""

from langchain.tools import tool

from config import get_llm
from prompts.compare_prompt import COMPARE_PROMPT
from tools.extract_tool import paper_texts
from tools.errors import tool_error_guard


@tool
def compare_tool(paper_ids: str) -> str:
    """
    对比多篇论文，输出 Markdown 对比表格（方法/数据集/指标/结论/局限性）。
    paper_ids 格式：用逗号分隔，例如 "paper1,paper2,paper3"

    :param paper_ids: 逗号分隔的论文 ID 字符串
    """
    ids = [pid.strip() for pid in paper_ids.split(",") if pid.strip()]

    if len(ids) < 2:
        return "错误：对比至少需要 2 篇论文。"

    # 检查所有论文是否已上传
    missing = [pid for pid in ids if pid not in paper_texts]
    if missing:
        return f"错误：以下论文未找到，请先上传：{', '.join(missing)}"

    # 为每篇论文准备摘要信息（取前 2000 字，避免 token 超限）
    papers_info_parts = []
    for pid in ids:
        text = paper_texts[pid]
        snippet = text[:2000] if len(text) > 2000 else text
        papers_info_parts.append(f"【论文：{pid}】\n{snippet}")

    papers_info = "\n\n".join(papers_info_parts)

    llm = get_llm()
    chain = COMPARE_PROMPT | llm

    with tool_error_guard("compare_tool"):
        result = chain.invoke({
            "paper_count": len(ids),
            "papers_info": papers_info,
        })
        return result.content
