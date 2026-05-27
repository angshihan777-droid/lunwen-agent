"""
prompts/gap_prompt.py — 研究缺口识别 Prompt

任务：综合多篇论文，主动找出尚未解决的问题和研究空白。
这是最有差异化价值的功能——Agent 不只是总结，而是主动分析。
"""

from langchain_core.prompts import ChatPromptTemplate

GAP_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是一位资深学术研究专家，擅长发现研究领域的空白和未解决问题。

请综合分析多篇论文后，指出：
1. 这些论文共同关注但尚未完全解决的问题
2. 被所有论文忽略的角度或场景
3. 方法论上存在的共同局限
4. 未来研究最有价值的方向

要求：
- 具体，结合论文内容，不要泛泛而谈
- 用中文，分点输出
- 每点给出依据（"论文 A 和论文 B 都未涉及..."）""",
    ),
    (
        "human",
        """请分析以下 {paper_count} 篇论文的研究缺口：

{papers_info}

请输出结构化的研究缺口分析。""",
    ),
])
