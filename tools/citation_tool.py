"""
tools/citation_tool.py — 参考文献提取 Tool

LangChain Tool：从论文文本末尾提取参考文献列表。
体现多步推理：先用 LLM 提取文献列表，再格式化输出。
"""

from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

from config import get_llm
from tools.extract_tool import paper_texts

CITATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是学术文献专家。请从以下论文文本中提取参考文献列表。
要求：
- 每条文献单独一行，前面加编号
- 格式：[编号] 作者. 标题. 期刊/会议, 年份
- 最多提取 20 条
- 如果找不到参考文献部分，请回复"未找到参考文献"
- 只输出文献列表，不要其他解释""",
    ),
    (
        "human",
        # 参考文献通常在论文末尾，取最后 3000 字符
        "以下是论文末尾部分内容，请提取参考文献：\n\n{paper_tail}",
    ),
])


@tool
def citation_tool(paper_id: str) -> str:
    """
    从指定论文中提取参考文献列表（最多 20 条）。

    :param paper_id: 论文 ID
    """
    if paper_id not in paper_texts:
        return f"错误：找不到论文 {paper_id}，请先上传。"

    text = paper_texts[paper_id]
    # 参考文献通常在末尾，取最后 3000 字
    paper_tail = text[-3000:] if len(text) > 3000 else text

    llm = get_llm()
    chain = CITATION_PROMPT | llm

    try:
        result = chain.invoke({"paper_tail": paper_tail})
        return result.content
    except Exception as e:
        return f"参考文献提取失败：{str(e)}"
