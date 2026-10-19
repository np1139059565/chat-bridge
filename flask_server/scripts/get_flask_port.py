#!/usr/bin/env python3
"""读取本地工具服务应使用的端口。

用途：
    供 start_server.cmd 在启动前确定目标端口，用于清理占用该端口的旧进程。
    单独成文件是为了避开 cmd 里嵌套引号调用 Python 的转义陷阱。

端口来源与 server.py 保持一致：
    config/runtime.yaml 的 flask.port → config/definition.yaml 的 app.flask.port
    → 服务端内置默认值 5000。

输出：
    仅向标准输出打印一个整型端口号，便于 cmd 的 for /f 直接取用。
"""
import os
import sys

# 默认端口，与服务端 server.py 中的兜底值保持一致
DEFAULT_PORT = 5000


def _load_yaml(path):
    """读取 YAML 文件并返回字典；文件缺失或解析失败时返回空字典。

    这里刻意吞掉异常：端口读取失败不应阻塞启动，交由调用方回退默认值。
    """
    try:
        import yaml
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _pick_port():
    """按优先级依次查找端口配置，返回第一个有效的整型端口。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 优先级一：运行时配置里的 flask.port
    runtime = _load_yaml(os.path.join(base, "config", "runtime.yaml"))
    flask_cfg = runtime.get("flask") or {}
    if isinstance(flask_cfg, dict) and flask_cfg.get("port"):
        return int(flask_cfg["port"])

    # 优先级二：定义文件里的 app.flask.port
    definition = _load_yaml(os.path.join(base, "config", "definition.yaml"))
    app_cfg = definition.get("app") or {}
    if isinstance(app_cfg, dict):
        flask_cfg = app_cfg.get("flask") or {}
        if isinstance(flask_cfg, dict) and flask_cfg.get("port"):
            return int(flask_cfg["port"])

    # 兜底：内置默认端口
    return DEFAULT_PORT


def main():
    """入口：打印解析出的端口号。"""
    try:
        print(_pick_port())
        return 0
    except Exception as exc:
        # 任何异常都回退默认端口，并只在标准错误里提示，避免污染 stdout
        print("读取端口失败，回退默认值：%s" % exc, file=sys.stderr)
        print(DEFAULT_PORT)
        return 0


if __name__ == "__main__":
    sys.exit(main())
