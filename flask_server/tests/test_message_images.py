"""网页消息图片推送测试（message_images 执行路径）

背景：
  采集端把网页图片解析成 image 块，这里落盘后发到 QQ。
  关键设计：地址拿不到（blob: 等网页进程内的临时地址）不计入失败——
  重试多少次也拿不到，计了只会让这条消息永远卡在待推缓存里、后续消息跟着堵。
  这条区分写错，表现是「发了张图之后，后面所有消息都不推了」。

覆盖点：
  1. 开关关闭时什么都不做
  2. 成功发送计入成功张数
  3. 发送失败计入可重试张数
  4. 地址不可达不计入失败（关键区分）
  5. 非图片块被跳过
  6. push_images_block 的去重：已推过不再评估
  7. push_images_block 成功后才记入 seen_keys

运行：python -m pytest tests/test_message_images.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import message_images as mi


def _img_block(src):
    """造一个图片块。

    @param src 图片地址
    @returns 块对象
    """
    return {"type": "image", "src": src}


class PushMessageImagesTest(unittest.TestCase):
    """单条消息内的图片推送。"""

    def setUp(self):
        """替换落盘函数：可控地返回路径或空串。"""
        self._orig_save = mi._save_src_to_file
        self._save_map = {}

        def _fake_save(src):
            """按预设表返回落盘路径。"""
            return self._save_map.get(src, "")

        mi._save_src_to_file = _fake_save

    def tearDown(self):
        """还原落盘函数。"""
        mi._save_src_to_file = self._orig_save

    def test_switch_off_returns_zero(self):
        """图片开关关闭时什么都不做。"""
        m = {"blocks": [_img_block("http://x/a.png")]}
        self._save_map["http://x/a.png"] = "/tmp/a.png"
        sent, failed = mi.push_message_images(None, "u", m, {"tool": False}, lambda *a: True)
        self.assertEqual((sent, failed), (0, 0))

    def test_success_counts_as_sent(self):
        """发送成功计入成功张数。"""
        m = {"blocks": [_img_block("http://x/a.png")]}
        self._save_map["http://x/a.png"] = "/tmp/a.png"
        sent, failed = mi.push_message_images(None, "u", m, {}, lambda *a: True)
        self.assertEqual((sent, failed), (1, 0))

    def test_send_failure_counts_as_retryable(self):
        """发送失败计入可重试张数。"""
        m = {"blocks": [_img_block("http://x/a.png")]}
        self._save_map["http://x/a.png"] = "/tmp/a.png"
        sent, failed = mi.push_message_images(None, "u", m, {}, lambda *a: False)
        self.assertEqual((sent, failed), (0, 1))

    def test_unreachable_src_not_counted_as_failure(self):
        """地址不可达不计入失败——这是关键区分，计了会让消息永久堵塞。"""
        m = {"blocks": [_img_block("blob:http://x/abc")]}
        # 落盘返回空串：模拟地址拿不到
        sent, failed = mi.push_message_images(None, "u", m, {}, lambda *a: True)
        self.assertEqual((sent, failed), (0, 0))

    def test_non_image_blocks_skipped(self):
        """非图片块被跳过，不调用落盘与发送。"""
        calls = []
        m = {"blocks": [{"type": "paragraph", "text": "文字"},
                        {"type": "code", "code": "x"}]}
        sent, failed = mi.push_message_images(None, "u", m, {}, lambda *a: calls.append(1))
        self.assertEqual((sent, failed), (0, 0))
        self.assertEqual(calls, [])

    def test_multiple_images(self):
        """多张图分别计数。"""
        m = {"blocks": [_img_block("a"), _img_block("b")]}
        self._save_map["a"] = "/tmp/a"
        self._save_map["b"] = "/tmp/b"
        sent, failed = mi.push_message_images(None, "u", m, {}, lambda *a: True)
        self.assertEqual((sent, failed), (2, 0))

    def test_mixed_success_and_failure(self):
        """部分成功部分失败，两个计数各自正确。"""
        m = {"blocks": [_img_block("a"), _img_block("b")]}
        self._save_map["a"] = "/tmp/a"
        self._save_map["b"] = "/tmp/b"
        results = iter([True, False])
        sent, failed = mi.push_message_images(
            None, "u", m, {}, lambda *a: next(results))
        self.assertEqual((sent, failed), (1, 1))

    def test_empty_src_skipped(self):
        """src 为空的图片块被跳过。"""
        m = {"blocks": [{"type": "image"}]}
        sent, failed = mi.push_message_images(None, "u", m, {}, lambda *a: True)
        self.assertEqual((sent, failed), (0, 0))


class PushImagesBlockTest(unittest.TestCase):
    """记账：已推过的图片不重复评估。"""

    def setUp(self):
        """替换内部的图片推送函数，隔离真实发送。"""
        self._orig = mi.push_message_images

    def tearDown(self):
        """还原。"""
        mi.push_message_images = self._orig

    def test_already_pushed_returns_zero(self):
        """已推过的消息不再评估。"""
        mi.push_message_images = lambda *a: (1, 0)
        m = {"id": "m-1", "blocks": []}
        pushed = {"m-1#img"}
        seen = []
        n, failed = mi.push_images_block(None, "u", m, {}, pushed, seen)
        self.assertEqual((n, failed), (0, False))
        self.assertEqual(seen, [])

    def test_seen_in_this_round_returns_zero(self):
        """本轮已记账的也不重复评估。"""
        mi.push_message_images = lambda *a: (1, 0)
        m = {"id": "m-1", "blocks": []}
        seen = ["m-1#img"]
        n, failed = mi.push_images_block(None, "u", m, {}, set(), seen)
        self.assertEqual((n, failed), (0, False))

    def test_success_appends_key(self):
        """有图成功发出后记账。"""
        mi.push_message_images = lambda *a: (2, 0)
        m = {"id": "m-2", "blocks": []}
        seen = []
        n, failed = mi.push_images_block(None, "u", m, {}, set(), seen)
        self.assertEqual(n, 2)
        self.assertEqual(seen, ["m-2#img"])

    def test_no_success_does_not_append(self):
        """一张都没发出时不记账，下轮还能重试。"""
        mi.push_message_images = lambda *a: (0, 1)
        m = {"id": "m-3", "blocks": []}
        seen = []
        n, failed = mi.push_images_block(None, "u", m, {}, set(), seen)
        self.assertEqual(n, 0)
        self.assertTrue(failed)
        self.assertEqual(seen, [])

    def test_no_message_id_no_key(self):
        """消息没有 id 时不产生记账键，也不崩。"""
        mi.push_message_images = lambda *a: (1, 0)
        m = {"blocks": []}
        seen = []
        n, _f = mi.push_images_block(None, "u", m, {}, set(), seen)
        self.assertEqual(n, 1)
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
