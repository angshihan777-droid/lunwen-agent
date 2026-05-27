"""
prompts/compare_prompt.py — 论文对比 Prompt

任务：对比多篇论文，输出 Markdown 表格。
横轴是论文标题，纵轴是对比维度（方法/数据集/指标/结论/局限性）。
"""

from langchain_core.prompts import ChatPromptTemplate

COMPARE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是一位专业的学术论文对比分析助手。
请对比以下多篇论文，以 Markdown 表格形式输出结果。

表格格式要求：
- 第一列：对比维度（研究问题 / 方法 / 数据集 / 核心指标 / 结论 / 局限性）
- 后续列：每篇论文各占一列，列名为论文标题
- 内容简洁，每格不超过 50 字
- 输出纯 Markdown，不要额外解释""",
    ),
    (
        "human",
        """请对比以下 {paper_count} 篇论文：

{papers_info}

请输出 Markdown 对比表格。""",
    ),
])
