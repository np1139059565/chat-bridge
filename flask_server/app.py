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
from routes.memory import bp as memory_bp
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
    # 启动远程桥接（QQ ↔ 网页 AI）。失败不阻断服务启动：
    # 桥接是可选功能，凭证未填或依赖未装时其余功能照常可用。
    try:
        import remote_bridge
        remote_bridge.init_bridge()
    except Exception as e:
        print("[bridge] 启动失败（不阻断服务）：", e)
    return app
