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


def main(argv):
    """按参数合成一段语音，成功时在输出路径写出 WAV。

    @param argv 命令行参数列表（不含脚本名）
    @returns 进程退出码
    """
    if len(argv) < 4:
        sys.stderr.write("用法: pyttsx3_worker.py <文本文件> <输出WAV> <音色名> <语速>\n")
        return 1
    text_path, out_path, voice, rate = argv[0], argv[1], argv[2], argv[3]

    try:
        with open(text_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write("读取文本失败：%s\n" % e)
        return 1
    if not text.strip():
        sys.stderr.write("文本为空\n")
        return 1

    try:
        import pyttsx3
    except Exception as e:
        sys.stderr.write("未安装 pyttsx3：%s\n" % e)
        return 2

    try:
        import pythoncom
        pythoncom.CoInitialize()            # 本进程内独立初始化 COM
    except Exception:
        pass                                # 非 Windows 或已初始化

    engine = None
    try:
        engine = pyttsx3.init(driverName="sapi5")
        # 音色匹配：同时比对 name 与 id，兼容不同系统的命名差异
        target = (voice or "").strip().lower()
        if target:
            for v in engine.getProperty("voices"):
                name = (getattr(v, "name", "") or "").lower()
                vid = (getattr(v, "id", "") or "").lower()
                if target in name or target in vid:
                    engine.setProperty("voice", v.id)
                    break
        # 语速：收敛到 SAPI 的合理区间，过低会明显拖慢合成
        try:
            r = int(rate)
        except Exception:
            r = 150
        engine.setProperty("rate", max(80, min(r, 300)))

        if os.path.exists(out_path):
            os.remove(out_path)
        engine.save_to_file(text, out_path)
        engine.runAndWait()                 # 本进程内阻塞到底，由父进程负责超时

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            sys.stderr.write("未产出有效音频\n")
            return 1
        return 0
    except Exception as e:
        sys.stderr.write("合成异常：%s\n" % e)
        return 1
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
