"""
agents/research_agent.py — 论文研究 Agent 主逻辑

架构：ReAct Agent（Reason + Act）
- 不依赖 OpenAI function calling，兼容任意 OpenAI 兼容模型
- 推理格式：Thought → Action → Action Input → Observation → Final Answer

Prompt 设计分两层：
  静态层：Agent 身份、工具说明、行为准则（写死在这里）
  动态层：当前会话上下文（由 run_agent 调用方注入，每次调用时变化）
"""

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain.callbacks.base import BaseCallbackHandler

from config import get_llm
from memory.session_memory import get_memory

from tools.extract_tool import extract_tool
from tools.summary_tool import summary_tool
from tools.search_tool import search_tool
from tools.compare_tool import compare_tool
from tools.gap_tool import gap_tool
from tools.citation_tool import citation_tool
from tools.arxiv_tool import arxiv_tool
from tools.web_search_tool import web_search_tool

ALL_TOOLS = [
    extract_tool,
    summary_tool,
    search_tool,
    compare_tool,
    gap_tool,
    citation_tool,
    arxiv_tool,
    web_search_tool,
]

# ── Prompt 模板 ─────────────────────────────────────────────
#
# 固定占位符（由 LangChain ReAct 框架自动填充）：
#   {tools}            — 所有工具的名称 + docstring
#   {tool_names}       — 仅工具名称列表
#   {input}            — 用户本轮输入
#   {chat_history}     — Memory 维护的对话历史
#   {agent_scratchpad} — 模型的推理草稿（Thought/Action/Observation 循环）
#
# 自定义占位符（由 run_agent 在调用前 .partial() 预填）：
#   {context}          — 当前会话上下文（论文列表、当前聚焦论文等）
#
REACT_PROMPT = PromptTemplate.from_template(
    """你是「论文研究助手」，一个专为学术研究者设计的 AI 分析工具。
你的目标是帮助用户快速理解、提取、对比和分析学术论文，输出有价值的研究洞察。

## 当前工作上下文
{context}

## 你拥有的工具
{tools}

## 工具使用指引
| 任务类型               | 应使用的工具       | 输入格式              |
|------------------------|--------------------|-----------------------|
| 提取论文结构化信息     | extract_tool       | paper_id              |
| 生成通俗摘要           | summary_tool       | paper_id              |
| 对比多篇论文           | compare_tool       | paper_id1,paper_id2,… |
| 识别研究缺口           | gap_tool           | paper_id1,paper_id2,… |
| 在已上传论文中语义检索 | search_tool        | 自然语言查询          |
| 提取参考文献列表       | citation_tool      | paper_id              |
| 搜索 ArXiv 论文        | arxiv_tool         | 关键词                |
| 网络搜索最新信息       | web_search_tool    | 关键词                |

## 行为准则
1. **不编造**：所有关于论文的具体内容（数据、结论、方法）必须通过工具获取，禁止自行生成
2. **用工具**：涉及论文的任何分析任务必须调用对应工具，不可凭记忆直接回答
3. **说清楚**：若论文未加载、工具调用失败或信息不足，直接告知用户原因和解决办法
4. **中文优先**：始终用流畅的中文回答；专业术语（如 BLEU、Transformer）可保留英文

## 输出格式（ReAct，严格遵守）

情况 A——需要使用工具：
Thought: 分析问题，决定调用哪个工具
Action: 工具名称（必须是 [{tool_names}] 之一）
Action Input: 传给工具的参数
Observation: 工具返回的结果
...（可多轮 Thought / Action / Observation）
Thought: 已获得足够信息
Final Answer: 最终回答

情况 B——不需要工具（闲聊、解释性问题、已知信息）：
Thought: 这个问题不需要工具，我可以直接回答
Final Answer: 最终回答

⚠️ 无论哪种情况，必须以 "Final Answer:" 结束，禁止在没有 Final Answer 的情况下停止输出。

## 历史对话
{chat_history}

Question: {input}
Thought: {agent_scratchpad}"""
)


# ── 步骤收集器 ────────────────────────────────────────────────

