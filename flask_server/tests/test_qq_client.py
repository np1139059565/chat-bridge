"""QQ 协议层测试（qq_client 执行路径）

背景：
  该模块此前零覆盖。它是 QQ 通道唯一的收发实现，
  token 续期、网关地址获取、下行事件分派任一环出错，
  表现都是「连上了但收不到消息」或「发送全部失败」，且不易自查。

覆盖点：
  1. 请求体构造：文本与 Markdown 两种形态的字段差异
  2. token：获取成功、响应缺字段、网络异常、未过期不刷新、过期触发刷新
  3. 取网关：token 失效短路、成功、401 清 token、非 401 保留、普通异常
  4. 发送：无 token、成功、地址带 openid、HTTP 错误带详情、普通异常
  5. 下行分派：坏 JSON 与未知 op 忽略、五种 op 各自路由
  6. 事件派发：序号与最近事件维护、回调异常吞掉、分派表缓存
  7. 连接：鉴权包、断开复位、启停幂等与降级、心跳不重复

写法说明：
  断言雷同的用例合并到同一方法内，分段注释说明各自验证什么。

运行：python -m pytest tests/test_qq_client.py -q
"""
import io
import json
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import qq_client as qc


def _http_error(code, body=b""):
    """构造带响应体的 HTTPError，用于模拟服务端拒绝。

    @param code HTTP 状态码
    @param body 响应体字节
    """
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body))


class _FakeWs:
    """模拟 WebSocket 连接，记录发出的帧与关闭动作。"""

    def __init__(self, raise_on_send=False):
        self.sent = []
        self.closed = False
        self._raise = raise_on_send

    def send(self, data):
        """记录发出的数据；可配置为抛异常以测心跳中断。"""
        if self._raise:
            raise RuntimeError("连接已断")
        self.sent.append(data)

    def close(self):
        """记录关闭动作。"""
        self.closed = True


def _client(token="tok", expire=0):
    """构造一个已注入 token 的客户端，避免测试触网。

    @param token 初始 token
    @param expire 过期时间戳
    @returns 客户端实例
    """
    c = qc.QQClient("app", "secret", lambda t, d: None)
    c._token = token
    c._token_expire = expire
    return c


class BodyAndTokenTest(unittest.TestCase):
    """请求体构造与 token 管理。"""

    def test_body_shapes(self):
        """文本走 msg_type=0 且无 markdown 字段；Markdown 走 2 且 content 留空。"""
        b = qc._c2c_body("你好", "m1", 3, False)
        self.assertEqual((b["msg_type"], b["content"], b["msg_id"], b["msg_seq"]),
                         (0, "你好", "m1", 3))
        self.assertNotIn("markdown", b)
        b = qc._c2c_body("**粗体**", "m2", 1, True)
        self.assertEqual(b["msg_type"], 2)
        self.assertEqual(b["markdown"]["content"], "**粗体**")
        self.assertEqual(b["content"], "")

    def test_refresh_cases(self):
        """成功写入 token 与过期时间；缺 access_token 判失败；网络异常返回 False。"""
        c = _client(token="")
        c._http_post = lambda url, body, headers=None: {
            "access_token": "new_tok", "expires_in": 7200}
        self.assertTrue(c.refresh_token())
        self.assertEqual(c._token, "new_tok")
        self.assertGreater(c._token_expire, 0)
        # 响应里没有 access_token：不能带着空 token 去连
        c = _client(token="")
        c._http_post = lambda url, body, headers=None: {"expires_in": 7200}
        self.assertFalse(c.refresh_token())
        self.assertEqual(c._token, "")
        # 网络异常不穿透
        c = _client(token="")

        def _boom(*a, **k):
            """模拟请求失败。"""
            raise RuntimeError("断网")
        c._http_post = _boom
        self.assertFalse(c.refresh_token())

    def test_ensure_token_and_header(self):
        """未过期不刷新；过期触发刷新；鉴权头固定为 QQBot 前缀。"""
        c = _client(token="t", expire=10 ** 12)
        called = {"n": 0}

        def _r():
            """计数刷新调用。"""
            called["n"] += 1
            return True
        c.refresh_token = _r
        self.assertTrue(c._ensure_token())
        self.assertEqual(called["n"], 0)
        c = _client(token="t", expire=0)
        c.refresh_token = lambda: True
        self.assertTrue(c._ensure_token())
        self.assertEqual(_client("abc")._auth_header()["Authorization"], "QQBot abc")


