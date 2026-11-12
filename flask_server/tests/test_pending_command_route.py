"""B-5 / 指令通道取件接口测试：/api/commands/pending。

覆盖点：
  1. 空队列返回空列表
  2. 指令通道条目可被取走；确认前可反复取
  3. target_page 归属过滤：定向条目只有目标页取得到
  4. 取件方未声明页面时只见不限页面的条目
  5. 与常规通道物理隔离：常规卡片不出现在指令取件里
  6. 带 page 取件会把该页面登记为在线

隔离策略：不调 create_app，只注册投递蓝图；两条通道各换空实例
（routes.cards 对两实例的绑定是模块级属性，整实例替换即可生效）。

运行方式（在 .\\flask_server\\ 目录下）：
    python -m pytest tests/test_pending_command_route.py -q
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import page_registry
from delivery_queue import DeliveryQueue
from routes.cards import bp as cards_bp


def _preflight_204():
    """预检请求直接 204，业务方法照常进入视图。"""
    from flask import request
    return ("", 204) if request.method == "OPTIONS" else None


@pytest.fixture(autouse=True)
def _clean_pages():
    """每用例前后清空页面登记，在线集合不渗漏到别的用例。"""
    page_registry.reset()
    yield
    page_registry.reset()


@pytest.fixture
def queues(monkeypatch):
    """两条通道各换空实例：用例互不污染，也不碰全局单例。"""
    from routes import cards as cards_mod
    cmd = DeliveryQueue()
    reg = DeliveryQueue()
    monkeypatch.setattr(cards_mod, "command_bus", cmd)
    monkeypatch.setattr(cards_mod, "bus", reg)
    return cmd, reg


@pytest.fixture
def pend_api():
    """最小应用：只挂投递蓝图，本组接口不读写桥接配置。"""
    app = Flask("b5_pending_test")
    app.register_blueprint(cards_bp)
    app.before_request(_preflight_204)
    yield app.test_client()


def _seed(bus, target=""):
    """往指定通道登记一条投递项，返回条目 id。"""
    return bus.create("bridge", "drawer-command", "t", "c", {}, target).id


def test_pending_empty_returns_empty_list(pend_api, queues):
    """空队列：成功且 cards 为空列表。"""
    body = pend_api.get("/api/commands/pending").get_json()
    assert body["success"] is True
    assert body["cards"] == []


def test_pending_returns_command_bus_items(pend_api, queues):
    """指令通道的条目可被取走；确认前可反复取。"""
    cmd_bus, _ = queues
    _seed(cmd_bus)
    first = pend_api.get("/api/commands/pending").get_json()
    assert len(first["cards"]) == 1
    again = pend_api.get("/api/commands/pending").get_json()
    assert len(again["cards"]) == 1


def test_pending_filters_by_target_page(pend_api, queues):
    """定向条目只有目标页面取得到，别的页面取不到。"""
    cmd_bus, _ = queues
    _seed(cmd_bus, target="https://a.example/chat")
    hit = pend_api.get("/api/commands/pending?page=https://a.example/chat")
    assert len(hit.get_json()["cards"]) == 1
    miss = pend_api.get("/api/commands/pending?page=https://b.example/chat")
    assert miss.get_json()["cards"] == []


def test_pending_without_page_gets_only_unbounded(pend_api, queues):
    """未声明页面：只取不限页面的条目，宁可少给不串台。"""
    cmd_bus, _ = queues
    _seed(cmd_bus)
    _seed(cmd_bus, target="https://a.example/chat")
    body = pend_api.get("/api/commands/pending").get_json()
    assert len(body["cards"]) == 1


def test_pending_isolated_from_regular_bus(pend_api, queues):
    """常规通道的卡片不出现在指令取件里：双通道物理隔离。"""
    _, reg_bus = queues
    _seed(reg_bus)
    body = pend_api.get("/api/commands/pending").get_json()
    assert body["cards"] == []


def test_pending_registers_page_online(pend_api, queues):
    """带 page 取件会把该页面登记进在线表（兜底登记副作用）。"""
    cmd_bus, _ = queues
    _seed(cmd_bus, target="https://a.example/chat")
    pend_api.get("/api/commands/pending?page=https://a.example/chat")
    assert "https://a.example/chat" in page_registry.online()
