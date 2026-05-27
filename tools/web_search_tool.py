"""
tools/web_search_tool.py — 网络搜索 Tool

LangChain Tool：使用 Tavily API 搜索网络信息。
适合查询：作者近期工作、论文引用情况、相关讨论、最新进展。
需要用户提供 Tavily API Key（在前端设置面板填写）。
"""

from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults

from config import get_tavily_key


@tool
def web_search_tool(query: str) -> str:
    """
    在互联网上搜索与论文相关的信息（作者、引用、最新进展等）。
    需要在设置面板中填写 Tavily API Key。

    :param query: 搜索内容，例如"Geoffrey Hinton 2024 research"
    """
    try:
        api_key = get_tavily_key()

        # 创建 Tavily 搜索实例，返回最多 3 条结果
        search = TavilySearchResults(
            max_results=3,
            tavily_api_key=api_key,
        )

        results = search.invoke(query)

        if not results:
            return f"未找到与 '{query}' 相关的网络信息。"

        # 格式化输出
        formatted = []
        for i, item in enumerate(results, 1):
            title = item.get("title", "无标题")
            url = item.get("url", "")
            content = item.get("content", "")[:300]
            formatted.append(f"[{i}] {title}\n{url}\n{content}...")

        return "\n\n---\n\n".join(formatted)

    except ValueError as e:
        # API Key 未设置
        return str(e)
    except Exception as e:
        return f"网络搜索失败：{str(e)}"
