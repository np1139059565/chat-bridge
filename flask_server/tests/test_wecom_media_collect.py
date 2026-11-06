"""企业微信媒体收集测试（wecom_media_collect 执行路径）

背景：
  该模块此前覆盖率 15%，是微信通道收图的必经之路。
  它把消息里的图片、文件、语音落成本地文件供发送层取用。
  这里出错的表现不是报错，而是「图片一条都发不出去」「文件下载到一半静默失败」，
  排查时只能看到发送层说「没有可发的内容」。

覆盖点：
  1. collect_images：空块与无关块、相对接口地址命中本地、dataURL 落盘、
     http 下载、两种来源都失败时不入列表、不支持的协议丢弃
  2. collect_files：files 字段本地路径与 http 下载、旧格式块路径、
     非字典与路径不存在跳过、两处重复路径只保留一份
  3. collect_voice：无朗读文本返回空、优先预合成路径、回退 voice 字段、
     相对文件名解析到音频目录、文件不存在时路径为空但保留文本
  4. resolve_local_image：非斜杠开头与未知前缀拒绝、路径穿越拒绝、
     URL 解码、截图前缀映射、文件不存在返回空
  5. materialize_image：dataURL 按 MIME 定扩展名、非法 base64 返回空、
     http 扩展名识别与查询串、未知扩展名回退、下载异常与非 http 协议返回空
  6. download_to_media：文件名扩展名优先、URL 扩展名次之、
     都无则回退 .bin、异常返回空

写法说明：
  断言雷同的用例合并到同一方法内，分段注释说明各自验证什么。

运行：python -m pytest tests/test_wecom_media_collect.py -q
"""
import base64
import os
import sys
import tempfile
import unittest
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import wecom_media_collect as wmc


class _FakeResp:
    """模拟 urlopen 的返回对象，支持上下文管理与 read。"""

    def __init__(self, data=b"payload"):
        """
        @param data 要返回的字节
        """
        self._data = data

    def __enter__(self):
        """进入上下文，返回自身。"""
        return self

    def __exit__(self, *a):
        """退出上下文，不吞异常。"""
        return False

    def read(self):
        """返回预设内容。"""
        return self._data


class _Base(unittest.TestCase):
    """公共夹具：临时目录接管媒体与图片目录，并提供网络与文件桩。"""

    def setUp(self):
        """把四个路径变量切到临时目录，并保存原值。"""
        self._dir = tempfile.mkdtemp()
        self._saved = {
            "media": paths.WECOM_MEDIA_DIR,
            "images": paths.WEB_IMAGES_DIR,
            "shots": paths.SCREENSHOTS_DIR,
            "audio": paths.WEB_AUDIO_DIR,
            "urlopen": wmc.urllib.request.urlopen,
        }
        # 必须是 Path 而不是字符串：被测代码用 `目录 / 文件名` 拼接
        paths.WECOM_MEDIA_DIR = Path(self._dir) / "media"
        paths.WEB_IMAGES_DIR = Path(self._dir) / "images"
        paths.SCREENSHOTS_DIR = Path(self._dir) / "shots"
        paths.WEB_AUDIO_DIR = Path(self._dir) / "audio"
        for d in (paths.WECOM_MEDIA_DIR, paths.WEB_IMAGES_DIR,
                  paths.SCREENSHOTS_DIR, paths.WEB_AUDIO_DIR):
            os.makedirs(str(d), exist_ok=True)

    def tearDown(self):
        """还原路径变量与网络函数，清理临时目录。"""
        paths.WECOM_MEDIA_DIR = self._saved["media"]
        paths.WEB_IMAGES_DIR = self._saved["images"]
        paths.SCREENSHOTS_DIR = self._saved["shots"]
        paths.WEB_AUDIO_DIR = self._saved["audio"]
        wmc.urllib.request.urlopen = self._saved["urlopen"]
        shutil.rmtree(self._dir, ignore_errors=True)

    def _fake_urlopen(self, data=b"payload", raise_it=False):
        """替换 urlopen，返回预设内容或抛异常。

        @param data 返回的字节
        @param raise_it 是否抛异常
        """
        def _open(url, timeout=None):
            """模拟网络请求。"""
            if raise_it:
                raise OSError("下载失败")
            return _FakeResp(data)
        wmc.urllib.request.urlopen = _open

    def _write(self, directory, name, data=b"x"):
        """在指定目录写一个文件并返回路径。

        @param directory 目标目录
        @param name 文件名
        @param data 内容
        @returns 文件绝对路径
        """
        p = os.path.join(str(directory), name)
        with open(p, "wb") as f:
            f.write(data)
        return p


