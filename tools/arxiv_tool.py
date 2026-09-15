"""
tools/arxiv_tool.py — ArXiv 论文搜索 Tool

LangChain Tool：根据关键词在 ArXiv 上搜索相关论文。
使用 arxiv Python 库，完全免费，无需 API Key。
体现 Agent 能主动获取外部信息，不只是处理上传文件。
"""

import arxiv
from langchain.tools import tool

from tools.errors import log_tool_failure


@tool
def arxiv_tool(query: str) -> str:
    """
    在 ArXiv 上搜索相关论文，返回最多 5 篇结果。
    返回每篇论文的标题、作者、摘要和链接。

    :param query: 搜索关键词或论文标题（英文效果更好）
    """
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=5,
            sort_by=arxiv.SortCriterion.Relevance,
        )

        results = list(client.results(search))

        if not results:
            return f"ArXiv 上未找到与 '{query}' 相关的论文。"

        papers = []
        for i, paper in enumerate(results, 1):
            authors = ", ".join(str(a) for a in paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " 等"

            # 摘要截取前 200 字
            abstract = paper.summary[:200] + "..." if len(paper.summary) > 200 else paper.summary

            papers.append(
                f"[{i}] **{paper.title}**\n"
                f"作者：{authors}\n"
                f"摘要：{abstract}\n"
                f"链接：{paper.entry_id}\n"
            )

        return "\n---\n".join(papers)

    except Exception as e:
        # 网络/解析等系统故障：记完整日志，返回可读提示让 Agent 如实转告用户
        return log_tool_failure("arxiv_tool", e)
