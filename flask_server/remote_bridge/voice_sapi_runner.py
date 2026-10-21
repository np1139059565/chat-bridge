"""远程桥接 —— 系统语音引擎（SAPI）的父进程侧调度

职责：把待合成文本与一段 PowerShell 脚本写入临时文件，拉起 powershell
子进程调用 Windows 自带的 System.Speech 合成 WAV，再编码为 MP3。

为何需要本模块：
- pyttsx3 依赖 pywin32，二者都需 pip 安装；网络受限的机器上装不上，
  系统语音整条链路就不可用。
- Windows 自带 System.Speech（SAPI5）无需任何第三方包，由 PowerShell
  直接调用即可离线合成，是零依赖的保底路径。

编码要点（关键）：
- 朗读文本单独写 UTF-8 文件，脚本内用 UTF8 显式读入。
- PowerShell 5.1 按本地 ANSI 解析脚本文件，故脚本本身保持纯 ASCII；
  若脚本里直接写中文，字节会被误判、引号配平被打乱，直接语法报错。

并发与超时：
- 合成在独立子进程中完成，超时即杀进程，与项目既有的「独立进程 + 超时」
  故障隔离模型一致。
- 超时值由调用方传入，属合成策略，由主流程统一持有。
"""
import os
import shutil
import subprocess

from . import bridge_log
from . import voice_mp3
from .voice_pyttsx3_runner import write_synth_text


def log(*args):
    """统一前缀日志：与合成模块同一前缀，便于按来源检索。"""
    bridge_log.write("[bridge][tts]", *args)


# SAPI 的语速属性是 -10 ~ 10 的档位，而配置里存的是每分钟词数（WPM）。
# 以 150 WPM 为 0 档，每差 15 WPM 平移一档，并夹紧到合法范围。
_RATE_BASE_WPM = 150
_RATE_STEP_WPM = 15
_RATE_MIN = -10
_RATE_MAX = 10


# PowerShell 脚本：内容保持纯 ASCII，文本从文件按 UTF-8 读入。
# 第一行必须是 param 块：PowerShell 要求参数声明位于脚本最前。
_PS_SCRIPT = (
    "param([string]$TextFile, [string]$OutFile, [string]$Voice, [int]$Rate)\n"
    "$ErrorActionPreference = 'Stop'\n"
    "Add-Type -AssemblyName System.Speech\n"
    "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
    "if ($Voice) { try { $synth.SelectVoice($Voice) } catch { [Console]::Error.WriteLine('VOICE_NOT_FOUND:' + $Voice) } }\n"
    "try { $synth.Rate = $Rate } catch { }\n"
    "$text = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)\n"
    "$synth.SetOutputToWaveFile($OutFile)\n"
    "$synth.Speak($text)\n"
    "$synth.Dispose()\n"
)


def wpm_to_sapi_rate(wpm):
    """把配置里的语速（WPM）换算成 SAPI 的 -10~10 档位。

    @param wpm 每分钟词数；非数字或缺失时按默认 150 处理
    @returns 夹紧在 -10~10 之间的整数档位
    """
    try:
        value = int(wpm)
    except Exception:
        value = _RATE_BASE_WPM
    # 与基准语速的差值换算成档位，四舍五入后夹紧
    steps = int(round((value - _RATE_BASE_WPM) / float(_RATE_STEP_WPM)))
    return max(_RATE_MIN, min(_RATE_MAX, steps))


def parse_missing_voice(stderr_text):
    """从子进程 stderr 中解析出「音色不存在」的那个音色名。

    背景：PowerShell 侧 SelectVoice 失败时会回落到系统默认音色并继续合成。
    结果可用，但若不记录就会造成「用户以为切换了音色、实际没生效」的误解。
    脚本因此在失败时向 stderr 打印一行 VOICE_NOT_FOUND:<音色名>。

    @param stderr_text 子进程 stderr 文本
    @returns 缺失的音色名；无此标记时返回空串
    """
    marker = "VOICE_NOT_FOUND:"
    text = str(stderr_text or "")
    if marker not in text:
        return ""
    # 取标记之后到行尾的内容即音色名；音色名可能含空格，故只按行切分
    tail = text.split(marker, 1)[1]
    return tail.splitlines()[0].strip() if tail.splitlines() else ""


