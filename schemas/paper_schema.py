"""
schemas/paper_schema.py — Pydantic 数据模型

定义论文的结构化字段，LangChain PydanticOutputParser 用这个约束 LLM 输出，
确保 Agent 每次返回的是可解析的 JSON，而不是自由文本。
"""

from pydantic import BaseModel, Field


class PaperExtraction(BaseModel):
    """论文结构化提取结果——6 个核心字段"""

    research_problem: str = Field(
        description="论文要解决的核心问题或研究目标"
    )
    methodology: str = Field(
        description="论文采用的主要方法、模型或技术手段"
    )
    dataset: str = Field(
        description="实验使用的数据集，若无实验则填'无'"
    )
    metrics: str = Field(
        description="评估指标及关键实验结果（如 accuracy 92%）"
    )
    conclusion: str = Field(
        description="论文的主要结论和贡献"
    )
    limitations: str = Field(
        description="论文自身指出或明显存在的局限性"
    )
