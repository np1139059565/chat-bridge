"""
服务进程控制：重启与滚动重启。

- restart_server：先退出旧进程、再拉起新进程（同端口重启用）。
  同端口不能并行监听，只能先退再起。
- rolling_restart：先以新端口起新进程、确认可连后旧进程再退出。
  这是「改端口」的标准做法：旧服务在新服务确认可用前一直存活，
  因此不存在「旧端口已让出、新端口还没起来」的真空期。

新端口通过命令行参数 --port 传给新进程（server.py 的入口负责解析）。
新进程的输出写入 data/logs/restart-YYYY-MM-DD.log（按天分文件），便于排查启动失败。
按天分文件可避免单文件无限增长；旧文件在服务重启释放后可单独清理。
"""
import os
import subprocess
import sys
import threading
import time
import urllib.request

# flask_server 根目录（本文件在 core/ 下）
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log_path():
    """新进程输出日志路径：按天分文件，restart-YYYY-MM-DD.log。

    按天分文件的原因：重启日志会持续追加，单文件会无限增长（曾达数十 MB）。
    按天切分后，旧文件可在服务重启释放后单独清理，不影响当天记录。
    @returns 绝对路径（不依赖运行时工作目录）
    """
    day = time.strftime("%Y-%m-%d")
    return os.path.join(_APP_DIR, "data", "logs", "restart-%s.log" % day)


def _spawn(extra_args=None, delay=0.0):
    """起一个与父进程彻底脱离的子进程，重新拉起当前服务。

    @param extra_args 附加到启动命令的参数，如 ['--port', '5006']
    @param delay      子进程等待多久再启动（秒）；0 表示立即
    """
    argv = [sys.executable] + list(sys.argv) + list(extra_args or [])
    if delay and delay > 0:
        # 用一段引导代码先睡再 execv，避免子进程与父进程抢端口
        code = "import time,os,sys;time.sleep(%s);os.execv(sys.executable,%r)" % (delay, argv)
        popen_cmd = [sys.executable, "-c", code]
    else:
        popen_cmd = argv
    # 把新进程输出重定向到日志文件，方便排查启动失败。
    # 之前丢弃输出，导致新服务起不来时无从查因。
    log_path = _log_path()
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_f = open(log_path, "a", encoding="utf-8", buffering=1)
    except Exception:
        log_f = subprocess.DEVNULL
    kw = {
        "cwd": _APP_DIR,
        "close_fds": True,               # 不继承监听 socket，避免端口被占
        "stdin": subprocess.DEVNULL,     # 与控制台解耦
        "stdout": log_f,
        "stderr": log_f,
    }
    if os.name == "nt":
        # Windows 上必须用 DETACHED_PROCESS 才能真正脱离父进程；
        # start_new_session 在 Windows 是空操作，子进程会随父进程一起被终止。
        kw["creationflags"] = 0x00000008
    else:
        kw["start_new_session"] = True
    subprocess.Popen(popen_cmd, **kw)


def _port_alive(port, host="127.0.0.1"):
    """探测某端口是否已有服务在监听（能响应 HTTP）。"""
    try:
        r = urllib.request.urlopen("http://%s:%d/config" % (host, port), timeout=2)
        return getattr(r, "status", 200) == 200
    except Exception:
        return False


def restart_server(delay=3.0, exit_delay=0.4):
    """先退出旧进程、再拉起新进程（同端口重启用）。

    同端口不能并行监听，故只能先退再起。旧进程延迟 exit_delay 秒退出，
    给调用方的 HTTP 响应留出写回时间。
    """
    _spawn(delay=delay)
    threading.Timer(exit_delay, lambda: os._exit(0)).start()


def rolling_restart(port, host="127.0.0.1", timeout=25.0):
    """滚动重启：先以新端口起新服务，确认可连后旧服务再退出。

    旧服务在新服务确认可用前一直存活，因此不会出现服务真空；
    新端口若在时限内起不来，旧服务保持运行（不退出）。
    本函数立即返回，实际的「确认后退出」在后台线程进行。

    @param port     新端口（通过 --port 传给新进程）
    @param host     探测用的主机（一般 127.0.0.1）
    @param timeout  等待新服务就绪的总时长（秒）
    """
    def _worker():
        # 1) 起新进程（--port 带新端口），旧服务此刻仍在运行
        _spawn(extra_args=["--port", str(port)])
        # 2) 轮询探测新端口，直到通或超时
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _port_alive(port, host):
                time.sleep(0.3)          # 再稳一下，确保能稳定响应
                os._exit(0)              # 3) 新服务确认可用，旧服务退出
            time.sleep(0.5)
        # 超时未确认：不动，旧服务继续运行（宁可保留旧服务，也不真空）

    threading.Thread(target=_worker, daemon=True).start()