class GatewayAndSendTest(unittest.TestCase):
    """取网关地址与发送单聊消息。"""

    def test_gateway_short_circuit_and_success(self):
        """token 失效时短路不发请求；token 有效时返回网关地址。"""
        c = _client(token="")
        c.refresh_token = lambda: False
        c._http_get = lambda *a, **k: self.fail("不该发请求")
        self.assertEqual(c._get_gateway(), "")
        c = _client(expire=10 ** 12)
        c._http_get = lambda url, headers=None: {"url": "wss://gw"}
        self.assertEqual(c._get_gateway(), "wss://gw")

    def test_gateway_failure_paths(self):
        """401 清 token；非 401 保留；普通异常返回空串。"""
        # 401：token 已作废，必须清空，否则会带废 token 死循环重试
        c = _client(expire=10 ** 12)

        def _401(*a, **k):
            """模拟 401。"""
            raise _http_error(401, b"unauthorized")
        c._http_get = _401
        self.assertEqual(c._get_gateway(), "")
        self.assertEqual(c._token, "")
        # 非 401：token 本身没问题，保留
        c = _client(expire=10 ** 12)

        def _500(*a, **k):
            """模拟 500。"""
            raise _http_error(500, b"oops")
        c._http_get = _500
        self.assertEqual(c._get_gateway(), "")
        self.assertEqual(c._token, "tok")
        # 普通异常
        c = _client(expire=10 ** 12)

        def _timeout(*a, **k):
            """模拟超时。"""
            raise TimeoutError("超时")
        c._http_get = _timeout
        self.assertEqual(c._get_gateway(), "")

    def test_send_no_token(self):
        """拿不到 token 时返回 no_token，调用方可据此区分原因。"""
        c = _client(token="")
        c.refresh_token = lambda: False
        self.assertEqual(c.send_c2c("u1", "hi"), (False, "no_token"))

    def test_send_success(self):
        """成功后返回服务端响应体，且请求地址带上接收方 openid。"""
        c = _client(expire=10 ** 12)
        seen = {}

        def _post(url, body, headers=None):
            """记录请求地址并返回响应。"""
            seen["url"] = url
            return {"id": "m1"}
        c._http_post = _post
        ok, data = c.send_c2c("openid-abc", "hi", msg_id="x", msg_seq=2)
        self.assertTrue(ok)
        self.assertEqual(data["id"], "m1")
        self.assertIn("openid-abc", seen["url"])

    def test_send_errors(self):
        """HTTP 错误带状态码与平台说明；普通异常转字符串；响应体读不出返回空串。"""
        c = _client(expire=10 ** 12)

        def _400(*a, **k):
            """模拟 400 并带说明。"""
            raise _http_error(400, "内容违规".encode("utf-8"))
        c._http_post = _400
        ok, err = c.send_c2c("u1", "hi")
        self.assertFalse(ok)
        self.assertIn("400", err)
        self.assertIn("内容违规", err)
        c = _client(expire=10 ** 12)

        def _conn(*a, **k):
            """模拟连接失败。"""
            raise ConnectionError("连不上")
        c._http_post = _conn
        ok, err = c.send_c2c("u1", "hi")
        self.assertFalse(ok)
        self.assertIn("连不上", err)

        class _Bad:
            def read(self):
                """模拟响应体读取失败。"""
                raise RuntimeError("读不了")
        self.assertEqual(qc.QQClient._http_error_detail(_Bad()), "")


