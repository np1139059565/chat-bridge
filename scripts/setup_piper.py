"""Piper 语音引擎安装脚本

作用：把本地离线语音引擎 Piper 及其中文模型下载到 models/tts/piper/。

为什么需要本脚本：
    models/ 目录体积大、可重新下载，已被 .gitignore 排除，不进版本库。
    新环境克隆后该目录为空，语音功能会按配置回落到其它引擎；
    想用本地引擎时跑一次本脚本即可补齐，无需手工找下载地址。

用法（在仓库根目录）：
    python scripts/setup_piper.py            # 缺什么补什么，已存在的跳过
    python scripts/setup_piper.py --force    # 全部重新下载
    python scripts/setup_piper.py --mirror   # 强制走国内镜像（默认已镜像优先）

下载源：
    Piper 程序  GitHub Releases
    模型文件    HuggingFace（国内常连不上，默认先试 hf-mirror.com）

退出码：0 = 全部就绪；1 = 有文件下载失败。
"""
import os
import shutil
import socket
import sys
import time
import urllib.request
import zipfile

# 仓库根：本脚本位于 scripts/ 下，向上两级
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 安装目标目录：与 flask_server/paths.py 的 PIPER_DIR 保持一致
PIPER_DIR = os.path.join(ROOT, "models", "tts", "piper")

# Piper 程序包（Windows 64 位）
PIPER_ZIP_URL = (
    "https://github.com/rhasspy/piper/releases/download/"
    "2023.11.14-2/piper_windows_amd64.zip"
)

# 中文模型：主文件与配置文件必须成对存在，缺一不可
MODEL_NAME = "zh_CN-huayan-medium"
MODEL_FILES = (MODEL_NAME + ".onnx", MODEL_NAME + ".onnx.json")

# 模型下载源：镜像优先，官方作为备选
MODEL_BASES = (
    "https://hf-mirror.com/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/",
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/",
)

# 网络超时（秒）：模型约 60MB，留足余量
TIMEOUT = 180


# ==================== 一、通用下载 ====================

def _write_stream(resp, dst, label):
    """把 HTTP 响应流分块写入文件，带百分比进度。

    @param resp  已打开的 HTTP 响应对象
    @param dst   目标路径
    @param label 日志用的名称
    @returns 写入的字节数
    """
    total = int(resp.headers.get("Content-Length") or 0)
    got = 0
    with open(dst, "wb") as fh:
        for chunk in iter(lambda: resp.read(65536), b""):
            fh.write(chunk)                       # 分块写入，避免大文件占满内存
            got += len(chunk)
            if total:
                pct = got * 100 // total
                print("\r  %s %d%% (%d/%d)" % (label, pct, got, total), end="")
    print()
    return got


def _download(url, dst, label):
    """下载单个文件到 dst，带进度提示。

    @param url   下载地址
    @param dst   目标路径
    @param label 日志用的名称
    @returns 是否成功
    """
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            _write_stream(resp, dst, label)
        size = os.path.getsize(dst)
        print("  完成 %s  %.1f MB  %.1f 秒" % (label, size / 1048576.0, time.time() - t0))
        return size > 0
    except Exception as e:
        print("\n  失败 %s  %s: %s" % (label, type(e).__name__, str(e)[:120]))
        # 失败时清掉半成品，避免下次误判为已完成
        try:
            os.remove(dst)
        except OSError:
            pass
        return False


# ==================== 二、安装 Piper 程序 ====================

def _flatten(inner_dir):
    """把解压产生的一层多余目录压平。

    官方 zip 顶层是 piper/，解压后会多一层；这里把内容上移一层再删空目录，
    使 piper.exe 直接位于 PIPER_DIR 下，与 paths.PIPER_DIR 的约定一致。
    @param inner_dir 多出来的那层目录
    """
    for name in os.listdir(inner_dir):
        src = os.path.join(inner_dir, name)
        dst = os.path.join(PIPER_DIR, name)
        if os.path.exists(dst):
            continue                              # 同名已存在，保留现有
        shutil.move(src, dst)
    os.rmdir(inner_dir)                           # 移空后可删


def install_piper(force=False):
    """安装 Piper 程序本体。

    @param force 为真时即使已存在也重新下载
    @returns 是否就绪
    """
    exe = os.path.join(PIPER_DIR, "piper.exe")
    if os.path.exists(exe) and not force:
        print("[跳过] Piper 程序已存在：%s" % exe)
        return True
    print("[安装] Piper 程序")
    os.makedirs(PIPER_DIR, exist_ok=True)
    zip_path = os.path.join(PIPER_DIR, "_piper.zip")
    if not _download(PIPER_ZIP_URL, zip_path, "piper_windows_amd64.zip"):
        return False
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(PIPER_DIR)
        # 顶层若只有一个同名目录，说明多了一层，压平它
        inner = os.path.join(PIPER_DIR, "piper")
        if os.path.isdir(inner) and not os.path.exists(os.path.join(PIPER_DIR, "piper.exe")):
            _flatten(inner)
        return os.path.exists(exe)
    except Exception as e:
        print("  解压失败：%s" % e)
        return False
    finally:
        try:
            os.remove(zip_path)                   # 临时压缩包用完即删
        except OSError:
            pass


# ==================== 三、安装中文模型 ====================

def install_model(force=False):
    """安装中文语音模型（主文件 + 配置）。

    @param force 为真时即使已存在也重新下载
    @returns 是否就绪
    """
    os.makedirs(PIPER_DIR, exist_ok=True)
    all_ok = True
    for fname in MODEL_FILES:
        dst = os.path.join(PIPER_DIR, fname)
        if os.path.exists(dst) and os.path.getsize(dst) > 0 and not force:
            print("[跳过] 模型已存在：%s" % fname)
            continue
        print("[安装] 模型 %s" % fname)
        ok = False
        for base in MODEL_BASES:
            # 优先镜像；主文件直接用 resolve 路径即可
            if _download(base + fname, dst, fname):
                ok = True
                break
            print("  换下一个下载源")
        if not ok:
            print("  [失败] %s 所有下载源均不可用" % fname)
            all_ok = False
    return all_ok


# ==================== 四、入口 ====================

def main(argv):
    """入口：安装程序与模型，打印最终状态。

    @param argv 命令行参数列表
    @returns 进程退出码
    """
    force = "--force" in argv
    socket.setdefaulttimeout(TIMEOUT)
    print("安装目录：%s" % PIPER_DIR)
    print("=" * 60)

    ok_exe = install_piper(force)
    ok_model = install_model(force)

    print("=" * 60)
    print("Piper 程序：%s" % ("就绪" if ok_exe else "缺失"))
    print("中文模型：%s" % ("就绪" if ok_model else "缺失"))
    if ok_exe and ok_model:
        print("\n安装完成。语音配置 voice_engine 设为 piper 或 auto 即可使用本地引擎。")
        return 0
    print("\n部分文件未就绪。语音功能会自动回落到其它引擎，不影响服务启动。")
    print("可稍后重跑本脚本补齐。")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
