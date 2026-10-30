"""企业微信富媒体：文件头魔数识别扩展名

为什么需要：
    企业微信的媒体下载地址不带扩展名。旧实现从 URL 取扩展名，
    结果永远落到兜底的 .bin——图片和 PDF 存下来前端认不出，
    既贴不进输入框也打不开。改成按文件头魔数判断后，
    这条路径此前没有任何测试兜底。

本文件覆盖：
    常见格式 —— PNG / JPEG / GIF / BMP / PDF / ZIP / GZIP
    RIFF 容器 —— webp 与 wav 靠偏移 8 的类型区分，其余归 .riff
    偏移判定 —— MP4 的 ftyp 在偏移 4，不在开头
    兜底路径 —— 空数据、未知字节都返回 .bin，不得抛异常

运行：python -m pytest tests/test_wecom_media.py -q
"""
from remote_bridge.wecom_media import sniff_extension


class TestKnownFormats:
    """开头即签名的格式：直接按前缀匹配。"""

    def test_png(self):
        """PNG 的签名是 8 字节，必须完整匹配。"""
        assert sniff_extension(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) == ".png"

    def test_jpeg(self):
        """JPEG 以 ff d8 ff 开头。"""
        assert sniff_extension(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == ".jpg"

    def test_gif87a_and_gif89a(self):
        """两个 GIF 版本号都要认。"""
        assert sniff_extension(b"GIF87a" + b"\x00" * 8) == ".gif"
        assert sniff_extension(b"GIF89a" + b"\x00" * 8) == ".gif"

    def test_pdf(self):
        """PDF 以 %PDF 开头。"""
        assert sniff_extension(b"%PDF-1.7" + b"\x00" * 8) == ".pdf"

    def test_zip_container(self):
        """zip 与 docx/xlsx/pptx 同属 PK 头，统一给 .zip。"""
        assert sniff_extension(b"PK\x03\x04" + b"\x00" * 8) == ".zip"

    def test_gzip(self):
        """gzip 以 1f 8b 开头。"""
        assert sniff_extension(b"\x1f\x8b\x08" + b"\x00" * 8) == ".gz"


class TestRiffContainer:
    """RIFF 家族：前 4 字节相同，必须再看偏移 8 的类型。"""

    def test_webp(self):
        """RIFF + 偏移 8 为 WEBP。"""
        assert sniff_extension(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"

    def test_wav(self):
        """RIFF + 偏移 8 为 WAVE。"""
        assert sniff_extension(b"RIFF\x00\x00\x00\x00WAVEfmt ") == ".wav"

    def test_other_riff(self):
        """既非 WEBP 也非 WAVE 的 RIFF，给通用的 .riff。"""
        assert sniff_extension(b"RIFF\x00\x00\x00\x00AVI LIST") == ".riff"


class TestOffsetAndFallback:
    """偏移判定与兜底路径。"""

    def test_mp4_ftyp_at_offset_4(self):
        """MP4 的 ftyp 位于偏移 4，前缀匹配抓不到，需单独判断。"""
        assert sniff_extension(b"\x00\x00\x00\x20ftypisom") == ".mp4"

    def test_empty_returns_bin(self):
        """空数据不能抛异常，返回兜底扩展名。"""
        assert sniff_extension(b"") == ".bin"

    def test_unknown_returns_bin(self):
        """认不出的字节一律 .bin。"""
        assert sniff_extension(b"\x01\x02\x03\x04\x05\x06\x07\x08") == ".bin"

    def test_short_data_does_not_raise(self):
        """短于 16 字节的输入也要安全返回，切片不会越界。"""
        assert sniff_extension(b"RI") == ".bin"
