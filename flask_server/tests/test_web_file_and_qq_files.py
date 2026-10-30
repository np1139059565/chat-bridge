"""文件来件入口：文件名净化、类型与体积校验、落盘路径

为什么需要：
    网页上传与企业微信媒体走的是同一条「来件」链路，但两者的文件名
    都来自对端，属于不可信输入。这条链路此前没有任何测试：
    路径穿越、超限文件、白名单外的类型全靠运行时才发现。

本文件覆盖：
    qq_files._safe_name   —— 去目录、过滤保留符号、空名兜底
    web_file.handle_upload —— 空文件、坏 base64、非法类型、超限体积、成功落盘
    file_types            —— 后缀提取、点文件判定、白名单查询

运行：python -m pytest tests/test_web_file_and_qq_files.py -q
"""
import base64

import pytest

from remote_bridge import qq_files
from routes import web_file
from tools import file_types


class TestSafeName:
    """对端文件名净化：只允许落在目标目录内。"""

    def test_strips_directory_parts(self):
        """带路径的文件名只取基名，防止写到目录外。"""
        assert qq_files._safe_name("../../etc/passwd", "fb") == "passwd"

    def test_backslash_path_treated_as_separator(self):
        """Windows 风格反斜杠同样视为目录分隔符。"""
        assert qq_files._safe_name("C:\\tmp\\a.txt", "fb") == "a.txt"

    def test_filters_reserved_symbols(self):
        """文件系统保留符号被剔除，不留在落盘名里。"""
        assert qq_files._safe_name('a<>:"|?*.txt', "fb") == "a.txt"

    def test_empty_falls_back(self):
        """对端未给名字时用兜底名。"""
        assert qq_files._safe_name("", "qqfile_1") == "qqfile_1"

    def test_whitespace_only_falls_back(self):
        """全空白也视作未给名字。"""
        assert qq_files._safe_name("   ", "fb") == "fb"


class TestHandleUpload:
    """网页上传：四道校验按序拦截，成功时落盘并投卡片。

    每条用例都把落盘目录指向临时目录：校验逻辑一旦被改坏、
    本该被拒的文件流到写盘那一步，也不会落到真实来件目录。
    """

    @pytest.fixture(autouse=True)
    def _isolate_dirs(self, tmp_path, monkeypatch):
        """隔离落盘目录与卡片投递，避免测试触碰真实数据。"""
        monkeypatch.setattr(web_file.paths, "QQ_FILES_DIR", tmp_path)
        cards = []
        monkeypatch.setattr(
            web_file.web_bridge.web, "ingest_file",
            lambda path, name, size, text: cards.append((path, name, size)) or "card-1")
        self.cards = cards
        self.tmp_dir = tmp_path

    def test_empty_file_rejected(self):
        """没有 data 字段直接拒，不进入解码。"""
        res, status = web_file.handle_upload({"name": "a.txt"})
        assert status == 400
        assert res["error"] == "empty_file"

    def test_bad_name_rejected(self):
        """文件名净化后为空时拒掉，避免落成无主名文件。"""
        res, status = web_file.handle_upload({"name": "<>", "data": "YQ=="})
        assert status == 400
        assert res["error"] == "bad_name"

    def test_unsupported_type_rejected_before_decode(self):
        """白名单外的扩展名在解码前就拒，省一次解码与写盘。"""
        res, status = web_file.handle_upload({"name": "a.exe", "data": "YQ=="})
        assert status == 400
        assert res["error"] == "unsupported_type"

    def test_bad_base64_rejected(self):
        """扩展名合法但内容不是 base64 时返回解码错误。"""
        res, status = web_file.handle_upload({"name": "a.txt", "data": "!!!not-b64"})
        assert status == 400
        assert res["error"] == "bad_base64"

    def test_oversized_rejected(self, monkeypatch):
        """超过上限时拒收，并提示实际体积。

        上限调小到 4 字节，避免真的构造 20MB 数据。
        """
        monkeypatch.setattr(qq_files, "MAX_INBOUND_BYTES", 4)
        payload = base64.b64encode(b"12345").decode()
        res, status = web_file.handle_upload({"name": "a.txt", "data": payload})
        assert status == 400
        assert res["error"] == "too_large"

    def test_success_writes_file_and_returns_path(self):
        """合法文件落盘到来件目录，返回值带上路径与体积。"""
        payload = base64.b64encode("内容".encode()).decode()
        res, status = web_file.handle_upload(
            {"name": "a.txt", "data": payload, "text": "看下这个"})
        assert status == 200
        assert res["success"] is True
        assert res["name"] == "a.txt"
        assert res["size"] == len("内容".encode())
        # 卡片投递一次，名字与上传名一致
        assert len(self.cards) == 1
        assert self.cards[0][1] == "a.txt"
        # 文件真的落在临时目录里，内容与上传一致
        written = list(self.tmp_dir.iterdir())
        assert len(written) == 1
        assert written[0].read_bytes() == "内容".encode()


class TestSuffixOf:
    """后缀提取：普通文件取末段，点文件取整名。"""

    def test_normal_extension(self):
        """取最后一个点之后的部分，含点。"""
        assert file_types.suffix_of("a/b/readme.MD") == ".md"

    def test_dotfile_uses_whole_name(self):
        """.gitignore 这类点文件整名即后缀。"""
        assert file_types.suffix_of("a/.gitignore") == ".gitignore"

    def test_no_extension_returns_empty(self):
        """没有点的主名返回空串。"""
        assert file_types.suffix_of("a/Makefile") == ""

    def test_empty_input_returns_empty(self):
        """空输入不抛异常。"""
        assert file_types.suffix_of("") == ""


class TestIsPasteable:
    """可粘贴判定：白名单查询，点文件一律不可粘贴。"""

    def test_whitelisted_type(self):
        """白名单内的类型可粘贴。"""
        assert file_types.is_pasteable("a.txt") is True

    def test_unknown_type(self):
        """白名单外的类型不可粘贴。"""
        assert file_types.is_pasteable("a.exe") is False

    def test_dotfile_never_pasteable(self):
        """无主名的点文件即使后缀在清单内也不可粘贴。"""
        assert file_types.is_pasteable(".env") is False
