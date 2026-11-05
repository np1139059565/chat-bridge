"""QQ 事件解析测试（qq_event_parse 执行路径）

背景：
  该模块此前只有 10% 覆盖。它负责从 QQ 推送的事件里取出用户标识、正文、
  消息 id 与各类附件地址。这些判定靠字段名与扩展名试错，
  任何一处判错就是「消息收到了但内容丢了」或「图片被当成文件下载」。

覆盖点：
  1. extract：正常取字段、缺字段时的容错
  2. extract_voice：content_type 判据、扩展名判据、无附件
  3. extract_image：content_type 前缀判据（image/jpeg 形态）、文件名兜底
  4. extract_file：跳过图片与语音、按 content_type 或文件名判定
  5. 附件不是字典时跳过，不抛异常

运行：python -m pytest tests/test_qq_event_parse.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import qq_event_parse as ep


class ExtractBasicTest(unittest.TestCase):
    """基础字段提取。"""

    def test_extract_all_fields(self):
        """三个关键字段都能取出。"""
        d = {"id": "msg-1", "content": "  你好  ",
             "author": {"user_openid": "openid-a"}}
        self.assertEqual(ep.extract(d), ("openid-a", "你好", "msg-1"))

    def test_extract_missing_fields(self):
        """缺字段时返回空串，不抛异常。"""
        self.assertEqual(ep.extract({}), ("", "", ""))

    def test_extract_author_not_dict(self):
        """author 不是字典时的容错。"""
        d = {"author": "oops", "content": "x", "id": "1"}
        self.assertEqual(ep.extract(d)[0], "")


class ExtractVoiceTest(unittest.TestCase):
    """语音附件提取。"""

    def test_voice_by_content_type(self):
        """content_type 为 voice 时命中。"""
        d = {"attachments": [{"content_type": "voice", "url": "http://x/a"}]}
        self.assertEqual(ep.extract_voice(d), "http://x/a")

    def test_voice_by_extension(self):
        """url 以 .silk 结尾时命中。"""
        d = {"attachments": [{"url": "http://x/a.silk"}]}
        self.assertEqual(ep.extract_voice(d), "http://x/a.silk")

    def test_voice_amr_extension(self):
        """url 以 .amr 结尾时命中。"""
        d = {"attachments": [{"url": "http://x/a.amr"}]}
        self.assertEqual(ep.extract_voice(d), "http://x/a.amr")

    def test_voice_none(self):
        """没有语音附件时返回空串。"""
        self.assertEqual(ep.extract_voice({}), "")
        self.assertEqual(ep.extract_voice({"attachments": []}), "")

    def test_voice_skips_non_dict(self):
        """附件列表里混入非字典项时跳过。"""
        d = {"attachments": ["oops", {"content_type": "voice", "url": "u"}]}
        self.assertEqual(ep.extract_voice(d), "u")

    def test_voice_without_url_skipped(self):
        """没有 url 的附件跳过。"""
        d = {"attachments": [{"content_type": "voice"}]}
        self.assertEqual(ep.extract_voice(d), "")


class ExtractImageTest(unittest.TestCase):
    """图片附件提取。"""

    def test_image_by_content_type_prefix(self):
        """content_type 形如 image/jpeg 时命中——这是真实形态。"""
        d = {"attachments": [{"content_type": "image/jpeg", "url": "http://x/a"}]}
        self.assertEqual(ep.extract_image(d), "http://x/a")

    def test_image_by_filename_extension(self):
        """URL 无扩展名时靠文件名兜底。"""
        d = {"attachments": [{"filename": "pic.PNG", "url": "http://x/download?id=1"}]}
        self.assertEqual(ep.extract_image(d), "http://x/download?id=1")

    def test_image_pic_type(self):
        """content_type 为 pic 时命中。"""
        d = {"attachments": [{"content_type": "pic", "url": "http://x/a"}]}
        self.assertEqual(ep.extract_image(d), "http://x/a")

    def test_image_none(self):
        """没有图片附件时返回空串。"""
        self.assertEqual(ep.extract_image({"attachments": [{"url": "http://x/a.pdf"}]}), "")


class ExtractFileTest(unittest.TestCase):
    """文件附件提取。"""

    def test_file_by_content_type(self):
        """content_type 指向文件时命中，并带出文件名。"""
        d = {"attachments": [{"content_type": "application/pdf",
                             "url": "http://x/f", "filename": "报告.pdf"}]}
        self.assertEqual(ep.extract_file(d), ("http://x/f", "报告.pdf"))

    def test_file_by_filename(self):
        """没有明确 content_type 但有文件名时命中。"""
        d = {"attachments": [{"url": "http://x/f", "filename": "a.zip"}]}
        self.assertEqual(ep.extract_file(d), ("http://x/f", "a.zip"))

    def test_file_skips_image(self):
        """图片不被当成文件——这是判定顺序的关键约束。"""
        d = {"attachments": [{"content_type": "image/png",
                             "url": "http://x/i", "filename": "a.png"}]}
        self.assertEqual(ep.extract_file(d), ("", ""))

    def test_file_skips_voice(self):
        """语音不被当成文件。"""
        d = {"attachments": [{"content_type": "voice",
                             "url": "http://x/v", "filename": "a.silk"}]}
        self.assertEqual(ep.extract_file(d), ("", ""))

    def test_file_none(self):
        """没有文件附件时返回两个空串。"""
        self.assertEqual(ep.extract_file({}), ("", ""))

    def test_file_without_url_skipped(self):
        """有文件名但没有 url 时跳过。"""
        d = {"attachments": [{"filename": "a.zip"}]}
        self.assertEqual(ep.extract_file(d), ("", ""))


if __name__ == "__main__":
    unittest.main()
