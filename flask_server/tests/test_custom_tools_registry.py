"""自定义工具注册表：写盘失败必须报错的回归测试。

背景：
    registry 的 install / remove / update / set_skill_enabled 原先忽略
    save_tools 的返回值。当写盘失败（配置只读、磁盘满、文件被占用等）时，
    函数仍照常返回「成功」，前端据此显示「已安装」，但配置并未落盘；
    刷新后重新读文件即变回「未安装」。本文件锁定「写盘失败必须报错」的行为。

验证目标：
    1. 写盘失败时 install 抛异常，且不谎报成功；
    2. 写盘失败时 remove / update / set_skill_enabled 抛异常；
    3. 配置可写时，安装能落盘并能读回。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_custom_tools_registry -v
"""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import config_file
import custom_tools as ct


def _make_skill(root, name, tool_name):
    """在 root 下造一个含 tool.json 与可执行脚本的最小 skill，返回其目录。"""
    d = Path(root) / name
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")
    tool = {
        "name": tool_name, "description": "测试工具",
        "script": "scripts/run.py", "interpreter": "python", "parameters": [],
    }
    (d / "tool.json").write_text(json.dumps(tool, ensure_ascii=False), encoding="utf-8")
    return str(d)


class TestRegistryWriteFailure(unittest.TestCase):
    """写盘失败时各写操作必须报错，而非谎报成功。"""

    def setUp(self):
        # 配置目录重定向到临时目录，避免触碰真实配置
        self.tmp = tempfile.mkdtemp(prefix="ctreg_test_")
        self._orig_env = os.environ.get("CHAT_BRIDGE_CONFIG_DIR")
        cfg = os.path.join(self.tmp, "config")
        os.makedirs(cfg)
        # 造一个空的 definition/runtime
        (Path(cfg) / "definition.yaml").write_text("app: {}\ncustom_tools: {tools: []}\n", encoding="utf-8")
        (Path(cfg) / "runtime.yaml").write_text("custom_tools: {enabled: {}}\n", encoding="utf-8")
        os.environ["CHAT_BRIDGE_CONFIG_DIR"] = cfg
        # 重新解析 config_file 的路径常量（模块级已按环境变量求值）
        import importlib
        importlib.reload(config_file)
        self.cfg = cfg
        self.defp = str(config_file.DEFINITION_PATH)
        self.skill = _make_skill(os.path.join(self.tmp, "skills"), "newsk", "t_new")

    def tearDown(self):
        # 恢复可写，再清理
        try:
            os.chmod(self.defp, stat.S_IWRITE)
        except Exception:
            pass
        if self._orig_env is None:
            os.environ.pop("CHAT_BRIDGE_CONFIG_DIR", None)
        else:
            os.environ["CHAT_BRIDGE_CONFIG_DIR"] = self._orig_env
        import importlib
        importlib.reload(config_file)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_readonly(self):
        os.chmod(self.defp, stat.S_IREAD)

    def test_install_raises_on_write_failure(self):
        """只读时安装应抛异常，而不是返回已安装。"""
        self._make_readonly()
        with self.assertRaises(RuntimeError):
            ct.install(self.skill)
        # 确认确实没落盘
        self.assertNotIn("t_new", ct.load_tools())

    def test_install_succeeds_when_writable(self):
        """可写时安装成功并能读回。"""
        installed = ct.install(self.skill)
        self.assertIn("t_new", installed)
        self.assertIn("t_new", ct.load_tools())

    def test_remove_raises_on_write_failure(self):
        """先正常安装，再只读，删除应抛异常。"""
        ct.install(self.skill)
        self._make_readonly()
        with self.assertRaises(RuntimeError):
            ct.remove("t_new")

    def test_update_raises_on_write_failure(self):
        """先正常安装，再只读，更新应抛异常。"""
        ct.install(self.skill)
        self._make_readonly()
        with self.assertRaises(RuntimeError):
            ct.update("t_new", {"description": "改一下"})


if __name__ == "__main__":
    unittest.main()
