"""
AI 工具调用镜像插件 —— 本地 Flask 工具服务（兼容入口）

服务实现已按职责拆分：
- runtime.py        运行期全局状态（app / impl / TOOLS / DISPATCH / CONFIG）
- config_store.py   config.yaml 读写与合并
- error_utils.py    错误分类与定位
- responses.py      错误响应辅助
- routes/           各功能域蓝图
- app.py            应用装配（create_app）

本文件保留原启动方式（python server.py），内部委托给 app.create_app()。
支持 --host / --port 命令行参数：用于「改端口后自重启」时把新端口直接传给
新进程，无需先写配置文件。命令行参数优先级高于 config.yaml。
"""
import argparse

import runtime
from app import create_app

# 构建应用（初始化工具表、配置、路由）
app = create_app()


def _parse_cli_args(argv=None):
    """解析命令行参数。仅识别 --host / --port，其余参数一概忽略，
    以免与 Flask 自身或其它调用方式冲突。
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    # 忽略未知参数：调用方（如重启逻辑）可能透传了不属于本服务的参数。
    args, _ = parser.parse_known_args(argv)
    return args


if __name__ == "__main__":
    # 端口 / 主机优先级：
    #   环境变量 CB_PORT（滚动重启注入） > 命令行 --port > config.yaml > 默认。
    # 环境变量最高，确保「改端口重启」时新进程一定用新端口，
    # 即便启动入口不解析命令行参数也能生效。
    import os as _os
    cli = _parse_cli_args()
    flask_cfg = runtime.CONFIG.get("flask", {})
    env_port = _os.environ.get("CB_PORT")
    host = cli.host or flask_cfg.get("host", "127.0.0.1")
    port = int(env_port) if env_port else (cli.port or flask_cfg.get("port", 5000))
    # threaded=True：卡片与外部工具均为同步阻塞，需并发承载
    app.run(host=host, port=port, debug=False, threaded=True)
