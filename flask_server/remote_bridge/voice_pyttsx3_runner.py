"""远程桥接 —— 系统语音引擎（pyttsx3）的父进程侧调度

职责：把待合成文本写入临时文件，拉起 pyttsx3 子进程，并处理超时与失败。

为何独立成模块：
- 这块逻辑只关心「父进程如何驱动子进程」，与三引擎选择、并发闸门等
  合成主流程无关，拆开后主流程更短，本模块可单独测试与演进；
- 子进程脚本本身是 pyttsx3_worker.py，本模块是它在父进程一侧的对手方，
  两者成对阅读更清楚。

超时由调用方传入而非模块内常量：合成超时属于合成策略，应由主流程统一持有。
"""
import os
import subprocess
import sys


def write_synth_text(text_path, text):
    """把待合成文本写入临时文件。

    文本走临时文件而非命令行参数：朗读文本可能很长、含引号与换行，
    直接拼进命令行容易因转义失败而报错。

    @param text_path 临时文本路径
    @param text      待合成文本（可为空）
    @returns 失败时返回错误描述字符串；成功返回 None
    """
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text or "")
    except OSError as e:
        return "写入合成文本失败：%s" % e
    return None


def run_worker(worker, text_path, wav_path, voice, rate, timeout):
    """拉起子进程执行合成，并处理超时与非零退出。

    超时处理要点：杀掉整个子进程而非只放弃等待。SAPI 是进程级单例资源，
    子进程被杀死后资源随进程回收，主进程不会留下卡死的僵尸线程。

    @param worker    合成脚本路径
    @param text_path 临时文本路径
    @param wav_path  输出 WAV 路径
    @param voice     音色名（可为空）
    @param rate      语速（整数）
    @param timeout   超时秒数
    @returns (ok, error)：ok 为 True 表示子进程成功产出 WAV，error 为错误描述
    """
    proc = subprocess.Popen(
        [sys.executable, worker, text_path, wav_path, voice, str(rate)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    _, err = _wait_or_kill(proc, timeout)
    if err:
        return False, err
    return _check_output(proc, err, wav_path)


def _wait_or_kill(proc, timeout):
    """等待子进程结束；超时则杀掉并返回错误描述。

    超时处理要点：杀掉整个子进程而非只放弃等待。SAPI 是进程级单例资源，
    子进程被杀死后资源随进程回收，主进程不会留下卡死的僵尸线程。

    @param proc    子进程对象
    @param timeout 超时秒数
    @returns (err,): 超时返回错误描述字符串，正常结束返回 None
    """
    try:
        _, err = proc.communicate(timeout=timeout)
        return err
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return "pyttsx3 合成超时（%d 秒）" % timeout


def _check_output(proc, err, wav_path):
    """校验子进程退出码与产物有效性。

    @param proc     子进程对象（已结束）
    @param err      子进程 stderr 原始字节
    @param wav_path 输出 WAV 路径
    @returns (ok, error)
    """
    # 非零退出：把子进程 stderr 前 120 字符带回，便于定位具体原因
    if proc.returncode != 0:
        detail = (err or b"").decode("utf-8", "replace").strip()[:120]
        return False, "pyttsx3 失败：%s" % (detail or ("退出码 %d" % proc.returncode))
    # 产物缺失或为空，说明子进程虽正常退出但没合成出东西
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        return False, "pyttsx3 未产出有效音频"
    return True, None
