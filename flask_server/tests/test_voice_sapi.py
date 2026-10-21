"""sapi 引擎的纯逻辑测试

覆盖点：
- 音色不存在时能从子进程输出中解析出音色名（用于告警，避免静默回落）
- 语速换算：WPM 到 SAPI 档位，并夹紧到合法范围

为何只测纯函数：真正合成要起 PowerShell 子进程、依赖 Windows 语音库，
不适合在单元测试里跑；把判定逻辑抽成纯函数后，这部分可跨环境稳定验证。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import voice_sapi_runner as sr


class ParseMissingVoiceTestCase(unittest.TestCase):
    """从子进程输出里解析缺失音色名。"""

    def test_returns_name_when_marker_present(self):
        """有标记时返回标记后的音色名。"""
        self.assertEqual(sr.parse_missing_voice("VOICE_NOT_FOUND:NoSuchVoice"), "NoSuchVoice")

    def test_name_with_spaces_preserved(self):
        """音色名含空格时完整保留，只按行切分。"""
        text = "VOICE_NOT_FOUND:Microsoft Huihui Desktop\n其它输出"
        self.assertEqual(sr.parse_missing_voice(text), "Microsoft Huihui Desktop")

    def test_ignores_surrounding_output(self):
        """标记前后的无关输出不影响解析。"""
        text = "some warning\nVOICE_NOT_FOUND:Foo Voice\nmore"
        self.assertEqual(sr.parse_missing_voice(text), "Foo Voice")

    def test_empty_when_no_marker(self):
        """无标记时返回空串。"""
        self.assertEqual(sr.parse_missing_voice("all good"), "")

    def test_empty_for_none_and_empty(self):
        """None 与空串都不报错，返回空串。"""
        self.assertEqual(sr.parse_missing_voice(None), "")
        self.assertEqual(sr.parse_missing_voice(""), "")


class WpmToSapiRateTestCase(unittest.TestCase):
    """WPM 到 SAPI 档位（-10~10）的换算。"""

    def test_baseline_is_zero(self):
        """默认 150 WPM 对应 0 档。"""
        self.assertEqual(sr.wpm_to_sapi_rate(150), 0)

    def test_faster_is_positive(self):
        """更快语速给出正档位。"""
        self.assertGreater(sr.wpm_to_sapi_rate(200), 0)

    def test_slower_is_negative(self):
        """更慢语速给出负档位。"""
        self.assertLess(sr.wpm_to_sapi_rate(100), 0)

    def test_clamped_to_upper_bound(self):
        """极高语速夹紧到上限 10。"""
        self.assertEqual(sr.wpm_to_sapi_rate(100000), 10)

    def test_clamped_to_lower_bound(self):
        """极低语速夹紧到下限 -10。"""
        self.assertEqual(sr.wpm_to_sapi_rate(-100000), -10)

    def test_invalid_falls_back_to_baseline(self):
        """非数字按默认基准处理，得到 0 档。"""
        self.assertEqual(sr.wpm_to_sapi_rate("not-a-number"), 0)
        self.assertEqual(sr.wpm_to_sapi_rate(None), 0)


if __name__ == "__main__":
    unittest.main()
