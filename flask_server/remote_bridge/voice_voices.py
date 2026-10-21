"""远程桥接 —— 语音音色清单

职责：按引擎列举可选音色，供设置页下拉选择。

为何独立成模块：
- 三类引擎的音色来源完全不同（系统注册表 / 本地模型文件 / 在线固定名），
  与合成流程无关，拆开后可单独演进；
- 列举系统音色需要起子进程查 SAPI，这份代码不该混在合成主路径里。

依赖 voice_tts 的配置读取与超时常量，故由合成模块反向导入使用。
"""
import os

from .bridge_log import write as _blog
from .voice_tts import DEFAULT_VOICE, SYNTH_TIMEOUT, _engine_order, _load_voice_cfg


def log(*args):
    """统一前缀日志：与合成模块同一前缀，便于按来源检索。"""
    _blog("[bridge][tts]", *args)


# ==================== 七、音色清单（供设置页选择） ====================

def list_voices(engine=None):
    """列出某引擎可选的音色，供设置页下拉选择。

    三类引擎的音色来源完全不同：
      pyttsx3 —— 读 Windows SAPI 注册表里的系统语音，需起子进程列举
                 （主进程不加载 SAPI，避免又把那份单例资源占住）；
      piper   —— 本地模型文件即音色，列出 models/tts/piper 下的 .onnx；
      edge_tts—— 在线服务的固定音色名，取内置清单。
    auto 模式按 fallback 首个引擎列举，因为它才是实际生效的那个。

    @param engine 引擎名；None 时取当前配置
    @returns {"engine": 实际引擎名, "voices": [{"id","name"}...], "current": 当前配置的音色}
    """
    cfg = _load_voice_cfg()
    if not engine:
        order = _engine_order(cfg)
        engine = order[0] if order else "pyttsx3"
    engine = (engine or "").strip().lower()
    voices = []
    current = ""
    if engine == "pyttsx3":
        voices = _list_pyttsx3_voices()
        current = (cfg.get("pyttsx3_voice") or "").strip()
    elif engine == "piper":
        voices = _list_piper_voices()
        current = (cfg.get("piper_model") or "").strip()
    elif engine == "sapi":
        voices = _list_sapi_voices()
        current = (cfg.get("sapi_voice") or "").strip()
    elif engine == "edge_tts":
        voices = _list_edge_voices()
        current = DEFAULT_VOICE
    return {"engine": engine, "voices": voices, "current": current}


def _list_pyttsx3_voices():
    """列举系统语音音色：起短命子进程查询，不在主进程加载 SAPI。

    @returns [{"id","name"}]；失败时为空列表
    """
    import subprocess
    import sys
    code = (
        "import json,sys\n"
        "try:\n"
        "    import pythoncom,pyttsx3\n"
        "    pythoncom.CoInitialize()\n"
        "    e=pyttsx3.init(driverName='sapi5')\n"
        "    out=[{'id':str(v.id),'name':str(v.name)} for v in e.getProperty('voices')]\n"
        "    print(json.dumps(out,ensure_ascii=False))\n"
        "except Exception as ex:\n"
        "    print('[]')\n"
    )
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           timeout=SYNTH_TIMEOUT)
        import json
        data = json.loads((r.stdout or b"[]").decode("utf-8", "replace").strip() or "[]")
        return data if isinstance(data, list) else []
    except Exception as e:
        log("列举系统音色失败：", e)
        return []


def _list_piper_voices():
    """列举本地 Piper 模型文件：每个 .onnx 即一个音色。

    @returns [{"id","name"}]，id 为模型绝对路径
    """
    import paths
    out = []
    try:
        if paths.PIPER_DIR.is_dir():
            for f in sorted(paths.PIPER_DIR.glob("*.onnx")):
                out.append({"id": str(f), "name": f.stem})
    except Exception as e:
        log("列举 Piper 模型失败：", e)
    return out


def _list_sapi_voices():
    """列举系统语音音色：起短命 PowerShell 子进程查询，不在主进程加载 SAPI。

    与 pyttsx3 分支同一思路：SAPI 是进程级单例资源，放在主进程里会占死，
    故每次列举都开一个短命子进程，查完即退。

    @returns [{"id","name"}]；失败时为空列表
    """
    import json
    import shutil
    import subprocess
    # 脚本保持纯 ASCII：PowerShell 5.1 按本地 ANSI 解析脚本文件
    code = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$out = @()\n"
        "foreach ($v in $s.GetInstalledVoices()) {\n"
        "  $out += [pscustomobject]@{ id = $v.VoiceInfo.Name; name = $v.VoiceInfo.Name + ' | ' + $v.VoiceInfo.Culture }\n"
        "}\n"
        "$s.Dispose()\n"
        "ConvertTo-Json -InputObject $out -Compress\n"
    )
    exe = shutil.which("powershell")
    if not exe:
        log("列举系统音色失败：未找到 powershell")
        return []
    try:
        r = subprocess.run(
            [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code],
            capture_output=True, timeout=SYNTH_TIMEOUT)
        raw = (r.stdout or b"").decode("utf-8", "replace").strip()
        if not raw:
            return []
        data = json.loads(raw)
        # 只有一个音色时 ConvertTo-Json 返回对象而非数组，统一成列表
        if isinstance(data, dict):
            data = [data]
        return [{"id": str(d.get("id") or ""), "name": str(d.get("name") or "")}
                for d in data if isinstance(d, dict)]
    except Exception as e:
        log("列举系统音色失败：", e)
        return []


def _list_edge_voices():
    """列举 edge-tts 常用中文音色（在线服务，取内置清单）。

    @returns [{"id","name"}]，id 为 edge 音色名
    """
    return [
        {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓（女声，通用）"},
        {"id": "zh-CN-YunxiNeural", "name": "云希（男声，活泼）"},
        {"id": "zh-CN-YunjianNeural", "name": "云健（男声，沉稳）"},
        {"id": "zh-CN-XiaoyiNeural", "name": "晓伊（女声，甜）"},
        {"id": "zh-CN-YunyangNeural", "name": "云扬（男声，播音）"},
    ]
