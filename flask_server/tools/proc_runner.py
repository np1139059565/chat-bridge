"""AI 工具调用镜像插件 —— 子进程执行（带健壮的超时保护）

供 run_command（内置）与自定义脚本工具（custom_tools.registry）共用。

为什么不能直接用 subprocess.run(timeout=...)：
    它超时后只 kill「直接子进程」，随后 communicate() 读输出管道直到 EOF。
    若子进程又派生了孙进程，孙进程继承着管道写端，EOF 永不到来，
    于是超时调用一直阻塞到孙进程自然退出——超时形同虚设。
    （实测：孙进程 sleep 8、设 timeout=3，实际 8.1 秒才返回。）

为什么 taskkill /T 也不够：
    /T 按父子链杀树。若子进程先退出、孙进程「挣脱」成孤儿（PPID 指向已死进程），
    /T 找不到它，杀不掉。
    （实测：子进程 spawn 孙进程后立即退出，taskkill /T 后孙进程仍存活。）

本模块的应对：
    既然杀不干净是操作系统层面的限制，就**不去依赖「必须杀死所有进程」**。
    改用「读取线程 + 主线程超时」：
      1. 读取线程负责读走 stdout / stderr（daemon，读不到 EOF 就一直挂着，不碍事）；
      2. 主线程只 wait(timeout)，超时立即杀树（尽力）+ 关闭管道读端，然后返回。
    这样无论孙进程是否挣脱、是否持有管道，**调用方都能在超时后立即拿到结果**。

权衡（明确记录）：
    超时后「挣脱的孙进程」可能残留在系统里，无法从本进程可靠杀死。
    这是 OS 层面限制，接受它；换来的是调用方绝不被拖住。
"""
import collections
import os
import signal
import subprocess
import threading


# 子进程执行结果：超时与否都用同一结构承载，调用方据 timed_out 判断。
ProcResult = collections.namedtuple(
    "ProcResult", ["returncode", "stdout", "stderr", "timed_out"])


def _kill_tree(proc):
    """尽力杀死进程及其子孙进程（不保证成功，见模块说明）。

    已退出的进程直接跳过；杀树失败时兜底只杀直接子进程。
    「挣脱的孙进程」可能杀不到，此处不纠缠——调用方靠「不等 EOF」保命。
    @param proc Popen 实例
    """
    if proc.poll() is not None:
        return   # 已退出，无需再杀
    try:
        if os.name == "nt":
            # /F 强制终止、/T 连子孙进程、/PID 指定树的根
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10,
            )
        else:
            # 杀整个进程组（start_new_session 已让子进程自成一組）
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        # 兜底：至少杀掉直接子进程
        try:
            proc.kill()
        except Exception:
            pass


def _close_quietly(stream):
    """静默关闭一个流对象；None 或已关闭时忽略。

    关闭读端的目的：促使仍持有写端的进程在下次写入时收到 EPIPE，
    从而主动退出——是「杀不死孙进程」的补充手段。
    """
    try:
        if stream:
            stream.close()
    except Exception:
        pass


def run_with_tree_timeout(cmd, cwd=None, timeout=60, env=None):
    """执行命令，超时后立即返回（不等可能持有管道的孙进程）；返回 ProcResult。

    与 subprocess.run 的关键差异：超时能真正生效——不依赖杀死全部进程，
    而是不让主线程去等管道 EOF（见模块说明）。

    @param cmd     命令列表
    @param cwd     工作目录
    @param timeout 超时秒数
    @param env     环境变量字典
    @returns ProcResult(returncode, stdout, stderr, timed_out)
    @raises FileNotFoundError 解释器 / 程序缺失
    """
    proc = _spawn_process(cmd, cwd, env)
    # 读取线程：把输出读进缓冲区。它是 daemon，读不到 EOF 就一直挂着，
    # 但不妨碍主线程按超时返回。
    out_chunks, err_chunks = [], []
    reader = _start_reader(proc, out_chunks, err_chunks)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # 超时：杀树 + 关管道，立即返回，不等读取线程
        _abort_on_timeout(proc)
        return ProcResult(None, "", "", True)
    # 正常退出：给读取线程一个很短的时间收尾。
    # 进程已退出时 EOF 通常立即到达，读取线程瞬间结束；
    # 但若存在「孤儿孙进程持管道」，EOF 不到、读取线程会一直挂着——
    # 故此处只等很短时间，拿不到就带着已读到的内容返回，绝不陪它干等。
    reader.join(timeout=1)
    return ProcResult(proc.returncode, "".join(out_chunks), "".join(err_chunks), False)


def _spawn_process(cmd, cwd, env):
    """启动子进程并接好管道，返回 Popen 对象。

    @param cmd 命令列表
    @param cwd 工作目录
    @param env 环境变量字典
    @returns Popen 对象
    @raises FileNotFoundError 解释器 / 程序缺失
    """
    kwargs = {}
    if os.name != "nt":
        # POSIX：自建会话，os.killpg 才能按组杀
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            shell=False, env=env, **kwargs,
        )
    except FileNotFoundError as e:
        # 解释器或程序缺失：交由调用方归类为环境类错误
        raise FileNotFoundError("无法启动命令（解释器或程序缺失）：%s" % e)


def _start_reader(proc, out_chunks, err_chunks):
    """启动守护读取线程，把子进程输出读进给定缓冲区，返回线程对象。

    @param proc       子进程
    @param out_chunks 标准输出缓冲（就地追加）
    @param err_chunks 标准错误缓冲（就地追加）
    @returns 读取线程对象
    """
    def _reader():
        try:
            o, e = proc.communicate()
            out_chunks.append(o or "")
            err_chunks.append(e or "")
        except Exception:
            # 管道被主线程关闭时读取会抛错，忽略即可
            pass

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    return reader


def _abort_on_timeout(proc):
    """超时处置：尽力杀进程树，并关闭管道读端让持写端的进程收到 EPIPE。

    @param proc 子进程
    """
    # 1) 尽力杀树（可能杀不掉挣脱的孙进程，见模块说明）
    _kill_tree(proc)
    # 2) 关闭管道读端：让仍持写端的进程下次写入时收到 EPIPE
    _close_quietly(proc.stdout)
    _close_quietly(proc.stderr)
