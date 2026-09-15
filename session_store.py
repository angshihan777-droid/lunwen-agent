"""
session_store.py — 会话级存储的过期淘汰与并发保护

背景：原本 config / 论文文本 / 对话记忆 / 向量库都用普通 dict 按 session_id 存，
只增不减，长期运行内存会被无限占满，最终进程崩溃。

这里统一提供带 TTL 的缓存容器：
- 超过 SESSION_TTL 秒未被访问的会话，连同其全部数据一起淘汰；
- 同时保留的会话数不超过 SESSION_MAXSIZE，防止极端并发下内存无上限。

并发：/upload 的重活会被放到线程池执行（见 main.py），
届时缓存可能被工作线程与事件循环同时访问。TTLCache 的过期扫描不是原子操作，
故所有对缓存的"存在判断 + 读写"复合操作都必须在 STORE_LOCK 下进行。
"""

import threading

from cachetools import TTLCache

# 单个会话最长闲置时间（秒）；超过则其配置、论文、记忆、索引一并被清理
SESSION_TTL = 2 * 60 * 60  # 2 小时
# 最多同时保留的会话数，作为内存兜底上限
SESSION_MAXSIZE = 512

# 保护所有会话缓存的复合读写操作；跨线程访问时避免过期扫描期间的竞态
STORE_LOCK = threading.RLock()


def new_session_cache() -> TTLCache:
    """创建一个按会话隔离、带闲置过期与容量上限的存储容器。"""
    return TTLCache(maxsize=SESSION_MAXSIZE, ttl=SESSION_TTL)


def touch(cache: TTLCache, key):
    """
    刷新某会话条目的过期计时，实现"按最后访问时间淘汰"。

    TTLCache 默认按写入时间过期、读取不会续期；活跃用户若长时间读取同一会话，
    仍会在写入满 TTL 后被误清。这里通过重新写回条目重置其计时。
    调用方必须已持有 STORE_LOCK。返回该条目的值，键不存在时返回 None。
    """
    if key in cache:
        val = cache[key]
        cache[key] = val
        return val
    return None
