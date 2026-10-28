"""微信通道（ClawBot / iLink）环境准备与自检

用途：
    在新机器上一条命令确认微信通道能否运行，并把缺的东西补上。

运行：
    python scripts/setup_weixin.py            # 检查并初始化
    python scripts/setup_weixin.py --check    # 只检查，不改动任何文件

检查项：
    1. Python 版本（需 3.10+，与服务端要求一致）
    2. 数据目录可创建可写（凭证与长轮询游标都落在这里）
    3. 微信接口可达（ilinkai.weixin.qq.com）
    4. 可选的 OpenClaw 路线组件（Node / npm / openclaw）

关于 OpenClaw：
    `npx -y @tencent-weixin/openclaw-weixin-cli@latest install` 安装的是
    OpenClaw 框架的微信插件，属于「另起一个 Node 网关」的路线。
    本工程的微信通道用 Python 直接实现协议，不需要 Node，也不需要 OpenClaw。
    脚本会检测它们是否存在：存在则一并说明可用，不存在不影响本通道运行。
"""
import argparse
import os
import socket
import sys
import urllib.request


# 微信接口基地址（与 weixin_client.DEFAULT_BASE 保持一致）。
ILINK_HOST = "ilinkai.weixin.qq.com"
# 服务端要求的最低 Python 版本。
MIN_PY = (3, 10)


# ---------- 输出辅助 ----------
def say(msg, tag="信息"):
    """打印一行带标签的提示。

    @param msg 正文
    @param tag 标签（信息 / 通过 / 警告 / 失败）
    """
    print("[%s] %s" % (tag, msg))


# ---------- 各项检查 ----------
def check_python():
    """检查 Python 版本是否满足要求。

    @returns 满足返回 True
    """
    cur = sys.version_info[:2]
    if cur >= MIN_PY:
        say("Python %d.%d，满足要求" % cur, "通过")
        return True
    say("Python %d.%d 过低，需要 %d.%d 或更高" % (cur + MIN_PY), "失败")
    return False


def ensure_data_dir(root, check_only=False):
    """确保微信数据目录存在且可写。

    凭证（含 bot_token）与长轮询游标都落在这个目录，
    目录不可写会导致扫码登录「成功但重启后失效」的怪象。
    @param root       工程根目录
    @param check_only 只检查不创建
    @returns 可用返回 True
    """
    target = os.path.join(root, "flask_server", "data", "weixin")
    if not check_only:
        try:
            os.makedirs(target, mode=0o700, exist_ok=True)
        except OSError as e:
            say("无法创建目录 %s：%s" % (target, e), "失败")
            return False
    if not os.path.isdir(target):
        # 只检查模式下目录不存在属正常：服务首次运行会自动创建。
        # 此处报「警告」而非「失败」，避免新机器首次自检就被判为环境不可用。
        if check_only:
            say("目录尚未创建：%s（首次启动服务时自动创建）" % target, "警告")
            return True
        say("目录不存在：%s" % target, "失败")
        return False
    probe = os.path.join(target, ".write_probe")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        say("数据目录可写：%s" % target, "通过")
        return True
    except OSError as e:
        say("数据目录不可写：%s" % e, "失败")
        return False


def check_network(timeout=8):
    """检查微信接口是否可达。

    只做 TCP 连通性探测：不发起真实请求，避免触发任何鉴权或限流。
    @param timeout 超时秒数
    @returns 可达返回 True
    """
    try:
        with socket.create_connection((ILINK_HOST, 443), timeout=timeout):
            pass
        say("接口可达：%s" % ILINK_HOST, "通过")
        return True
    except OSError as e:
        say("接口不可达：%s（检查网络或代理）" % e, "警告")
        return False


def _which(cmd):
    """在 PATH 里查找可执行文件。

    @param cmd 命令名
    @returns 找到返回完整路径，否则空串
    """
    from shutil import which
    return which(cmd) or ""


def check_openclaw():
    """检查可选的 OpenClaw 路线组件。

    这条路线与 Python 直连互斥：用了 OpenClaw 就不需要本工程的微信通道。
    此处只做存在性检测并说明，不安装任何东西——
    在用户机器上擅自安装一整套 Node 运行时不是本脚本该做的事。
    @returns 组件是否齐全
    """
    node = _which("node")
    npm = _which("npm")
    claw = _which("openclaw")
    if node and npm and claw:
        say("检测到 Node / npm / openclaw，OpenClaw 路线可用", "通过")
        say("如需该路线，执行：npx -y @tencent-weixin/openclaw-weixin-cli@latest install", "信息")
        return True
    missing = [n for n, p in (("node", node), ("npm", npm), ("openclaw", claw)) if not p]
    say("未检测到：%s（不影响本通道运行）" % "、".join(missing), "信息")
    return False


# ---------- 入口 ----------
def main():
    """按顺序执行各项检查并汇总结果。

    @returns 退出码：全部必需项通过为 0，否则 1
    """
    parser = argparse.ArgumentParser(description="微信通道环境准备与自检")
    parser.add_argument("--check", action="store_true", help="只检查，不创建目录")
    args = parser.parse_args()

    # 工程根目录：本脚本位于 <root>/scripts/ 下
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    say("工程根目录：%s" % root)

    # 必需项：任一失败即判定环境不可用
    required = [check_python(), ensure_data_dir(root, args.check)]
    # 网络是警告项：离线环境下用户仍可先完成配置，联网后再扫码
    check_network()
    # OpenClaw 是纯信息项：存在与否都不影响本通道
    check_openclaw()

    if all(required):
        say("环境就绪。启动服务后，在设置页「远程桥接（微信）」里点「扫码登录微信」即可。", "完成")
        return 0
    say("环境未就绪，请先解决上面标为「失败」的项。", "失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
