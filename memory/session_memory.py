"""
memory/session_memory.py — 对话记忆管理（多用户隔离版）

每个会话（session_id）拥有独立的 ConversationBufferWindowMemory 实例，
会话 ID 由 config._current_session ContextVar 提供。
"""

from langchain.memory import ConversationBufferWindowMemory

_all_memories: dict = {}  # session_id -> ConversationBufferWindowMemory


def get_memory() -> ConversationBufferWindowMemory:
    from config import _current_session
    sid = _current_session.get()
    if sid not in _all_memories:
        _all_memories[sid] = ConversationBufferWindowMemory(
            k=10,
            memory_key="chat_history",
            return_messages=True,
        )
    return _all_memories[sid]


def reset_memory() -> None:
    from config import _current_session
    sid = _current_session.get()
    _all_memories.pop(sid, None)
