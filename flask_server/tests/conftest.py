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
def _enable_memory_switch():
    """自动打开记忆总开关，使全部测试不依赖本机真实配置。

    为什么需要：记忆系统总开关取自 runtime.yaml 的 check_memory。
    开发机上该开关可能正被用户关闭，若测试直接读真实配置，
    所有涉及记忆库的用例都会因「功能被关」而失败，测不到真实逻辑。

    做成全局自动夹具而非逐个用例设置：涉及记忆库的测试文件有十几个，
    逐个补既易漏、也会让每个文件多出前后两段样板代码。
    """
    import memory_switch
    memory_switch.set_override(True)
    yield
    # 收尾必须取消覆盖，否则会污染同进程内后续用例
    memory_switch.clear_override()


# 需要隔离到临时目录的运行时数据路径：全部是「用后可重建」的产物，
# 但测试若写进真实路径，就会污染用户数据（曾真实发生：跑测试后
# 网页会话里冒出数十条「文件已就绪」投递消息、下载目录塞满测试文件）。
_RUNTIME_DATA_ATTRS = (
    "WEB_DIR", "WEB_INBOX_PATH", "WEB_AUDIO_DIR", "WEB_IMAGES_DIR",
    "WEB_SEGMENTS_DIR", "WEB_FILES_DIR",
    "QQ_FILES_DIR", "QQ_IMAGES_DIR", "SCREENSHOTS_DIR", "VOICE_DIR",
)


@pytest.fixture(autouse=True)
def _isolate_runtime_data(tmp_path):
    """把所有运行时数据目录重定向到临时目录，测试永不写真实数据。

    为什么必须做：测试此前只重定向了记忆库，网页收件箱、下载目录、
    音频目录等全指向真实路径。任何碰到收件箱的测试都会写进用户真实数据，
    既污染现场、也让测试结果依赖上一次人工操作。

    重定向是逐个改模块变量而非改 DATA_DIR：各路径在 import 时已推导完成，
    改父目录不会影响子路径变量，必须逐个覆盖才真正生效。

    @param tmp_path pytest 为每个用例生成的独立临时目录
    """
    import paths
    saved = {}
    root = tmp_path / "data"
    for attr in _RUNTIME_DATA_ATTRS:
        if not hasattr(paths, attr):
            continue
        saved[attr] = getattr(paths, attr)
        # 每个目录都放到临时根下，保持与真实布局同构，便于排查
        setattr(paths, attr, root / attr.lower())
    yield
    # 还原：模块级变量改了必须改回，否则后续用例仍指向临时目录
    for attr, val in saved.items():
        setattr(paths, attr, val)


@pytest.fixture(autouse=True)
def _isolate_active_channel(tmp_path):
    """把「最近活跃渠道」隔离到临时文件，并复位内存状态。

    为什么需要：该状态已落盘，测试若读真实文件，会受开发机上
    「上次是谁在说话」影响——本机可能正停在 web，导致推送分支断言失败。
    不隔离就变成「测试结果取决于上一次人工操作」，属不可接受的随机失败。

    @param tmp_path pytest 为每个用例生成的独立临时目录
    """
    # 必须用与业务代码相同的导入路径（core/ 已在 sys.path，
    # `import core.active_channel` 与 `import active_channel` 是两个不同的模块对象，
    # 改错对象等于没改）。
    import active_channel as ac
    old_path = ac._STATE_PATH
    old_channel = ac._channel
    old_loaded = ac._loaded
    # 指向一个不存在的临时文件：等价于「尚无任何客户端发过消息」
    ac._STATE_PATH = tmp_path / "active_channel.txt"
    ac._channel = ""
    ac._loaded = True   # 标记已加载，避免 get() 去读旧路径
    yield
    # 还原：模块级变量改了必须改回，否则后续用例仍指向临时目录
    ac._STATE_PATH = old_path
    ac._channel = old_channel
    ac._loaded = old_loaded


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
