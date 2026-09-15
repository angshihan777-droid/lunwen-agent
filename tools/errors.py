"""
tools/errors.py — 工具层统一错误处理

背景：原先各工具把系统级异常直接 `return f"失败：{e}"`。
- 对直接调用的 endpoint：该字符串会被当成 200 正常结果返回，故障被伪装成成功；
- 对 ReAct Agent：该字符串会被当成正常 Observation 继续推理，真实错误被吞掉。

这里区分两类失败并分别处理：
1. 业务性失败（论文不存在、少于 2 篇等用户可纠正的问题）
   —— 仍由调用方返回明确的中文提示字符串，不进入本模块；
2. 系统性故障（LLM/网络/解析异常）
   —— 一律记录完整堆栈日志（loud），再按调用场景抛出或转成可见错误，
      绝不静默吞掉。

用法：
- 直接由 HTTP endpoint 调用的工具（extract/summary/compare/gap）用
  `with tool_error_guard(name):` 包裹外部调用；系统故障会被记日志并抛出
  ToolError，endpoint 侧据此返回 5xx，而不是把故障当成功。
- 由 Agent 调用、需保持对话继续的工具（arxiv/web_search/search）用
  `log_tool_failure(name, exc)`：记日志后返回一句可读提示，让 Agent 如实转告
  用户，同时错误已落到日志里可追查。
"""

import logging
from contextlib import contextmanager

logger = logging.getLogger("lunwen_agent.tools")


class ToolError(Exception):
    """工具执行过程中发生的系统级故障（区别于用户可纠正的业务性问题）。"""

    def __init__(self, tool_name: str, original: Exception):
        self.tool_name = tool_name
        self.original = original
        super().__init__(f"{tool_name} 执行失败：{type(original).__name__}: {original}")


@contextmanager
def tool_error_guard(tool_name: str):
    """
    包裹工具中的外部调用（LLM、网络等）。捕获到异常时记录完整堆栈日志，
    再抛出 ToolError，避免系统故障被伪装成正常结果。业务校验应在进入本
    上下文前完成，不要用它来兜业务分支。
    """
    try:
        yield
    except Exception as exc:  # noqa: BLE001 — 边界处统一记录并转译
        logger.exception("工具 %s 执行失败", tool_name)
        raise ToolError(tool_name, exc) from exc


def log_tool_failure(tool_name: str, exc: Exception) -> str:
    """
    记录工具系统级故障的完整堆栈，并返回一句可读的中文提示。
    用于 Agent 调用、需要保持对话继续的工具：错误已落日志可追查，
    同时让 Agent 如实告知用户失败原因，而不是把故障当成正常结果。
    """
    logger.exception("工具 %s 执行失败", tool_name)
    return f"{tool_name} 调用失败（{type(exc).__name__}）：{str(exc)[:150]}"
