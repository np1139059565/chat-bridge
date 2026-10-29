"""pytest 全局夹具

为什么需要这个文件：
    微信推送路由与桥接存储都带进程内状态和磁盘状态，若不隔离会造成两类问题：
    1. 用例之间互相污染——前一个用例留下的配额、推送目标影响后一个用例；
    2. 测试写进生产数据——状态文件路径是生产路径，测试的假用户 id 与已推
       记录会写进真实文件，线上随后拿着不存在的用户去发送、每次都被拒。
       这个坑真实发生过。

    因此本夹具把桥接状态文件整体重定向到每个用例独立的临时目录，
    并在前后清空内存缓存。这样测试彻底不碰生产文件，用例之间也互不影响。
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_bridge_state(tmp_path):
    """把桥接状态文件重定向到临时目录，并清空内存状态。

    重定向必须覆盖「读」与「写」两条路径：bridge_store 的 _state_path()
    每次调用都解析模块变量，故改模块变量即可同时影响读写。

    @param tmp_path pytest 为每个用例生成的独立临时目录
    """
    from remote_bridge import bridge_store as bs
    from remote_bridge import weixin_router as router

    # 保存原路径，用例结束还原，避免影响其它测试文件
    old_path = bs.BRIDGE_STATE_PATH
    old_pushed = bs._pushed

    # 重定向到临时文件：该文件初始不存在，等价于「干净状态」
    bs.BRIDGE_STATE_PATH = tmp_path / "bridge_state.json"
    bs._pushed = None
    router._quota.clear()
    router._last_user = ""

    yield

    # 还原：模块级变量改了必须改回，否则后续用例仍指向临时目录
    bs.BRIDGE_STATE_PATH = old_path
    bs._pushed = old_pushed
    router._quota.clear()
    router._last_user = ""
