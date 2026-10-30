"""push_file 工具：校验与推送分支的测试。

覆盖四类拒绝分支（缺参、文件不存在、类型不在白名单、体积超限）
与桥接未就绪分支，确认这些情况都抛出参数错误而不是静默失败。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_push_file -v
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发 core/ 与 tools/ 的路径引导
import runtime
from tool_helpers import ToolParamError
import push_file_impl
from push_file_impl import t_push_file
# 白名单已改为复用 read_file 那一套（file_types.PASTEABLE_EXTS），
# 故断言对象也从 push_file_impl 改到公共清单，验证两者确实同源。
from file_types import PASTEABLE_EXTS


class TestPushFileValidation(unittest.TestCase):
    """参数与文件本身的校验分支。"""

    def setUp(self):
        """准备一个临时目录，用于放置各类测试文件。"""
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        """清理临时目录。"""
        self._tmp.cleanup()

    def _touch(self, name, size=8):
        """在临时目录下创建指定大小（字节）的文件，返回路径。"""
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(b"x" * size)
        return p

    def test_missing_path_raises(self):
        """缺少 path 参数应抛参数错误。"""
        with self.assertRaises(ToolParamError):
            t_push_file({})

    def test_nonexistent_file_raises(self):
        """文件不存在时应抛参数错误并指出路径。"""
        with self.assertRaises(ToolParamError) as ctx:
            t_push_file({"path": os.path.join(self.tmp, "nope.zip")})
        self.assertIn("文件不存在", str(ctx.exception))

    def test_disallowed_extension_raises(self):
        """扩展名不在白名单时，应按「不支持」拒绝。

        用 .xyz：它不在公共白名单内，能稳定走到「不在白名单」这条分支。
        """
        p = self._touch("a.xyz")
        with self.assertRaises(ToolParamError) as ctx:
            t_push_file({"path": p})
        self.assertIn("不支持的文件类型", str(ctx.exception))

    def test_no_extension_raises(self):
        """无扩展名文件应被拒绝。"""
        p = self._touch("LICENSE")
        with self.assertRaises(ToolParamError) as ctx:
            t_push_file({"path": p})
        self.assertIn("不支持的文件类型", str(ctx.exception))

    def test_oversize_file_raises(self):
        """超过体积上限时应被拒绝。"""
        p = self._touch("big.zip", size=2048)
        # 把上限压到 1KB，使 2KB 的文件必然超限
        with mock.patch.object(push_file_impl, "_max_bytes", return_value=1024):
            with self.assertRaises(ToolParamError) as ctx:
                t_push_file({"path": p})
        self.assertIn("文件过大", str(ctx.exception))

    def test_bridge_not_ready_raises(self):
        """桥接无客户端 / 无目标时，应提示先在手机发一条消息。"""
        p = self._touch("ok.md")
        with mock.patch("remote_bridge.message_router.get_last_client", return_value=None), \
             mock.patch("remote_bridge.message_router.get_last_openid", return_value=""):
            with self.assertRaises(ToolParamError) as ctx:
                t_push_file({"path": p})
        self.assertIn("远程桥接尚未就绪", str(ctx.exception))


class TestPushFileSuccess(unittest.TestCase):
    """推送成功与失败回传两条路径。"""

    def setUp(self):
        """准备临时目录与一个合法的 md 文件。"""
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.md = os.path.join(self._tmp.name, "note.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("# hi\n")

    def tearDown(self):
        """清理临时目录。"""
        self._tmp.cleanup()

    def test_success_returns_pushed_true(self):
        """发送成功时结果标记 pushed 为真，并带回文件名与体积。"""
        sentinel = object()
        with mock.patch("remote_bridge.message_router.get_last_client", return_value=sentinel), \
             mock.patch("remote_bridge.message_router.get_last_openid", return_value="openid-x"), \
             mock.patch("remote_bridge.message_router.push_file", return_value=(True, {})):
            res = t_push_file({"path": self.md})
        self.assertTrue(res["pushed"])
        self.assertEqual(res["name"], "note.md")
        self.assertEqual(res["target"], "QQ")

    def test_failure_reports_reason(self):
        """发送失败时结果标记 pushed 为假，并带回失败原因。"""
        with mock.patch("remote_bridge.message_router.get_last_client", return_value=object()), \
             mock.patch("remote_bridge.message_router.get_last_openid", return_value="openid-x"), \
             mock.patch("remote_bridge.message_router.push_file",
                        return_value=(False, "窗口已关闭")):
            res = t_push_file({"path": self.md})
        self.assertFalse(res["pushed"])
        self.assertEqual(res["error"], "窗口已关闭")


class TestAllowedExts(unittest.TestCase):
    """白名单来源的约定。"""

    def test_reuses_pasteable_list(self):
        """推送白名单必须与 read_file 的可粘贴清单同源，不得各存一份。"""
        # push_file_impl 里引用的就是这份集合对象
        self.assertIs(push_file_impl.PASTEABLE_EXTS, PASTEABLE_EXTS)

    def test_common_types_allowed(self):
        """压缩包与常见文档都应在白名单内。"""
        for ext in (".zip", ".md", ".pdf", ".docx", ".txt"):
            self.assertIn(ext, PASTEABLE_EXTS, "%s 应在白名单内" % ext)

    def test_archive_formats_allowed(self):
        """本次扩展的压缩包格式都应放行。"""
        for ext in (".zip", ".rar", ".7z", ".tar", ".gz"):
            self.assertIn(ext, PASTEABLE_EXTS, "%s 应在白名单内" % ext)


