"""
服务进程控制：以新参数重启自身。

把「重启服务」从 QQ 指令处理里抽出，供两处共用：
- QQ 指令 /restart（remote_bridge.command_panel）
- 前端改端口后的重启（routes.config_route 的新端点）

原理：起一个与父进程彻底脱离的子进程，父进程随后退出让出端口，
子进程稍候用给定参数重新拉起服务。
"""
import os
import subprocess
import sys
import threading


def restart_server(delay=3.0, extra_args=None, exit_delay=0.4):
    """延迟 delay 秒后用原解释器重启服务，并附加 extra_args。

    @param delay      子进程等待多久再拉起新服务（秒），给旧端口留出释放时间
    @param extra_args 附加到启动命令的参数列表，如 ['--port', '5001']
    @param exit_delay 父进程多久后退出（秒）。
        不立即退出，是给调用方（如 HTTP 响应）留出写回时间；
        退出太早会把还没发完的响应掐断。
    """
    # 在原始启动命令后追加新参数。
    # 注意：argparse 对重复的 --port 取最后一个，因此后追加的值会覆盖旧值，
    # 无需先把旧参数剔除。
    argv = [sys.executable] + list(sys.argv) + list(extra_args or [])
    # 子进程代码：先睡 delay 秒，再用 execv 就地替换为新的服务进程。
    code = "import time,os,sys;time.sleep(%s);os.execv(sys.executable,%r)" % (delay, argv)
    kw = {
        "cwd": os.getcwd(),
        "close_fds": True,               # 不继承监听 socket，避免端口被占
        "stdin": subprocess.DEVNULL,     # 与控制台解耦
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        # Windows 上必须用 DETACHED_PROCESS 才能真正脱离父进程；
        # start_new_session 在 Windows 是空操作，子进程会随父进程一起被终止。
        kw["creationflags"] = 0x00000008
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, "-c", code], **kw)
    # 延迟退出父进程：先让调用方的响应发出去，再让出端口。
    threading.Timer(exit_delay, lambda: os._exit(0)).start()
