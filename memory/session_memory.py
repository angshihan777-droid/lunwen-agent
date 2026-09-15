"""
memory/session_memory.py — 对话记忆管理（多用户隔离版）

每个会话（session_id）拥有独立的 ConversationBufferWindowMemory 实例，
会话 ID 由 config._current_session ContextVar 提供。

记忆存放在带 TTL 的缓存中（见 session_store），闲置超时后随会话一并淘汰，
避免长期运行时内存无上限增长。
"""

from langchain.memory import ConversationBufferWindowMemory

from session_store import STORE_LOCK, new_session_cache, touch

_all_memories = new_session_cache()  # session_id -> ConversationBufferWindowMemory


def get_memory() -> ConversationBufferWindowMemory:
    from config import _current_session
    sid = _current_session.get()
    with STORE_LOCK:
        mem = touch(_all_memories, sid)
        if mem is None:
            mem = ConversationBufferWindowMemory(
                k=10,
                memory_key="chat_history",
                return_messages=True,
            )
            _all_memories[sid] = mem
        return mem


def reset_memory() -> None:
    from config import _current_session
    sid = _current_session.get()
    with STORE_LOCK:
        _all_memories.pop(sid, None)
