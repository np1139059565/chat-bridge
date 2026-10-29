"""pytest 全局夹具

为什么需要这个文件：
    微信推送路由用进程内字典记录「回复池」与「最近用户」，这些状态会跨用例残留，
    导致顺序相关的假失败（例如前一个用例设置了目标用户，后一个「无目标」用例
    就测不出预期）。

    这类清理必须放在 conftest.py：autouse 夹具只有定义在这里才对整个
    测试目录生效；定义在普通模块里只对该模块内生效，其它文件完全不受影响——
    这正是「夹具写了但没起作用」的典型坑。
"""
import pytest


@pytest.fixture(autouse=True)
def _clean_weixin_router_state():
    """每个用例前后清空微信推送路由的进程内状态。

    只清微信路由的两个字典，不碰其它模块：
    清空动作对无关用例无副作用，因此可以安全地全局 autouse。
    """
    from remote_bridge import weixin_router as router
    router._quota.clear()
    router._last_user = ""
    yield
    router._quota.clear()
    router._last_user = ""
