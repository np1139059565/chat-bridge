"""pyttsx3 合成子进程（独立运行，不参与主进程生命周期）

为何必须独立成进程：
    Windows SAPI 是进程级单例资源。主进程里把 runAndWait 放进守护线程、
    超时后放弃等待，线程并不会结束——它继续卡在 SAPI 调用里，永久占住
    这份资源。每失败一次就多一个僵尸线程，最终所有合成都在闸门处超时，
    只能重启进程恢复。

    改为子进程后，超时直接杀掉整个进程，SAPI 随进程一起被系统回收，
    主进程不会残留任何状态，失败只影响这一次调用。

调用方式（由 voice_tts._synth_pyttsx3 拉起）：
    python pyttsx3_worker.py <文本文件> <输出WAV> <音色名> <语速>
文本走文件而非命令行：朗读文本可能很长、含引号换行，命令行转义易出错。

退出码：0 成功；1 参数或运行错误；2 未安装 pyttsx3。
"""
import os
import sys


def _read_text(text_path):
    """读取待朗读文本。

    文本走文件而非命令行：朗读内容可能很长、含引号换行，命令行转义易出错。

    @param text_path 文本文件路径
    @returns 文本内容；读取失败或内容为空时返回 None
    """
    try:
        with open(text_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write("读取文本失败：%s\n" % e)
        return None
    # 纯空白文本无法合成，视同读取失败
    if not text.strip():
        sys.stderr.write("文本为空\n")
        return None
    return text


def _init_com():
    """在本进程内独立初始化 COM。

    SAPI 依赖 COM，子进程每次都是全新进程，需要自行初始化；
    非 Windows 环境或已初始化时忽略异常。
    """
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass


def _apply_voice(engine, voice):
    """把音色设置应用到引擎。

    同时比对 name 与 id，兼容不同 Windows 版本的系统语音命名差异；
    未找到匹配项时保持引擎默认音色。

    @param engine pyttsx3 引擎实例
    @param voice  期望音色名（可为空，为空则不处理）
    """
    target = (voice or "").strip().lower()
    if not target:
        return
    for v in engine.getProperty("voices"):
        name = (getattr(v, "name", "") or "").lower()
        vid = (getattr(v, "id", "") or "").lower()
        if target in name or target in vid:
            engine.setProperty("voice", v.id)
            return


def _apply_rate(engine, rate):
    """把语速设置应用到引擎。

    语速收敛到 SAPI 的合理区间：过低会明显拖慢合成，过高则吐字不清。
    非数字输入回退到 150（SAPI 默认语速）。

    @param engine pyttsx3 引擎实例
    @param rate   期望语速（字符串或数字，可为空）
    """
    try:
        r = int(rate)
    except Exception:
        r = 150
    engine.setProperty("rate", max(80, min(r, 300)))


def _synthesize(engine, text, out_path):
    """执行合成并校验产物。

    合成在本进程内阻塞到底，超时由父进程负责（父进程超时即杀整个进程）。

    @param engine   pyttsx3 引擎实例
    @param text     待朗读文本
    @param out_path 输出 WAV 路径
    @returns 进程退出码（0 成功，1 产物无效）
    """
    # 清理旧产物，避免把上次的残留误判为本次成功
    if os.path.exists(out_path):
        os.remove(out_path)
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    # 产物缺失或为空即视为失败，不向父进程交出无效音频
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        sys.stderr.write("未产出有效音频\n")
        return 1
    return 0


def main(argv):
    """按参数合成一段语音，成功时在输出路径写出 WAV。

    @param argv 命令行参数列表（不含脚本名）
    @returns 进程退出码
    """
    if len(argv) < 4:
        sys.stderr.write("用法: pyttsx3_worker.py <文本文件> <输出WAV> <音色名> <语速>\n")
        return 1
    text_path, out_path, voice, rate = argv[0], argv[1], argv[2], argv[3]

    text = _read_text(text_path)
    if text is None:
        return 1

    try:
        import pyttsx3
    except Exception as e:
        sys.stderr.write("未安装 pyttsx3：%s\n" % e)
        return 2

    _init_com()
    return _run_engine(pyttsx3, text, out_path, voice, rate)


def _run_engine(pyttsx3, text, out_path, voice, rate):
    """初始化引擎、应用音色与语速、执行合成，并在结束时停止引擎。

    引擎的生命周期集中在这里：无论成功与否都停止引擎，
    停止失败不影响退出码（此时音频已产出或已判失败，清理异常无关紧要）。

    @param pyttsx3  已导入的 pyttsx3 模块
    @param text     待合成文本
    @param out_path 输出 WAV 路径
    @param voice    音色名（可为空）
    @param rate     语速
    @returns 进程退出码
    """
    engine = None
    try:
        engine = pyttsx3.init(driverName="sapi5")
        _apply_voice(engine, voice)
        _apply_rate(engine, rate)
        return _synthesize(engine, text, out_path)
    except Exception as e:
        sys.stderr.write("合成异常：%s\n" % e)
        return 1
    finally:
        _stop_engine(engine)


def _stop_engine(engine):
    """停止引擎；任何失败都静默忽略。

    @param engine 引擎实例（可为 None）
    """
    if engine is None:
        return
    try:
        engine.stop()
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
