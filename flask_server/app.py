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
from routes.web import bp as web_bp


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
    app.register_blueprint(web_bp)


def _register_cors(app):
    """统一响应头：允许跨域、禁用缓存。

    禁用缓存的原因：工具上下线、技能说明等状态变化需即时反映到前端。
    """
    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp


def _register_request_logging(app):
    """请求耗时日志：记录每个请求的开始、结束与耗时。

    目的：接口卡死时，日志能回答「哪个请求进来了、有没有出去、卡了多久」。
    慢请求（超过 SLOW_MS）额外以 WARN 打一条，便于一眼捞出卡点。
    """
    import time as _time
    import app_log
    import uuid as _uuid

    # 慢请求阈值（毫秒）：超过即告警，便于排查阻塞
    SLOW_MS = 1000

    @app.before_request
    def _log_req_start():
        # 给每个请求一个短 id，串起同一请求的开始与结束
        from flask import g, request
        g._req_t0 = _time.time()
        g._req_id = _uuid.uuid4().hex[:8]
        app_log.debug("[req][%s] -> %s %s" % (g._req_id, request.method, request.path))

    @app.after_request
    def _log_req_end(resp):
        from flask import g, request
        t0 = getattr(g, "_req_t0", None)
        rid = getattr(g, "_req_id", "?")
        if t0 is None:
            return resp
        ms = (_time.time() - t0) * 1000.0
        # 慢请求升级为 WARN，正常请求走 DEBUG（避免刷屏）
        line = "[req][%s] <- %s %s %d %.1fms" % (
            rid, request.method, request.path, resp.status_code, ms)
        if ms >= SLOW_MS:
            app_log.warn(line)
        else:
            app_log.debug(line)
        return resp


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
    _register_cors(app)
    # 请求耗时日志：排查接口卡死时，靠它还原「哪个请求卡了多久」
    _register_request_logging(app)
    # 全局异常日志：未捕获异常也落盘，避免只看到 500 却不知原因
    _register_error_logging(app)
    # 启动加载：把规则与记忆摘要一次性读进内存（方案核心目的）。
    # 失败不阻断启动：记忆库首次创建、或库损坏时，服务仍应可用。
    try:
        import memory_loader
        memory_loader.load_all()
    except Exception as e:
        print("[memory] 启动加载失败（不阻断服务）：", e)
    # 启动后台调度：周期性执行衰减与事件聚类（方案「事件层全自动」）。
    # 守护线程，不阻塞接口；失败不阻断服务。
    try:
        import memory_scheduler
        memory_scheduler.start_background_tasks()
    except Exception as e:
        print("[memory] 后台调度启动失败（不阻断服务）：", e)
    # 启动远程桥接（QQ ↔ 网页 AI）。失败不阻断服务启动：
    # 桥接是可选功能，凭证未填或依赖未装时其余功能照常可用。
    try:
        import remote_bridge
        remote_bridge.init_bridge()
    except Exception as e:
        print("[bridge] 启动失败（不阻断服务）：", e)
    return app
