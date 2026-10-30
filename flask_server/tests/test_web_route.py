"""网页版路由：路径穿越防护、图片入参与静态资源类型

为什么需要：
    routes/web.py 对外暴露文件读取接口（静态资源、图片、音频、截图），
    文件名来自 URL，属不可信输入。防穿越逻辑一旦失效，构造 ../ 就能读到
    目录外的任意文件。此前该路由零测试覆盖。

本文件覆盖：
    _safe_under       —— 路径分隔符与上跳被拒、不存在的文件返回 None、正常文件放行
    _safe_audio_path  —— 走通用防护，指向音频目录
    _image_urls       —— 数组与单值两种入参、空值过滤
    _image_label      —— 单图、多图、带文字三种展示
    _send_image_under —— 命中返回图片响应、穿越与不存在的文件返回 404
    web_asset         —— 非法文件名与未知扩展名返回 400、不存在文件返回 404

隔离策略：
    自建最小 Flask 实例，只注册被测蓝图；文件操作全部落在临时目录，
    不触碰真实图片与音频数据。

运行：python -m pytest tests/test_web_route.py -q
"""
import pytest
from flask import Flask, request

import paths
from routes import web as web_route


_APP = Flask("web_route_test")
_APP.register_blueprint(web_route.bp)


@_APP.before_request
def _preflight():
    """OPTIONS 预检直接返回 204。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return None


@pytest.fixture
def img_dir(tmp_path, monkeypatch):
    """临时媒体目录，并让被测模块指向它。"""
    d = tmp_path / "img"
    d.mkdir()
    monkeypatch.setattr(web_route.paths, "WEB_IMAGES_DIR", d)
    monkeypatch.setattr(web_route.paths, "WEB_AUDIO_DIR", d)
    return d


@pytest.fixture
def client():
    """被测蓝图的最小测试客户端。"""
    return _APP.test_client()


class TestSafeUnder:
    """路径穿越防护：只允许基准目录下的纯文件名。"""

    def test_normal_file_allowed(self, tmp_path):
        """基准目录内的真实文件放行，返回绝对路径。"""
        f = tmp_path / "a.css"
        f.write_text("x", encoding="utf-8")
        got = web_route._safe_under("a.css", tmp_path)
        assert got == str(f.resolve())

    def test_missing_file_returns_none(self, tmp_path):
        """文件不存在时返回 None，不把目录当文件返回。"""
        assert web_route._safe_under("nope.css", tmp_path) is None

    def test_empty_name_returns_none(self, tmp_path):
        """空文件名直接拒。"""
        assert web_route._safe_under("", tmp_path) is None

    @pytest.mark.parametrize("name", ["../secret.txt", "a/../../b.txt", "sub/x.css"])
    def test_path_separators_rejected(self, tmp_path, name):
        """含分隔符或上跳的文件名一律拒绝。"""
        assert web_route._safe_under(name, tmp_path) is None

    def test_backslash_rejected(self, tmp_path):
        """反斜杠同样视为分隔符。"""
        assert web_route._safe_under("..\\secret.txt", tmp_path) is None

    def test_directory_itself_not_returned(self, tmp_path):
        """名字对应基准目录本身时，它不是文件，返回 None。"""
        assert web_route._safe_under(".", tmp_path) is None


class TestSafeAudioPath:
    """音频路径：走通用防护。"""

    def test_audio_file_allowed(self, img_dir):
        """音频目录内的文件放行。"""
        f = img_dir / "in_1.webm"
        f.write_bytes(b"x")
        assert web_route._safe_audio_path("in_1.webm") == str(f.resolve())

    def test_traversal_rejected(self, img_dir):
        """上跳文件名被拒。"""
        assert web_route._safe_audio_path("../x.webm") is None


class TestImageUrls:
    """从请求体提取图片 dataURL 列表。"""

    def test_list_form(self):
        """数组形式全部保留。"""
        assert web_route._image_urls({"dataUrls": ["a", "b"]}) == ["a", "b"]

    def test_single_form(self):
        """单个 dataUrl 兼容为单元素列表。"""
        assert web_route._image_urls({"dataUrl": "a"}) == ["a"]

    def test_empty_values_filtered(self):
        """空值被过滤掉。"""
        assert web_route._image_urls({"dataUrls": ["", None, "b"]}) == ["b"]

    def test_nothing_provided(self):
        """两者都没给时返回空列表。"""
        assert web_route._image_urls({}) == []


class TestImageLabel:
    """收件箱展示文本。"""

    def test_single_image_plain(self):
        """单张且无文字时显示占位。"""
        assert web_route._image_label("", 1) == "[图片]"

    def test_single_image_with_text(self):
        """单张带文字时只显示文字。"""
        assert web_route._image_label("看这个", 1) == "看这个"

    def test_multiple_images_with_text(self):
        """多张时在文字后标注张数。"""
        assert web_route._image_label("看这个", 3) == "看这个 [3 张图片]"

    def test_multiple_images_without_text(self):
        """多张无文字时只标张数。"""
        assert web_route._image_label("", 2) == "[2 张图片]"


class TestSendImageUnder:
    """按基准目录安全发送图片。"""

    def test_missing_returns_404(self, img_dir):
        """文件不存在时返回 404 响应。"""
        with _APP.app_context():
            _, status = web_route._send_image_under("nope.png", img_dir)
            assert status == 404

    def test_traversal_returns_404(self, img_dir):
        """穿越文件名返回 404。"""
        with _APP.app_context():
            _, status = web_route._send_image_under("../x.png", img_dir)
            assert status == 404

    def test_png_sent_as_png_mime(self, img_dir):
        """png 文件按 image/png 发送。

        send_file 需要请求上下文，故用 test_request_context 构造。
        """
        (img_dir / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        with _APP.test_request_context("/"):
            resp = web_route._send_image_under("a.png", img_dir)
            assert resp.mimetype == "image/png"

    def test_jpg_sent_as_jpeg_mime(self, img_dir):
        """jpg 文件按 image/jpeg 发送。"""
        (img_dir / "a.jpg").write_bytes(b"\xff\xd8\xff")
        with _APP.test_request_context("/"):
            resp = web_route._send_image_under("a.jpg", img_dir)
            assert resp.mimetype == "image/jpeg"


class TestWebAsset:
    """静态资源接口：白名单扩展名与目录穿越。"""

    def test_separator_rejected(self, client):
        """带分隔符的资源名被拒。

        编码后的斜杠在路由匹配阶段就使路径不再符合单段规则，
        请求不会进入视图，故返回 404 而非视图内的 400。
        视图内的分隔符判断是第二道防线，由下面的直接调用用例覆盖。
        """
        resp = client.get("/web-bot/..%2Fsecret.css")
        assert resp.status_code == 404

    @pytest.mark.parametrize("name", ["../x.css", "a/b.css", "a\\b.css"])
    def test_view_rejects_separators(self, name):
        """视图自身的分隔符判断也拦截：路径参数被直接传入时返回 400。

        绕过路由匹配直接调用视图函数，验证第二道防线。
        """
        with _APP.test_request_context("/"):
            _, status = web_route.web_asset(name)
            assert status == 400

    def test_unknown_extension_rejected(self, client):
        """非 css/js/html 扩展名返回 400。"""
        resp = client.get("/web-bot/a.txt")
        assert resp.status_code == 400

    def test_missing_asset_returns_404(self, client):
        """扩展名合法但文件不存在时返回 404。"""
        resp = client.get("/web-bot/no_such_file_xyz.css")
        assert resp.status_code == 404

    def test_existing_asset_served(self, client, monkeypatch, tmp_path):
        """真实存在的 css 文件按 text/css 返回。"""
        base = tmp_path / "web_bridge"
        base.mkdir()
        (base / "a.css").write_text("body{}", encoding="utf-8")
        monkeypatch.setattr(web_route.paths, "APP_DIR", tmp_path)
        resp = client.get("/web-bot/a.css")
        assert resp.status_code == 200
        assert resp.mimetype == "text/css"
