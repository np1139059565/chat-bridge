"""出向媒体公共骨架（channel.media）测试

为什么需要：
    每条通道推媒体的流程相同：从消息里收集图片 / 文件 / 语音 →
    逐件交给通道自己的发送函数 → 统计成功条数。
    只有「怎么发」是通道差异，「收什么、发几件、怎么计数」是共通的。
    抽到公共层后，新增通道不必再抄一遍这个循环。

覆盖内容：
    - 三类媒体都能被收集并交给发送函数
    - 语音只在 AI 消息上推（用户与工具消息没有朗读文本）
    - 发送函数返回失败时不计数
    - 无媒体时返回 0，不调用发送函数

运行：python -m pytest tests/test_channel_media.py -q
"""
from remote_bridge.channel import media


class TestPushCollected:
    """收集与发送的编排。"""

    def test_collects_all_three_kinds(self, tmp_path, monkeypatch):
        """图片、文件、语音各一件时，三件都交给发送函数。"""
        # 造三个真实存在的本地文件：收集层会校验存在性
        img = tmp_path / "a.png"
        img.write_bytes(b"png")
        f = tmp_path / "b.txt"
        f.write_text("x", encoding="utf-8")
        voice = tmp_path / "c.mp3"
        voice.write_bytes(b"mp3")

        # 替换收集函数：避免依赖真实的块解析与下载逻辑，
        # 这里要验证的是编排，不是解析
        monkeypatch.setattr(media, "collect_images", lambda m: [str(img)] if m["id"] == "m1" else [])
        monkeypatch.setattr(media, "collect_files", lambda m: [str(f)] if m["id"] == "m1" else [])
        monkeypatch.setattr(media, "collect_voice", lambda m, vm: (str(voice), "文字") if m["id"] == "m1" else ("", ""))
        # 语音分类：只有 ai 类消息才推语音
        monkeypatch.setattr(media, "_classify", lambda m: "ai")

        sent = []
        def send_fn(path, kind):
            """记录每一次发送并报告成功。"""
            sent.append((path, kind))
            return True

        n = media.push_collected(
            [{"id": "m1"}], {"voice": True}, {}, send_fn)
        # 三件都发出
        assert n == 3
        # 类型标注正确
        assert (str(img), "image") in sent
        assert (str(f), "file") in sent
        assert (str(voice), "voice") in sent

    def test_voice_only_for_ai(self, tmp_path, monkeypatch):
        """非 AI 消息不推语音。"""
        voice = tmp_path / "c.mp3"
        voice.write_bytes(b"mp3")
        monkeypatch.setattr(media, "collect_images", lambda m: [])
        monkeypatch.setattr(media, "collect_files", lambda m: [])
        monkeypatch.setattr(media, "collect_voice", lambda m, vm: (str(voice), "文字"))
        # 分类为用户消息
        monkeypatch.setattr(media, "_classify", lambda m: "user")

        sent = []
        def send_fn(path, kind):
            sent.append(kind)
            return True

        n = media.push_collected([{"id": "m1"}], {"voice": True}, {}, send_fn)
        # 一件都不发
        assert n == 0
        assert sent == []

    def test_failed_send_not_counted(self, tmp_path, monkeypatch):
        """发送函数返回失败时不计数。"""
        img = tmp_path / "a.png"
        img.write_bytes(b"png")
        monkeypatch.setattr(media, "collect_images", lambda m: [str(img)])
        monkeypatch.setattr(media, "collect_files", lambda m: [])
        monkeypatch.setattr(media, "collect_voice", lambda m, vm: ("", ""))
        monkeypatch.setattr(media, "_classify", lambda m: "ai")

        # 发送一律失败
        n = media.push_collected([{"id": "m1"}], {}, {}, lambda p, k: False)
        assert n == 0

    def test_no_media_skips_send(self, monkeypatch):
        """无媒体时不调用发送函数。"""
        monkeypatch.setattr(media, "collect_images", lambda m: [])
        monkeypatch.setattr(media, "collect_files", lambda m: [])
        monkeypatch.setattr(media, "collect_voice", lambda m, vm: ("", ""))
        monkeypatch.setattr(media, "_classify", lambda m: "ai")

        called = []
        def send_fn(path, kind):
            called.append(kind)
            return True

        n = media.push_collected([{"id": "m1"}], {}, {}, send_fn)
        assert n == 0
        assert called == []

    def test_voice_disabled_by_switch(self, tmp_path, monkeypatch):
        """语音开关关闭时不推语音。"""
        voice = tmp_path / "c.mp3"
        voice.write_bytes(b"mp3")
        monkeypatch.setattr(media, "collect_images", lambda m: [])
        monkeypatch.setattr(media, "collect_files", lambda m: [])
        monkeypatch.setattr(media, "collect_voice", lambda m, vm: (str(voice), "文字"))
        monkeypatch.setattr(media, "_classify", lambda m: "ai")

        n = media.push_collected([{"id": "m1"}], {"voice": False}, {}, lambda p, k: True)
        assert n == 0
