"""
AI 工具调用镜像插件 —— Flask 应用装配

职责：
1. 初始化运行时状态（工具实现模块、工具表、配置）
2. 注册各功能域蓝图与 CORS 响应头
3. 暴露 create_app() 供 server.py 与测试脚本使用

错误回传设计：
- 工具执行失败时返回完整堆栈（traceback）+ 错误分类（origin），
  让 AI 能区分「参数问题」与「环境问题」，据此改参数或改路径重试。
"""
import runtime
import tools_impl

# 各功能域蓝图
from routes.tools import bp as tools_bp
from routes.prompts import bp as prompts_bp
from routes.config_route import bp as config_bp
from routes.custom_tools import bp as custom_tools_bp
from routes.rules import bp as rules_bp
from routes.cards import bp as cards_bp
from routes.ext import bp as ext_bp
from routes.bridge import bp as bridge_bp
from routes.memory_graph import bp as memory_bp
from routes.memory_graph_page import bp as memory_page_bp
from routes.web import bp as web_bp
from routes.web_clientlog import bp as web_clientlog_bp


def _register_blueprints(app):
    """注册全部蓝图：工具、提示词、配置、自定义工具、规则、卡片与外部通道。"""
    app.register_blueprint(tools_bp)
    app.register_blueprint(prompts_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(custom_tools_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(cards_bp)
    app.register_blueprint(ext_bp)
    app.register_blueprint(bridge_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(memory_page_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(web_clientlog_bp)


def _register_options(app):
    """统一处理 CORS 预检（OPTIONS）：任何路径的预检一律返回 204。

    目的：各路由原先各自写「if request.method == \"OPTIONS\": return (\"\", 204)」，
    约 30 处重复。集中到应用层一处拦截，路由函数只管业务方法，重复消除。
    before_request 返回响应即短路，不再进入视图函数；after_request 仍会补 CORS 头。
    """
    @app.before_request
    def _options_preflight():
        from flask import request
        # 预检请求：直接回空 204，无需进入任何视图函数
        if request.method == "OPTIONS":
            return ("", 204)


def _register_cors(app):
    """统一响应头：允许跨域、禁用缓存。

    禁用缓存的原因：工具上下线、技能说明等状态变化需即时反映到前端。
    """
    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        # 默认禁缓存：工具上下线、技能说明等状态变化需即时反映到前端。
        # 例外：音频 / 图片文件名唯一、内容不变，放行以便浏览器长期缓存
        # （断网后可复播语音、免去重复下载）；这些接口已自带 max-age。
        from flask import request
        p = request.path or ""
        cacheable = p.startswith("/api/web/audio/") or p.startswith("/api/web/image-file/")
        if not cacheable:
            resp.headers["Cache-Control"] = "no-store"
        return resp


# 进行中的请求登记表：{ req_id: {start, method, path} }，供看门狗巡检。
# 由 _register_request_logging 的钩子写入，看门狗线程读取。
_inflight = {}
_inflight_lock = None


# 慢请求阈值（毫秒）：超过即告警，便于排查阻塞
_SLOW_MS = 1000


def _req_start_hook():
    """before_request 钩子：登记请求开始时间与短 id，并打一条进入日志。

    给每个请求一个短 id，串起同一请求的开始与结束。
    """
    import time
    import uuid
    import threading
    import app_log
    import ui_priority
    from flask import g, request
    g._req_t0 = time.time()
    g._req_id = uuid.uuid4().hex[:8]
    # 登记界面请求开始：后台维护据此让路（界面响应优先级最高）。
    ui_priority.ui_request_enter()
    with _inflight_lock:
        _inflight[g._req_id] = {
            "start": g._req_t0, "method": request.method, "path": request.path,
            "thread": threading.current_thread().name,
        }
    app_log.debug("[req][%s] -> %s %s" % (g._req_id, request.method, request.path))


def _req_end_hook(resp):
    """after_request 钩子：登记请求结束、算耗时；慢请求升级为 WARN。"""
    import time
    import app_log
    from flask import g, request
    t0 = getattr(g, "_req_t0", None)
    rid = getattr(g, "_req_id", "?")
    if t0 is None:
        return resp
    with _inflight_lock:
        _inflight.pop(rid, None)
    ms = (time.time() - t0) * 1000.0
    # 慢请求升级为 WARN，正常请求走 DEBUG（避免刷屏）
    line = "[req][%s] <- %s %s %d %.1fms" % (
        rid, request.method, request.path, resp.status_code, ms)
    if ms >= _SLOW_MS:
        app_log.warn(line)
    else:
        app_log.debug(line)
    return resp


def _register_request_logging(app):
    """请求耗时日志：注册开始/结束钩子，并初始化进行中请求登记表。

    目的：接口卡死时，日志能回答「哪个请求进来了、有没有出去、卡了多久」。
    慢请求（超过 _SLOW_MS）额外以 WARN 打一条，便于一眼捞出卡点。
    同时把进行中的请求登记到 _inflight，供看门狗在卡死时 dump 线程堆栈。
    """
    global _inflight_lock
    import threading
    _inflight_lock = threading.Lock()
    app.before_request(_req_start_hook)
    app.after_request(_req_end_hook)


def _register_watchdog(app, hang_seconds=150):
    """卡死看门狗：请求超过 hang_seconds 未返回时，dump 全部线程堆栈。

    目的：卡死时抓现场。此前只能看到「请求卡了多久」，看不到「卡在哪一行」；
    看门狗在超时后打印所有线程的调用栈，直接指出阻塞位置。

    阈值必须大于「工具调用的最长正常耗时」，否则正常的慢工具会被误报为卡死：
    内置工具兜底超时 60 秒（routes/tools.BUILTIN_TOOL_TIMEOUT），故取 150 秒留出余量。
    @param hang_seconds 判定卡死的阈值（秒）
    """
    import threading
    # 已 dump 过的请求 id：避免同一卡死请求每轮都刷日志
    dumped = set()
    threading.Thread(target=_watchdog_loop, args=(hang_seconds, dumped),
                     daemon=True, name="watchdog").start()


def _watchdog_dump_stacks(reason):
    """打印所有线程的调用栈到日志。

    @param reason 触发原因（写入日志前缀）
    """
    import sys
    import traceback
    import app_log
    frames = sys._current_frames()
    for tid, frame in frames.items():
        stack = "".join(traceback.format_stack(frame))
        app_log.error("[watchdog] %s 线程tid=%s 堆栈:\n%s" % (reason, tid, stack))


def _watchdog_loop(hang_seconds, dumped):
    """看门狗循环：每 3 秒巡检一次进行中请求，超时则 dump 全部线程堆栈。

    @param hang_seconds 判定卡死的阈值（秒）
    @param dumped       已 dump 过的请求 id 集合（就地累加，避免重复刷日志）
    """
    import time
    import app_log
    while True:
        time.sleep(3)
        now = time.time()
        with _inflight_lock:
            snapshot = list(_inflight.items())
        for rid, info in snapshot:
            if now - info["start"] < hang_seconds:
                continue
            if rid in dumped:
                continue
            dumped.add(rid)
            app_log.error(
                "[watchdog] 请求疑似卡死 %s %s（线程=%s，已 %.0fs），dump 全部线程堆栈"
                % (info["method"], info["path"], info["thread"], now - info["start"]))
            _watchdog_dump_stacks("卡死现场")


def _register_error_logging(app):
    """全局异常日志：任何未捕获异常都落盘，附请求路径与堆栈。

    目的：接口报错或卡死后崩掉时，日志里能看到原因，不用猜。
    """
    import traceback
    import app_log

    @app.errorhandler(Exception)
    def _log_uncaught(e):
        from flask import request
        from werkzeug.exceptions import HTTPException
        # HTTP 异常（如 404）属正常流程，不当作错误刷日志
        if isinstance(e, HTTPException):
            return e
        tb = traceback.format_exc()
        app_log.error("[req] 未捕获异常 %s %s : %s\n%s" % (
            request.method, request.path, e, tb))
        # 交给 Flask 默认处理，保持原有响应形态
        return ({"success": False, "error": str(e)}, 500)


def _register_db_teardown(app):
    """请求结束时关闭本线程的记忆库连接。

    目的：请求线程用过的 SQLite 连接及时释放，不再依赖「线程退出 + GC」
    的隐式回收时机。只关当前请求线程的连接，后台长期线程（调度、工具池）
    各自的连接不受影响。关闭后该线程下次再访问记忆库会按需重建。
    失败不阻断：连接关闭异常不影响响应返回。
    """
    @app.teardown_request
    def _close_db_conn(exc=None):
        # 登记界面请求结束：teardown 无论成功失败都会执行，
        # 放这里可避免请求异常时漏减计数、导致维护永久让路。
        try:
            import ui_priority
            ui_priority.ui_request_exit()
        except Exception:
            pass
        try:
            import memory_db
            memory_db.close_conn()
        except Exception as e:
            # 关连接失败不应影响请求收尾
            import app_log
            app_log.debug("[db] 请求结束关闭连接失败：%s" % e)


def _init_runtime():
    """初始化运行期状态：工具实现、工具表、配置与外部提供方。"""
    # 1) 注入工具实现模块，直接建立工具表与派发表
    runtime.impl = tools_impl
    runtime.TOOLS = dict(tools_impl.TOOLS)
    runtime.DISPATCH = dict(tools_impl.DISPATCH)
    # 2) 配置在工具就绪后初始化（需要 TOOLS）
    from config_store import init_config
    runtime.CONFIG = init_config()
    # 3) 加载外部工具提供方（executor=external 的工具按 provider 注册）
    runtime.refresh_external_providers()


def create_app():
    """构建并返回可用的 Flask 应用实例（重复调用会复用同一 runtime.app）。"""
    app = runtime.app
    _init_runtime()
    # 注册蓝图与响应头
    _register_blueprints(app)
    # 统一处理 CORS 预检（OPTIONS）：集中在应用层，省去各路由重复判断
    _register_options(app)
    _register_cors(app)
    # 请求耗时日志：排查接口卡死时，靠它还原「哪个请求卡了多久」
    _register_request_logging(app)
    # 卡死看门狗：请求超时未返回时 dump 全部线程堆栈，直接指出卡在哪一行
    _register_watchdog(app)
    # 全局异常日志：未捕获异常也落盘，避免只看到 500 却不知原因
    _register_error_logging(app)
    # 请求结束关闭本线程的记忆库连接：及时释放，不依赖 GC 时机
    _register_db_teardown(app)
    # 启动加载：把规则与记忆摘要一次性读进内存（方案核心目的）。
    # 失败不阻断启动：记忆库首次创建、或库损坏时，服务仍应可用。
    try:
        import memory_loader
        memory_loader.load_all()
    except Exception as e:
        app_log.warn("[memory]", "启动加载失败（不阻断服务）：", e)
    # 启动后台调度：周期性执行衰减与事件聚类（方案「事件层全自动」）。
    # 守护线程，不阻塞接口；失败不阻断服务。
    try:
        import memory_scheduler
        memory_scheduler.start_background_tasks()
    except Exception as e:
        app_log.warn("[memory]", "后台调度启动失败（不阻断服务）：", e)
    # 启动远程桥接（QQ ↔ 网页 AI）。失败不阻断服务启动：
    # 桥接是可选功能，凭证未填或依赖未装时其余功能照常可用。
    try:
        import remote_bridge
        remote_bridge.init_bridge()
    except Exception as e:
        app_log.warn("[bridge]", "启动失败（不阻断服务）：", e)
    return app
