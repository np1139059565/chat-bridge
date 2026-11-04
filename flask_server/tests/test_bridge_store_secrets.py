"""桥接配置 —— 凭证字段的保存语义测试

为什么需要：
    前端保存桥接配置是全量提交，它会把内存里的 app_id / app_secret 一并回写。
    若此刻内存尚未从后端取回（加载未完成、加载失败），或用户只是点了某个开关，
    提交上来的凭证就是空串。后端若「见键就写」，会把已存的凭证清成空，
    表现为设置页输入框变空、连接随即断开，而用户没有任何操作失误。

    本文件把这个语义钉死：空串表示「保持原值」，不是「清空」。

运行：python -m pytest tests/test_bridge_store_secrets.py -q
"""
import os
import sys

import pytest

# 把 flask_server 加进导入路径：本文件可单独运行，
# 不依赖全量运行时其它测试文件先做的路径引导。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def store(tmp_path, monkeypatch):
    """把配置读写重定向到临时目录，并清掉内存缓存。

    配置路径是模块级变量，import 时已解析完成，故须逐个替换；
    内存缓存 _CONFIG 也要重置，否则用例之间会共享同一份字典。

    @param tmp_path  pytest 提供的独立临时目录
    @param monkeypatch pytest 的补丁工具
    @returns 已隔离的 bridge_store 模块
    """
    import config_file
    from remote_bridge import bridge_store as bs

    # 两份配置文件都指向临时目录，测试不碰真实配置
    monkeypatch.setattr(config_file, "DEFINITION_PATH", tmp_path / "definition.yaml")
    monkeypatch.setattr(config_file, "RUNTIME_PATH", tmp_path / "runtime.yaml")
    # 清掉内存缓存，确保读到的是刚写入的临时文件
    monkeypatch.setattr(bs, "_CONFIG", None)
    return bs


def test_empty_secret_does_not_clear_saved_value(store):
    """空串不覆盖已存凭证：这是本文件要钉住的核心行为。"""
    # 先存一份真实凭证
    store.save_config({"app_id": "real-app-id", "app_secret": "real-secret"})
    # 模拟前端全量提交时凭证为空（加载未完成 / 只改了开关）
    cfg = store.save_config({"app_id": "", "app_secret": "", "enabled": True})
    # 凭证应保持原值，不被空串清掉
    assert cfg["app_id"] == "real-app-id"
    assert cfg["app_secret"] == "real-secret"
    # 同批的开关变更照常生效
    assert cfg["enabled"] is True


def test_non_empty_secret_overwrites(store):
    """非空值正常覆盖：保护逻辑不能挡住真正的修改。"""
    store.save_config({"app_id": "old-id", "app_secret": "old-secret"})
    cfg = store.save_config({"app_id": "new-id", "app_secret": "new-secret"})
    assert cfg["app_id"] == "new-id"
    assert cfg["app_secret"] == "new-secret"


def test_empty_secret_survives_roundtrip(store):
    """保护后的值要真正落盘：重新读盘仍是原值。"""
    store.save_config({"app_id": "keep-id", "app_secret": "keep-secret"})
    store.save_config({"app_id": "", "app_secret": ""})
    # 清缓存强制重新读盘，验证写下去的就是保留后的值
    store._CONFIG = None
    cfg = store.get_config()
    assert cfg["app_id"] == "keep-id"
    assert cfg["app_secret"] == "keep-secret"
