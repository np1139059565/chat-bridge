"""
AI 工具调用镜像插件 —— 本地 Flask 工具服务（兼容入口）

服务实现已按职责拆分：
- runtime.py        运行期全局状态（app / impl / TOOLS / DISPATCH / CONFIG）
- config_store.py   config.yaml 读写与合并
- error_utils.py    错误分类与定位
- self_healing.py   自愈工具与热重载
- responses.py      错误响应辅助
- routes/           各功能域蓝图
- app.py            应用装配（create_app）

本文件保留原启动方式（python server.py），内部委托给 app.create_app()。
"""
import runtime
from app import create_app

# 构建应用（初始化工具表、配置、路由）
app = create_app()

if __name__ == "__main__":
    # 关闭 reloader：热重载由 hot_reload_fix 精确控制，避免与调试重载器打架
    # 端口来自 config.yaml（flask.port），修改后需重启服务
    flask_cfg = runtime.CONFIG.get("flask", {})
    # threaded=True：卡片与外部工具均为同步阻塞，需并发承载
    app.run(host=flask_cfg.get("host", "127.0.0.1"), port=flask_cfg.get("port", 5000),
            debug=False, threaded=True)