class CollectImagesTest(_Base):
    """图片收集：多种来源都要能落到本地。"""

    def test_empty_and_irrelevant_blocks(self):
        """无块、非图片块、空 src 都返回空列表。"""
        self.assertEqual(wmc.collect_images({}), [])
        self.assertEqual(wmc.collect_images({"blocks": [{"type": "text"}]}), [])
        self.assertEqual(wmc.collect_images({"blocks": [{"type": "image", "src": ""}]}), [])

    def test_local_route_hit(self):
        """相对接口地址命中本地文件时直接返回该路径，不走网络。"""
        self._write(paths.WEB_IMAGES_DIR, "a.png")
        # 网络一旦被调用即判失败：命中本地就不该再下载
        wmc.urllib.request.urlopen = lambda *a, **k: self.fail("不该发请求")
        out = wmc.collect_images({"blocks": [{"type": "image", "src": "/api/web/image-file/a.png"}]})
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].endswith("a.png"))

    def test_dataurl_and_http(self):
        """dataURL 解码写盘并按 MIME 定扩展名；http 地址下载后按 URL 定扩展名。"""
        b64 = base64.b64encode(b"GIF89a").decode()
        out = wmc.collect_images({"blocks": [{"type": "image", "src": "data:image/gif;base64," + b64}]})
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].endswith(".gif"))
        with open(out[0], "rb") as f:
            self.assertEqual(f.read(), b"GIF89a")
        self._fake_urlopen(b"IMG")
        out = wmc.collect_images({"blocks": [{"type": "image", "src": "https://x/a.webp"}]})
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].endswith(".webp"))

    def test_failures_excluded(self):
        """下载失败与不支持的协议都不入列表，也不抛异常。"""
        self._fake_urlopen(raise_it=True)
        self.assertEqual(wmc.collect_images({"blocks": [{"type": "image", "src": "https://x/a.png"}]}), [])
        self.assertEqual(wmc.collect_images({"blocks": [{"type": "image", "src": "ftp://x/a.png"}]}), [])


class CollectFilesTest(_Base):
    """文件收集：files 字段优先，兼容旧格式块。"""

    def test_files_field_local_path(self):
        """files 字段里带本地路径时直接采纳。"""
        p = self._write(self._dir, "doc.pdf")
        self.assertEqual(wmc.collect_files({"files": [{"path": p}]}), [p])

    def test_files_field_http_download(self):
        """files 字段只有 http 地址时下载，保留原扩展名。"""
        self._fake_urlopen(b"PDF")
        out = wmc.collect_files({"files": [{"url": "https://x/a.pdf", "name": "报告.pdf"}]})
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].endswith(".pdf"))

    def test_skips_invalid_items(self):
        """非字典项与路径不存在的条目都跳过。"""
        self.assertEqual(wmc.collect_files({"files": ["notdict", {"path": "/no/such/file"}]}), [])

    def test_legacy_block_and_dedup(self):
        """旧格式块里的路径也要能取到；与 files 字段重复时只保留一份。"""
        p = self._write(self._dir, "old.txt")
        self.assertEqual(wmc.collect_files({"blocks": [{"type": "file", "path": p}]}), [p])
        out = wmc.collect_files({"files": [{"path": p}], "blocks": [{"type": "file", "path": p}]})
        self.assertEqual(out, [p])


class CollectVoiceTest(_Base):
    """语音收集：优先预合成，回退消息自带字段。"""

    def setUp(self):
        """在父类夹具之外替换朗读文本提取，避免依赖真实消息结构。"""
        super().setUp()
        import remote_bridge.message_voice as mv
        self._saved_extract = mv.extract_voice_from_blocks

    def tearDown(self):
        """还原朗读文本提取。"""
        import remote_bridge.message_voice as mv
        mv.extract_voice_from_blocks = self._saved_extract
        super().tearDown()

    def _patch_text(self, text):
        """替换朗读文本提取结果。

        @param text 要返回的文本
        """
        import remote_bridge.message_voice as mv
        mv.extract_voice_from_blocks = lambda m: text

    def test_no_text_returns_empty(self):
        """没有朗读文本时不推语音，返回两个空串。"""
        self._patch_text("")
        self.assertEqual(wmc.collect_voice({"id": "m1"}), ("", ""))

    def test_prefer_presynth_then_fallback(self):
        """有预合成路径时优先；没有则回退消息自带 voice 字段。"""
        self._patch_text("你好")
        p = self._write(paths.WEB_AUDIO_DIR, "a.mp3")
        self.assertEqual(wmc.collect_voice({"id": "m1", "voice": "ignored.mp3"}, {"m1": p}), (p, "你好"))
        p2 = self._write(paths.WEB_AUDIO_DIR, "b.mp3")
        self.assertEqual(wmc.collect_voice({"id": "m1", "voice": p2}), (p2, "你好"))

    def test_relative_name_resolved(self):
        """voice 只是文件名时解析到网页音频目录，并返回绝对路径。"""
        self._patch_text("你好")
        self._write(paths.WEB_AUDIO_DIR, "c.mp3")
        got = wmc.collect_voice({"id": "m1", "voice": "c.mp3"})
        self.assertTrue(got[0].endswith("c.mp3"))
        self.assertTrue(os.path.isabs(got[0]))

    def test_missing_file_keeps_text(self):
        """音频不存在或无路径时路径为空，但文本仍返回供上层补合成。"""
        self._patch_text("你好")
        self.assertEqual(wmc.collect_voice({"id": "m1", "voice": "nope.mp3"}), ("", "你好"))
        self.assertEqual(wmc.collect_voice({"id": "m1"}), ("", "你好"))


