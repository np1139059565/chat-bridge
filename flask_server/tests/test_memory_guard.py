"""记忆接口守卫：基础存储不受开关控制。

背景：曾把「记忆检查」开关挡在数据库连接层，导致开关关闭时
整条会话存储链路静默失效——前端保存会话返回成功，实际一条都没落库，
刷新后读不到历史、卡片状态全部丢失。

本文件守住两条契约：
  1. 会话存储类接口（会话树、会话列表、删除会话）永远放行；
  2. 记忆分析类接口（检索、衰减、事件）仍受开关控制。

运行：python -m pytest tests/test_memory_guard.py -q
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import paths  # noqa: F401  触发路径引导（把 core 加入搜索路径）
import memory_guard  # noqa: E402


def test_conversation_get_is_storage():
    """取会话属基础存储，不受开关控制。"""
    assert memory_guard.is_storage_path("/memory/conversation") is True


def test_conversation_delete_is_storage():
    """删会话属基础存储。"""
    assert memory_guard.is_storage_path("/memory/conversation/delete") is True


def test_conversation_list_is_storage():
    """会话列表属基础存储。"""
    assert memory_guard.is_storage_path("/memory/conversations") is True


def test_search_is_not_storage():
    """检索属记忆分析，受开关控制。"""
    assert memory_guard.is_storage_path("/memory/search") is False


def test_decay_is_not_storage():
    """衰减属记忆分析。"""
    assert memory_guard.is_storage_path("/memory/decay/run") is False


def test_events_is_not_storage():
    """事件图层属记忆分析。"""
    assert memory_guard.is_storage_path("/memory/events") is False


def test_prefix_not_confused():
    """前缀相近但不同名的路径不应误判为存储接口。"""
    # /memory/conversationxxx 不是会话接口
    assert memory_guard.is_storage_path("/memory/conversationxxx") is False