class StepCollector(BaseCallbackHandler):
    """
    LangChain 回调：收集 Agent 每一步的执行记录。
    每次工具调用的开始和结束都会触发，结果存入 self.steps。
    run_agent() 把 steps 一起返回给前端，供右侧 Plan 面板渲染。
    """

    def __init__(self):
        self.steps: list[dict] = []

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        self.steps.append({
            "type": "tool_start",
            "tool": serialized.get("name", "unknown_tool"),
            "input": str(input_str)[:200],
        })

    def on_tool_end(self, output: str, **kwargs):
        preview = str(output)[:150] + ("..." if len(str(output)) > 150 else "")
        self.steps.append({
            "type": "tool_end",
            "output": preview,
        })

    def on_agent_action(self, action, **kwargs):
        self.steps.append({
            "type": "thought",
            "tool": action.tool,
            "log": action.log.strip()[:200] if action.log else "",
        })


# ── Agent 工厂 ────────────────────────────────────────────────

def get_agent_executor(collector: StepCollector, context: str = "") -> AgentExecutor:
    """
    创建 AgentExecutor。
    :param collector: 步骤收集器，用于可视化
    :param context:   当前会话上下文字符串（已加载论文列表等），
                      通过 prompt.partial() 预填到 {context} 占位符
    """
    llm    = get_llm()
    memory = get_memory()

    # 用 partial 预填动态上下文，create_react_agent 不需要知道 {context}
    filled_prompt = REACT_PROMPT.partial(
        context=context if context.strip() else "当前没有已加载的论文，请提示用户上传 PDF。"
    )

    agent = create_react_agent(
        llm=llm,
        tools=ALL_TOOLS,
        prompt=filled_prompt,
    )

    return AgentExecutor(
        agent=agent,
        tools=ALL_TOOLS,
        memory=memory,
        verbose=False,                   # 关掉 stdout（Windows GBK 路径会乱码）
        max_iterations=8,                # 给复杂多工具任务留足空间
        early_stopping_method="generate", # 超限时让 LLM 自己写 Final Answer，不返回报错字符串
        handle_parsing_errors="输出格式有误，请严格按照 Thought/Action/Action Input 或 Thought/Final Answer 格式重新输出。",
        callbacks=[collector],
    )


def run_agent(user_input: str, context: str = "") -> dict:
    """
    运行完整 ReAct Agent（多工具链路），返回包含最终回答和执行步骤的字典。
    仅在需要主动调用工具时使用；日常对话请用更快的 run_chat()。
    """
    collector = StepCollector()
    executor  = get_agent_executor(collector, context=context)
    result    = executor.invoke({"input": user_input})
    return {
        "output": result["output"],
        "steps":  collector.steps,
    }


def run_chat(user_input: str, context: str = "") -> dict:
    """
    轻量级对话模式：**单次** LLM 调用，无 ReAct 循环。
    适用于 /chat 的日常问答（解释、追问、总结等）。
    结构化分析任务（提取/摘要/对比/缺口）已有独立快捷按钮，不走这里。

    速度对比：ReAct ≈ 2-3 次 API 调用；run_chat ≈ 1 次 API 调用，快 2-3 倍。
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    llm    = get_llm()
    memory = get_memory()

    system_content = f"""你是「论文研究助手」，专门帮助学术研究者理解、分析论文。请用中文回答，表达流畅专业。

## 当前工作上下文
{context if context.strip() else "当前没有已加载的论文。"}

## 提示
如需结构化提取、摘要、多篇对比、研究缺口分析，建议使用左侧快捷操作按钮——那些操作已针对性优化，结果更精准。
你的职责是回答用户的追问、解释专业概念、总结要点、辅助思考。"""

    # 从 Memory 取历史消息（return_messages=True → BaseMessage 列表）
    history = memory.load_memory_variables({}).get("chat_history", [])

    messages = [SystemMessage(content=system_content)] + history + [HumanMessage(content=user_input)]

    response = llm.invoke(messages)
    answer   = response.content

    # 存回 Memory，保持对话连续性
    memory.save_context({"input": user_input}, {"output": answer})

    return {
        "output": answer,
        "steps":  [{"type": "thought", "tool": "direct_llm",
                    "log": "直接对话模式（1 次 LLM 调用）"}],
    }
