"""微信通道：协议层与客户端契约测试

为什么需要：
    微信通道上线后出现过两次真实故障，都是「没有任何测试覆盖」导致的：
    1. 指令全部哑掉——回执写死 QQ 的窗口检查，微信没有窗口概念；
    2. 配额按 24 小时累计——与平台「每条用户消息重置」的真实机制不符。
    两次都不是复杂 bug，而是没人验证过这些路径。

本文件覆盖：
    协议层 —— 版本编码、请求头、地址拼接必须与官方插件一致
    客户端 —— QQ 兼容签名、窗口标记、凭证读写、会话过期识别

推送与指令相关的用例见 test_weixin_router.py。
运行：python -m pytest tests/test_weixin_protocol.py -q
"""
import base64
import os
import sys
import tempfile

# 把 tests 目录加进导入路径，供导入同目录的公共替身模块。
# 仓库里其它测试只加服务端目录，本文件还要用同目录的 helper，故一并加。
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from remote_bridge import weixin_proto as proto          # noqa: E402
from remote_bridge.weixin_client import WeixinClient    # noqa: E402

from weixin_test_helpers import FakeWeixinClient         # noqa: E402


# ============ 协议层 ============
class TestProto:
    """协议常量与编码必须与官方插件一致，否则服务端直接拒绝。"""

    def test_client_version_encoding_matches_official(self):
        """版本号编码：major<<16 | minor<<8 | patch，与官方 buildClientVersion 一致。"""
        assert proto.build_client_version("2.4.10") == ((2 << 16) | (4 << 8) | 10)
        assert proto.build_client_version("1.0.11") == ((1 << 16) | (0 << 8) | 11)

    def test_client_version_handles_malformed_input(self):
        """残缺或非数字版本号不应抛异常，缺失段按 0 处理。"""
        assert proto.build_client_version("1") == (1 << 16)
        assert proto.build_client_version("") == 0
        assert proto.build_client_version("a.b.c") == 0

    def test_wechat_uin_is_base64_of_decimal_string(self):
        """X-WECHAT-UIN 是「随机数→十进制字符串→base64」，不是二进制打包。

        这两种做法产出的头部值不同，用错会被服务端判为非法请求。
        """
        for _ in range(20):
            uin = proto.random_wechat_uin()
            decoded = base64.b64decode(uin).decode("utf-8")
            assert decoded.isdigit(), "解码后必须是纯十进制数字串"
            assert 0 <= int(decoded) <= 0xFFFFFFFF

    def test_headers_contain_all_required_fields(self):
        """请求头必须齐全：鉴权类型、应用标识、客户端版本、随机 uin。"""
        h = proto.build_headers("tok")
        assert h["AuthorizationType"] == "ilink_bot_token"
        assert h["iLink-App-Id"] == proto.ILINK_APP_ID
        assert h["iLink-App-ClientVersion"] == str(proto.ILINK_APP_CLIENT_VERSION)
        assert h["Authorization"] == "Bearer tok"
        assert "X-WECHAT-UIN" in h

    def test_headers_omit_authorization_without_token(self):
        """无令牌时不应带 Authorization 头（扫码登录阶段就是这种状态）。"""
        assert "Authorization" not in proto.build_headers("")

    def test_base_info_shape(self):
        """每个请求体都要带 base_info，字段名必须准确。"""
        info = proto.base_info()
        assert set(info.keys()) == {"channel_version", "bot_agent"}
        assert info["channel_version"] == proto.CHANNEL_VERSION

    def test_join_url_handles_trailing_slash(self):
        """基地址有无末尾斜杠都应拼出正确 URL。"""
        expected = "https://example.com/ilink/bot/getupdates"
        assert proto.join_url("https://example.com", "ilink/bot/getupdates") == expected
        assert proto.join_url("https://example.com/", "ilink/bot/getupdates") == expected

    def test_join_url_falls_back_to_default_base(self):
        """基地址为空时回退到默认地址，而不是拼出相对路径。"""
        assert proto.join_url("", "ilink/bot/getupdates").startswith(proto.DEFAULT_BASE)


