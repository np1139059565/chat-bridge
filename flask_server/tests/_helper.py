"""测试公共辅助：统一处理导入路径。

作用：
- 把服务根目录（flask_server/）加入 sys.path，使测试能直接 import 被测模块；
- 提供统一的入口函数，供各测试文件在导入被测模块前调用。

约定：
- 各测试文件在最顶部、导入被测模块之前，先 `from _helper import ensure_path` 并调用；
- 这样即使从仓库根目录运行也能正确导入，不依赖当前工作目录。
"""
import os
import sys


def ensure_path():
    """把服务根目录（flask_server/）加入模块搜索路径。

    flask_server/ 是 tests/ 的上一级目录，被测模块都在它下面。
    重复调用是幂等的，不会重复插入。
    @returns 服务根目录的绝对路径
    """
    server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)
    return server_dir
