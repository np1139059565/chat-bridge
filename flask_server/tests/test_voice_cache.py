"""语音成品缓存：复用与删除保护的回归测试。

背景（两次真实问题）：
    1. 网页点播与 QQ 推送各自合成、互不复用，同一条 AI 消息被完整合成两遍；
       积压补推时逐条串行合成，把首条推送硬生生拖后十几秒。
    2. 语音推完即删的清理逻辑不区分目录，会把刚存好的缓存成品一并删掉，
       缓存形同虚设。

本测试锁定的契约：
    A. 同一段文本第二次查找必须命中，且路径指向缓存目录；
    B. 缓存键只由文本内容决定，与消息 id、时间无关；
    C. 临时语音推完即删，缓存成品一律保留；
    D. 空文本不产生缓存键，也不会误命中。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_voice_cache -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401
from remote_bridge import message_flow, voice_cache


class _SynthStub:
    """合成桩：写一个非空文件冒充音频，避免测试依赖真实语音引擎。"""

    def __init__(self, path):
        self.path = path

    def write(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "wb") as f:
            f.write(b"stub-audio")
        return self.path


def _tmp_voice_path(tag):
    """在临时语音目录里造一个不存在的目标路径。"""
    os.makedirs(paths.VOICE_DIR, exist_ok=True)
    return str(paths.VOICE_DIR / ("test_%s.mp3" % tag))


class TestVoiceCache(unittest.TestCase):
    """A/B/D：缓存键与命中行为。"""

    def setUp(self):
        self.text = "缓存契约测试文本"
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        """删掉本用例可能留下的缓存文件，保证用例可重复运行。"""
        p = voice_cache.cache_dir() / (voice_cache.key_of(self.text) + ".mp3")
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass

    def test_lookup_misses_before_store(self):
        """未存入前查找必须落空。"""
        self.assertEqual(voice_cache.lookup(self.text), "")

    def test_store_then_lookup_hits_cache_dir(self):
        """存入后再次查找必须命中，且落在缓存目录。"""
        src = _SynthStub(_tmp_voice_path("cache_src")).write()
        try:
            stored = voice_cache.store(self.text, src)
            self.assertTrue(os.path.exists(stored), "缓存文件未落盘")
            self.assertEqual(os.path.basename(os.path.dirname(stored)), "cache",
                             "成品未落在缓存目录")
            hit = voice_cache.lookup(self.text)
            self.assertEqual(hit, stored, "第二次查找未命中同一份成品")
        finally:
            for p in (src, voice_cache.lookup(self.text)):
                if p and os.path.exists(p):
                    os.remove(p)

    def test_key_depends_only_on_text(self):
        """同文本必同键；不同文本必不同键。"""
        self.assertEqual(voice_cache.key_of(self.text), voice_cache.key_of(self.text))
        self.assertNotEqual(voice_cache.key_of(self.text), voice_cache.key_of(self.text + "x"))

    def test_empty_text_has_no_key(self):
        """空文本不产生键，也永不命中。"""
        self.assertEqual(voice_cache.key_of("   "), "")
        self.assertEqual(voice_cache.lookup(""), "")


class TestRemoveVoiceFile(unittest.TestCase):
    """C：临时文件删得掉，缓存成品删不掉。"""

    def test_temp_file_is_removed(self):
        """临时目录里的合成产物推完即删。"""
        p = _SynthStub(_tmp_voice_path("temp")).write()
        message_flow.remove_voice_file(p)
        self.assertFalse(os.path.exists(p), "临时语音未被删除")

    def test_cache_file_is_kept(self):
        """缓存目录里的成品必须保留，否则下次同文本又要重合成。"""
        cache_dir = voice_cache.cache_dir()
        p = cache_dir / "test_keep_me.mp3"
        p.write_bytes(b"stub-audio")
        try:
            message_flow.remove_voice_file(str(p))
            self.assertTrue(p.exists(), "缓存成品被误删")
        finally:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass

    def test_empty_path_is_noop(self):
        """空路径直接返回，不抛异常。"""
        message_flow.remove_voice_file("")
        message_flow.remove_voice_file(None)


if __name__ == "__main__":
    unittest.main()