# ============ 客户端契约 ============
class TestClientContract:
    """客户端必须满足指令层的调用契约。"""

    def test_needs_window_is_false(self):
        """微信没有被动回复窗口：该标记为假，指令层据此跳过窗口检查。

        这条是「指令全部哑掉」那个故障的直接回归防线。
        """
        assert WeixinClient.needs_window is False

    def test_send_c2c_accepts_qq_signature(self):
        """send_c2c 必须接受 QQ 那套参数，指令层才能原样调用。"""
        c = FakeWeixinClient()
        ok, _ = c.send_c2c("u1", "hello", msg_id="m1", msg_seq=3, markdown=True)
        assert ok is True
        assert c.sent == [("u1", "hello")]

    def test_send_c2c_ignores_qq_window_params(self):
        """窗口参数应被忽略：传空 msg_id 也必须能发出去。"""
        c = FakeWeixinClient()
        ok, _ = c.send_c2c("u1", "hi", msg_id="", msg_seq=0)
        assert ok is True and c.sent

    def test_context_token_roundtrip(self):
        """上下文令牌要能存能取；发送时必须原样回传。"""
        c = FakeWeixinClient()
        assert c.get_context("u1") == ""
        c.set_context("u1", "ct-abc")
        assert c.get_context("u1") == "ct-abc"

    def test_context_ignores_empty_values(self):
        """空令牌不应覆盖已有值。"""
        c = FakeWeixinClient()
        c.set_context("u1", "ct-1")
        c.set_context("u1", "")
        assert c.get_context("u1") == "ct-1"

    def test_cred_save_load_roundtrip(self):
        """凭证要能落盘并读回，且含全部必要字段。"""
        c = FakeWeixinClient()
        cred = {"token": "tk", "bot_id": "bid", "base_url": "https://x", "user_id": "u"}
        c.save_cred(cred)
        c._cred = None
        loaded = c.load_cred()
        assert loaded["token"] == "tk" and loaded["bot_id"] == "bid"
        c.clear_cred()
        assert c.load_cred() is None

    def test_has_cred_reflects_state(self):
        """有无凭证的判断要准确，供页面展示登录状态。"""
        c = FakeWeixinClient()
        assert c.has_cred() is False
        c.save_cred({"token": "tk", "bot_id": "b"})
        assert c.has_cred() is True
        c.clear_cred()

    def test_session_expired_detection(self):
        """-14 表示会话过期，必须能识别（否则会带着废令牌无限重试）。"""
        assert WeixinClient._is_session_expired({"ret": -14}) is True
        assert WeixinClient._is_session_expired({"errcode": -14}) is True
        assert WeixinClient._is_session_expired({"ret": 0}) is False
        assert WeixinClient._is_session_expired({}) is False

    def test_buf_persisted_to_disk(self):
        """长轮询游标必须落盘：否则重启会重放历史消息。"""
        c = FakeWeixinClient()
        c._save_buf("cursor-123")
        c._buf = ""
        assert c._load_buf() == "cursor-123"
        try:
            os.remove(c.buf_path)
        except OSError:
            pass

    def test_context_token_persisted_across_instances(self):
        """上下文令牌必须落盘：否则服务重启后发送全被拒。

        真实故障：令牌只存内存，重启即丢，而推送目标仍持久化着，
        于是「知道发给谁、却没带凭证」，每次发送都被服务端以
        prepare failed 拒绝，且重试永远无效。
        """
        tmp = tempfile.gettempdir()
        ctxp = os.path.join(tmp, 'wx_ctx_test.json')
        try:
            os.remove(ctxp)
        except OSError:
            pass
        a = WeixinClient(os.path.join(tmp, 'k1.json'), os.path.join(tmp, 'k2.txt'),
                         None, ctx_path=ctxp)
        a.set_context("u1", "token-abc")
        assert os.path.exists(ctxp), "设置令牌后应写盘"
        # 新实例模拟重启：内存为空，必须从磁盘恢复
        b = WeixinClient(os.path.join(tmp, 'k1.json'), os.path.join(tmp, 'k2.txt'),
                         None, ctx_path=ctxp)
        assert b.get_context("u1") == "token-abc", "重启后应能取回令牌"
        try:
            os.remove(ctxp)
        except OSError:
            pass

    def test_context_persistence_optional(self):
        """未给 ctx_path 时只存内存，不报错（测试与临时实例依赖此行为）。"""
        c = FakeWeixinClient()
        c.set_context("u1", "tok")
        assert c.get_context("u1") == "tok"
