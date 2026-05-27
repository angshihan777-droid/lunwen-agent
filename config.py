"""
config.py — 全局配置与 API Key 管理

每个请求通过 X-Session-ID 头携带会话 ID。
_current_session ContextVar 由 main.py 中的 HTTP 中间件在每次请求开始时写入，
所有工具函数、Memory、LLM 实例均通过 _get_cfg() 读取当前会话的配置，
实现多用户隔离（部署到公网后每个浏览器 tab 拥有独立的密钥与论文列表）。
"""

import os
from contextvars import ContextVar
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# 当前请求的会话 ID；由 main.py 中间件在每次请求开始时写入
_current_session: ContextVar[str] = ContextVar("current_session", default="__default__")

# 每个会话独立的配置字典
_sessions_config: dict = {}


def _get_cfg() -> dict:
    sid = _current_session.get()
    if sid not in _sessions_config:
        _sessions_config[sid] = {
            "llm_provider":   os.getenv("LLM_PROVIDER", "openai"),
            "llm_api_key":    os.getenv("OPENAI_API_KEY", ""),
            "llm_base_url":   os.getenv("LLM_BASE_URL", ""),
            "llm_model":      os.getenv("LLM_MODEL", ""),
            "tavily_api_key": os.getenv("TAVILY_API_KEY", ""),
        }
    return _sessions_config[sid]


class _SessionProxy:
    """让 session_config 像 dict 一样使用，但实际读写当前会话的存储。"""
    def __getitem__(self, key):          return _get_cfg()[key]
    def __setitem__(self, key, value):   _get_cfg()[key] = value
    def __contains__(self, key):         return key in _get_cfg()
    def get(self, key, default=None):    return _get_cfg().get(key, default)


# 保持对外接口不变
session_config = _SessionProxy()


def update_config(
    llm_provider: str,
    llm_api_key: str,
    tavily_api_key: str,
    llm_base_url: str = "",
    llm_model: str = "",
) -> None:
    cfg = _get_cfg()
    cfg["llm_provider"]   = llm_provider
    cfg["llm_api_key"]    = llm_api_key
    cfg["llm_base_url"]   = llm_base_url
    cfg["llm_model"]      = llm_model
    cfg["tavily_api_key"] = tavily_api_key


def get_llm():
    cfg      = _get_cfg()
    provider = cfg["llm_provider"]
    api_key  = cfg["llm_api_key"]
    model    = cfg["llm_model"]

    if not api_key:
        raise ValueError("API Key 未设置，请在前端设置面板填写。")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model or "claude-3-5-sonnet-20241022",
            api_key=api_key,
            temperature=0,
        )

    from langchain_openai import ChatOpenAI

    if provider == "deepseek":
        base_url      = DEEPSEEK_BASE_URL
        default_model = "deepseek-chat"
    elif provider == "custom":
        base_url = cfg["llm_base_url"]
        if not base_url:
            raise ValueError("使用中转站时请填写 Base URL。")
        default_model = "gpt-4o"
    else:
        base_url      = None
        default_model = "gpt-4o"

    return ChatOpenAI(
        model=model or default_model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


def get_tavily_key() -> str:
    key = _get_cfg()["tavily_api_key"]
    if not key:
        raise ValueError("Tavily API Key 未设置，请在前端设置面板填写。")
    return key