class MessageDispatchTest(unittest.TestCase):
    """下行消息分派与事件派发。"""

    def test_bad_input_ignored(self):
        """非 JSON 与未知 op 都直接忽略，不能让长连接线程崩掉。"""
        c = _client()
        c._on_message(_FakeWs(), "not json")
        c._on_message(_FakeWs(), json.dumps({"op": 999}))

    def test_op_routing(self):
        """op=0 派发；op=10 握手换算间隔；op=7/9 关闭连接；op=9 清 token。"""
        c = _client()
        seen = []
        c.on_event = lambda t, d: seen.append(t)
        c._on_message(_FakeWs(), json.dumps({"op": 0, "t": "C2C_MESSAGE_CREATE", "d": {}}))
        self.assertEqual(seen, ["C2C_MESSAGE_CREATE"])
        got = {}
        c._start_heartbeat = lambda ws, interval: got.update({"interval": interval})
        c._on_message(_FakeWs(), json.dumps({"op": 10, "d": {"heartbeat_interval": 41250}}))
        self.assertAlmostEqual(got["interval"], 41.25)
        ws = _FakeWs()
        _client()._on_message(ws, json.dumps({"op": 7}))
        self.assertTrue(ws.closed)
        # 鉴权失败必须清 token，否则重连还是废 token
        c = _client(token="bad")
        ws = _FakeWs()
        c._on_message(ws, json.dumps({"op": 9}))
        self.assertEqual(c._token, "")
        self.assertTrue(ws.closed)
        # 心跳确认无动作，且不得抛异常
        _client()._on_message(_FakeWs(), json.dumps({"op": 11}))

    def test_dispatch_state(self):
        """序号与最近事件都要记下；消息缺序号时保留上一次，不清掉恢复锚点。"""
        c = _client()
        c.on_event = lambda t, d: None
        c._op_dispatch(_FakeWs(), {"s": 42, "t": "READY", "d": {"x": 1}})
        self.assertEqual((c._seq, c._last_event), (42, "READY"))
        c._op_dispatch(_FakeWs(), {"t": "X", "d": {}})
        self.assertEqual(c._seq, 42)

    def test_callback_exception_swallowed(self):
        """上层回调抛异常必须吞掉，否则整个长连接线程退出。"""
        c = _client()

        def _boom(t, d):
            """模拟上层处理失败。"""
            raise RuntimeError("处理炸了")
        c.on_event = _boom
        c._op_dispatch(_FakeWs(), {"t": "X", "d": {}})

    def test_handler_table_cached(self):
        """分派表只构建一次，且包含事件派发入口。"""
        c = _client()
        first = c._op_handler_table()
        self.assertIs(c._op_handler_table(), first)
        self.assertIn(qc.OP_DISPATCH, first)


class ConnectLifecycleTest(unittest.TestCase):
    """连接生命周期：鉴权包、启停、心跳。"""

    def test_on_open_and_close(self):
        """连上后发鉴权包；断开后状态位复位。"""
        c = _client(token="abc", expire=10 ** 12)
        ws = _FakeWs()
        c._on_open(ws)
        self.assertTrue(c._ws_connected)
        payload = json.loads(ws.sent[0])
        self.assertEqual(payload["op"], qc.OP_IDENTIFY)
        self.assertEqual(payload["d"]["token"], "QQBot abc")
        self.assertEqual(payload["d"]["intents"], qc.DEFAULT_INTENTS)
        c._on_close(_FakeWs(), 1000, "bye")
        self.assertFalse(c._ws_connected)

    def test_start_guards(self):
        """未装依赖降级不启动；已运行幂等返回；拿不到 token 不启动；正常启动置标记。"""
        old = qc.HAS_WS
        qc.HAS_WS = False
        try:
            self.assertFalse(_client().start())
        finally:
            qc.HAS_WS = old
        c = _client(expire=10 ** 12)
        c._running = True
        self.assertTrue(c.start())
        old = qc.HAS_WS
        qc.HAS_WS = True
        try:
            c = _client(token="")
            c.refresh_token = lambda: False
            self.assertFalse(c.start())
            c = _client(expire=10 ** 12)
            c._run_forever = lambda: None   # 线程空转即退，避免触网
            self.assertTrue(c.start())
            self.assertTrue(c._running)
        finally:
            qc.HAS_WS = old

    def test_stop(self):
        """停止时关闭连接并复位标记；关闭失败也照常停止。"""
        c = _client()
        c._running = True
        ws = _FakeWs()
        c._ws = ws
        c.stop()
        self.assertFalse(c._running)
        self.assertTrue(ws.closed)
        c = _client()
        c._running = True

        class _BadWs:
            def close(self):
                """模拟关闭异常。"""
                raise RuntimeError("关不掉")
        c._ws = _BadWs()
        c.stop()
        self.assertFalse(c._running)

    def test_heartbeat_and_contract(self):
        """心跳线程已在跑时不重复创建；QQ 通道需要被动回复窗口。"""
        c = _client()
        c._running = True
        ws = _FakeWs()
        c._ws = ws
        c._start_heartbeat(ws, 999)
        first = c._hb_thread
        c._start_heartbeat(ws, 999)
        self.assertIs(c._hb_thread, first)
        self.assertTrue(qc.QQClient.needs_window)


if __name__ == "__main__":
    unittest.main()