def _safe_remove(path):
    """删除文件，忽略不存在或占用等异常。

    @param path 待删除的文件路径
    """
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _powershell_exe():
    """定位 powershell 可执行文件。

    @returns 可执行文件路径；找不到时退回命令名，由系统解析
    """
    return shutil.which("powershell") or "powershell"


def _write_script(path):
    """把 PowerShell 脚本写入临时文件。

    脚本内容为纯 ASCII，用 ASCII 编码写出即可被 PowerShell 正确解析。

    @param path 脚本文件路径
    @returns 失败时返回错误描述；成功返回 None
    """
    try:
        with open(path, "w", encoding="ascii") as fh:
            fh.write(_PS_SCRIPT)
    except OSError as e:
        return "写入 SAPI 脚本失败：%s" % e
    return None


def _run_powershell(script, text_path, wav_path, voice, rate, timeout):
    """拉起 powershell 执行一次合成，并处理超时与失败。

    超时由 subprocess.run 杀掉整个子进程；SAPI 在子进程内，
    资源随进程回收，主进程不会留下卡死的僵尸线程。

    @param script    脚本文件路径
    @param text_path 文本文件路径
    @param wav_path  输出 WAV 路径
    @param voice     音色名（可为空，为空时用系统默认）
    @param rate      SAPI 档位（-10~10）
    @param timeout   超时秒数
    @returns (ok, error)
    """
    args = [
        _powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", script,
        "-TextFile", text_path,
        "-OutFile", wav_path,
        "-Voice", voice or "",
        "-Rate", str(rate),
    ]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "SAPI 合成超时（%d 秒）" % timeout
    except Exception as e:
        return False, "SAPI 合成异常：%s" % e
    detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
    # 非零退出：把 stderr 前 200 字符带回，便于定位具体原因
    if proc.returncode != 0:
        return False, "SAPI 退出码 %d：%s" % (proc.returncode, detail[:200])
    # 音色名不存在时脚本会回落到系统默认音色并完成合成。
    # 结果可用，但必须留下痕迹：否则用户以为切换了音色，实际并未生效。
    missing = parse_missing_voice(detail)
    if missing:
        log("音色不存在，已回落到系统默认音色：%s" % missing)
    return True, ""


def synthesize(text, out_path, cfg, timeout=20):
    """把文本合成为 MP3（本引擎对外入口）。

    流程：文本落临时文件 → 生成 PowerShell 脚本 → 子进程合成 WAV →
    编码为 MP3 → 清理临时文件。

    @param text     待合成文本
    @param out_path 输出 MP3 路径
    @param cfg      语音配置字典
    @param timeout  合成超时秒数
    @returns (ok, error)；成功时 error 为空串
    """
    text = (text or "").strip()
    if not text:
        return False, "待合成文本为空"
    voice = (cfg.get("sapi_voice") or "").strip()
    rate = wpm_to_sapi_rate(cfg.get("pyttsx3_rate"))
    text_path = out_path + ".tmp.txt"
    wav_path = out_path + ".tmp.wav"
    script = out_path + ".tmp.ps1"
    try:
        # 文本走 UTF-8 文件：命令行转义易出错，且中文编码需显式声明
        write_err = write_synth_text(text_path, text)
        if write_err:
            return False, write_err
        script_err = _write_script(script)
        if script_err:
            return False, script_err
        ok, err = _run_powershell(script, text_path, wav_path, voice, rate, timeout)
        if not ok:
            return False, err
        # 子进程正常退出但没产出文件，同样算失败
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            return False, "SAPI 未产出有效音频"
        return voice_mp3.ensure_mp3(wav_path, out_path)
    finally:
        # 无论成败都清掉三类临时文件，不留垃圾
        _safe_remove(text_path)
        _safe_remove(wav_path)
        _safe_remove(script)
