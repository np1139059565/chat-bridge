# -*- coding: utf-8 -*-
"""
手机本地 AI 接口服务（QPython 版）

作用：让手机上的其它软件可以通过标准 HTTP 接口使用网页 AI。
链路：外部软件 -> 本服务 -> Firefox 扩展 -> 网页 AI -> 扩展抓取 -> 本服务 -> 外部软件。

用法：在 QPython 里新建文件、粘贴全文、运行。保持在前台。
验证：浏览器打开 http://127.0.0.1:8000/health
"""
import json
import queue
import threading
import time
import uuid
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer


# ============ 全局状态 ============

# 待处理任务队列：扩展定时来取
_task_queue = queue.Queue()

# 任务等待信号与结果：task_id -> Event / 结果字典
_task_events = {}
_task_results = {}
_lock = threading.Lock()

# 任务租约记录：task_id -> {"taken_at": 时间戳}
# 用途：扩展领走后若迟迟不回传（崩溃 / 断网），据此判定超时并明确报错，
# 而不是让服务端一直干等到总超时。
_task_leases = {}

# 扩展领走任务后，多久没回传就视为失败（秒）
LEASE_TIMEOUT = 30


# ============ 辅助 ============

def estimate_tokens(text):
    """粗略估算 token 用量：中文 1 字 1 token，其它 4 字符 1 token。

    网页 AI 不展示真实用量，只能估算。返回的是近似值，不是真实计费数据。
    """
    if not text:
        return 0
    zh = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return zh + ((len(text) - zh) // 4)


def _cleanup_stale():
    """清理已超时的任务租约，返回被清理的 task_id 列表。

    扩展领走任务后若崩溃或断网，永远不会回传结果。
    这里把超过 LEASE_TIMEOUT 的租约清掉，并唤醒等待方让它明确失败。
    """
    now = time.time()
    stale = []
    with _lock:
        for tid, lease in list(_task_leases.items()):
            if now - lease.get("taken_at", now) > LEASE_TIMEOUT:
                stale.append(tid)
        for tid in stale:
            _task_leases.pop(tid, None)
            _task_results[tid] = {"error": "扩展领走任务后超时未回传"}
            ev = _task_events.get(tid)
        # 唤醒放在锁外进行，避免持锁调用用户代码
        for tid in stale:
            ev = _task_events.get(tid)
            if ev:
                ev.set()
    return stale


# ============ HTTP 处理 ============

class ApiHandler(BaseHTTPRequestHandler):
    """处理全部 HTTP 请求。"""

    def log_message(self, fmt, *args):
        """日志打到 QPython 控制台，便于观察请求往来。"""
        print("[HTTP]", self.path)

    def _send_json(self, status, obj):
        """返回 JSON 响应，统一带上 CORS 头。"""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """浏览器跨域预检。"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        """GET：健康检查、扩展领任务。"""
        if self.path.startswith("/health"):
            with _lock:
                pending = _task_queue.qsize()
                waiting = len(_task_events)
                leased = len(_task_leases)
            self._send_json(200, {
                "ok": True,
                "service": "phone-ai-api",
                "pending_tasks": pending,
                "waiting_requests": waiting,
                "active_leases": leased
            })
            return

        if self.path.startswith("/ext/get_task"):
            # 顺手清理超时租约，保证状态自愈
            _cleanup_stale()
            try:
                task = _task_queue.get_nowait()
            except queue.Empty:
                self._send_json(200, {"task_id": None})
                return
            # 登记租约：扩展领走后必须在 LEASE_TIMEOUT 内回传
            with _lock:
                _task_leases[task["task_id"]] = {"taken_at": time.time()}
            self._send_json(200, task)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        """POST：标准 AI 接口、扩展回传结果。"""
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:
            req = {}

        if self.path.startswith("/ext/submit_result"):
            self._handle_submit(req)
            return
        if self.path.startswith("/v1/chat/completions"):
            self._handle_chat(req)
            return
        self._send_json(404, {"error": "not found"})

    def _handle_submit(self, req):
        """扩展回传结果：记录并唤醒等待中的请求。"""
        task_id = req.get("task_id")
        if not task_id:
            self._send_json(400, {"error": "missing task_id"})
            return
        with _lock:
            # 清除租约：该任务已有结论，不再计入超时判定
            _task_leases.pop(task_id, None)
            _task_results[task_id] = req
            ev = _task_events.get(task_id)
        if ev:
            ev.set()
        else:
            # 服务端已不再等待该任务（如已超时返回）：记日志但不报错，
            # 避免扩展因回传迟到而反复重试
            print("[警告] 收到已过期任务的回传:", task_id[:8])
        self._send_json(200, {"ok": True})

    def _handle_chat(self, req):
        """标准 AI 接口：建任务 → 等扩展执行 → 按标准格式返回。"""
        messages = req.get("messages") or []
        prompt = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                prompt = m.get("content") or ""
                break
        if not prompt:
            self._send_json(400, {"error": {"message": "no user message"}})
            return

        task_id = str(uuid.uuid4())
        ev = threading.Event()
        with _lock:
            _task_events[task_id] = ev
        _task_queue.put({"task_id": task_id, "prompt": prompt})

        # 等待：总上限 180 秒。租约超时会提前唤醒并带回错误。
        ok = ev.wait(timeout=180)
        with _lock:
            res = _task_results.pop(task_id, {})
            _task_events.pop(task_id, None)
            _task_leases.pop(task_id, None)

        if not ok:
            self._send_json(504, {"error": {"message": "等待扩展超时（180 秒）"}})
            return

        # 关键：扩展报错必须原样转成错误响应，不能当成空内容返回
        err = res.get("error") or ""
        if err:
            self._send_json(502, {"error": {"message": "网页操作失败：" + str(err)}})
            return

        content = res.get("content") or ""
        thinking = res.get("thinking") or ""
        if not content:
            self._send_json(502, {"error": {"message": "扩展未抓到回答内容"}})
            return

        pt = estimate_tokens(prompt)
        ct = estimate_tokens(content)
        self._send_json(200, {
            "id": "chatcmpl-" + task_id[:8],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.get("model") or "web-ai",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": thinking
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": pt + ct,
                "note": "tokens 为估算值，网页 AI 不提供真实用量"
            }
        })


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """多线程服务器：一个请求等待时不会堵住其它请求。"""
    daemon_threads = True


if __name__ == "__main__":
    port = 8000
    server = ThreadedHTTPServer(("127.0.0.1", port), ApiHandler)
    print("=" * 44)
    print("手机 AI 接口服务已启动")
    print("健康检查: http://127.0.0.1:%d/health" % port)
    print("接口地址: http://127.0.0.1:%d/v1/chat/completions" % port)
    print("=" * 44)
    server.serve_forever()