class ResolveLocalImageTest(_Base):
    """相对地址解析：越权与不存在的路径一律拒绝。"""

    def test_rejects_invalid_forms(self):
        """非斜杠开头、未知前缀、路径穿越一律拒绝。"""
        self.assertEqual(wmc.resolve_local_image("api/web/image-file/a.png"), "")
        self.assertEqual(wmc.resolve_local_image("/api/other/a.png"), "")
        # 带 .. 或路径分隔符的文件名一律拒绝，防越权读取
        for bad in ("..%2Fetc/passwd", "a/b.png", "a\\b.png", "..png"):
            self.assertEqual(wmc.resolve_local_image("/api/web/image-file/" + bad), "", bad)

    def test_hit_with_url_decoding(self):
        """命中时做 URL 解码，中文文件名也能定位。"""
        self._write(paths.WEB_IMAGES_DIR, "图片.png")
        got = wmc.resolve_local_image("/api/web/image-file/%E5%9B%BE%E7%89%87.png")
        self.assertTrue(got.endswith("图片.png"))

    def test_screenshot_route_and_missing(self):
        """截图前缀映射到截图目录；文件不存在时返回空串。"""
        self._write(paths.SCREENSHOTS_DIR, "s.png")
        self.assertTrue(wmc.resolve_local_image("/api/web/screenshot-file/s.png").endswith("s.png"))
        self.assertEqual(wmc.resolve_local_image("/api/web/image-file/none.png"), "")


class MaterializeImageTest(_Base):
    """图片落盘：dataURL 与 http 两条路径。"""

    def test_dataurl_ext_by_mime(self):
        """扩展名按 MIME 头决定：jpeg、png、webp 各自对应。"""
        for mime, ext in (("jpeg", ".jpg"), ("png", ".png"), ("webp", ".webp")):
            src = "data:image/%s;base64," % mime + base64.b64encode(b"x").decode()
            got = wmc.materialize_image(src)
            self.assertTrue(got.endswith(ext), "%s → %s" % (mime, got))

    def test_dataurl_bad_base64(self):
        """非法 base64 返回空串，不抛异常。"""
        self.assertEqual(wmc.materialize_image("data:image/png;base64,!!!notbase64"), "")

    def test_http_ext_rules(self):
        """http 按已知扩展名识别（查询串不影响）；未知扩展名回退 .png。"""
        self._fake_urlopen(b"IMG")
        self.assertTrue(wmc.materialize_image("https://x/a.jpg?token=1").endswith(".jpg"))
        self.assertTrue(wmc.materialize_image("https://x/a.bmp").endswith(".png"))

    def test_failures_and_unsupported(self):
        """下载异常返回空串；既非 dataURL 也非 http(s) 也返回空串。"""
        self._fake_urlopen(raise_it=True)
        self.assertEqual(wmc.materialize_image("https://x/a.png"), "")
        self.assertEqual(wmc.materialize_image("ftp://x/a.png"), "")


class DownloadToMediaTest(_Base):
    """通用下载：落在媒体目录，扩展名处理正确。"""

    def test_extension_resolution(self):
        """文件名扩展名优先；无名字取 URL 末段并忽略查询串；都无则回退 .bin。"""
        self._fake_urlopen(b"DATA")
        got = wmc.download_to_media("https://x/download?id=1", "报表.xlsx")
        self.assertTrue(got.endswith(".xlsx"))
        self.assertTrue(os.path.isfile(got))
        self.assertTrue(got.startswith(str(paths.WECOM_MEDIA_DIR)))
        self.assertTrue(wmc.download_to_media("https://x/a.zip?v=2").endswith(".zip"))
        self.assertTrue(wmc.download_to_media("https://x/download").endswith(".bin"))

    def test_failure_returns_empty(self):
        """下载异常返回空串，不抛。"""
        self._fake_urlopen(raise_it=True)
        self.assertEqual(wmc.download_to_media("https://x/a.pdf"), "")


if __name__ == "__main__":
    unittest.main()
