"""
tools/extract_tool.py — 结构化提取 Tool（多用户隔离版）

paper_texts 是一个会话代理对象：所有对它的 dict 操作都路由到当前会话
（由 config._current_session ContextVar 确定）的独立存储。

启动时 main.py 把演示论文写入 __default__ 会话；
之后每个新用户会话首次访问时自动复制这些演示论文，保证体验一致。

各会话的论文文本存放在带 TTL 的缓存中（见 session_store），闲置超时后自动淘汰；
__default__ 会话承载演示论文，容量上限内长期保留即可，超时后下次访问会重新复制。
"""

from langchain.tools import tool

from config import get_llm, _current_session
from prompts.extract_prompt import EXTRACT_PROMPT, parser
from schemas.paper_schema import PaperExtraction
from session_store import STORE_LOCK, new_session_cache, touch
from tools.errors import ToolError, tool_error_guard

_DEFAULT_SESSION = "__default__"
_all_paper_texts = new_session_cache()  # session_id -> {paper_id: full_text}


def _get_texts() -> dict:
    sid = _current_session.get()
    with STORE_LOCK:
        texts = touch(_all_paper_texts, sid)
        if texts is None:
            # 新会话：复制演示论文，让用户开箱即用
            defaults = _all_paper_texts.get(_DEFAULT_SESSION, {})
            texts = dict(defaults)
            _all_paper_texts[sid] = texts
        return texts


class _PaperTextsProxy:
    """代理对象，使 paper_texts 像普通 dict 一样使用，但实际读写当前会话存储。"""
    def __getitem__(self, key):       return _get_texts()[key]
    def __setitem__(self, key, val):  _get_texts()[key] = val
    def __contains__(self, key):      return key in _get_texts()
    def __iter__(self):               return iter(_get_texts())
    def keys(self):                   return _get_texts().keys()
    def values(self):                 return _get_texts().values()
    def items(self):                  return _get_texts().items()
    def pop(self, key, *args):        return _get_texts().pop(key, *args)
    def get(self, key, *args):        return _get_texts().get(key, *args)
    def __len__(self):                return len(_get_texts())


# 对外保持原有接口：from tools.extract_tool import paper_texts
paper_texts = _PaperTextsProxy()


@tool
def extract_tool(paper_id: str) -> str:
    """
    对指定论文执行结构化信息提取。
    返回包含研究问题、方法、数据集、指标、结论、局限性的 JSON 字符串。

    :param paper_id: 论文 ID（上传时返回的标识符）
    """
    texts = _get_texts()
    if paper_id not in texts:
        return f"错误：找不到论文 {paper_id}，请先上传。"

    text      = texts[paper_id]
    truncated = text[:6000] if len(text) > 6000 else text

    llm   = get_llm()
    chain = EXTRACT_PROMPT | llm | parser

    with tool_error_guard("extract_tool"):
        result: PaperExtraction = chain.invoke({"paper_text": truncated})
        import json
        return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
