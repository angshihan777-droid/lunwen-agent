"""
prompts/extract_prompt.py — 结构化提取 Prompt

任务：从论文文本中提取 6 个核心字段。
使用 PydanticOutputParser 将输出格式指令自动注入 prompt，
确保 LLM 输出可以被解析为 PaperExtraction 对象。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from schemas.paper_schema import PaperExtraction

# 创建解析器，它会自动生成"请按以下 JSON 格式输出"的指令
parser = PydanticOutputParser(pydantic_object=PaperExtraction)

EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是一位专业的学术论文分析助手。
请仔细阅读以下论文内容，提取关键信息。
要求：准确、简洁，用中文回答，每个字段不超过 150 字。

{format_instructions}""",
    ),
    (
        "human",
        """请分析以下论文内容：

{paper_text}

请按格式提取上述 6 个字段。""",
    ),
]).partial(format_instructions=parser.get_format_instructions())
