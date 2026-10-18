"""Anatomy 技能 —— 网页 AI 可调用的插图导出与构建工具

职责：
把 Anatomy 技能的等距插图产出到 Flask 服务的静态目录，并返回可直接在浏览器打开的网址。
支持两种产出方式：
  - export：直接复制 examples/ 下已经构建好的 HTML；
  - build ：先调用 Node 执行该示例的 build.mjs 重新生成，再复制到静态目录。

运行环境：
- export 只用 Python 标准库，无需 Node。
- build 需要 Node.js 20.10 以上，脚本会自动在系统标准安装目录与系统 PATH 中查找。
"""
import argparse        # 命令行参数解析
import glob            # 按通配符查找文件
import json            # 输出 JSON 结果
import os              # 文件名与路径操作
import shutil          # 文件复制
import subprocess      # 调用 Node 构建
import sys             # 解释器路径与平台判断
from pathlib import Path  # 面向对象的路径处理

# ---------- 路径推导 ----------
# 本文件位于 <工程根>/skills/anatomy/scripts/anatomy_tool.py，
# 向上四级即工程根，其余目录全部由它推导，避免写死绝对路径。
PROJECT_ROOT = Path(__file__).resolve().parents[3]        # 工程根目录
SKILL_DIR = PROJECT_ROOT / "skills" / "anatomy"           # 本技能目录
EXAMPLES_DIR = SKILL_DIR / "examples"                     # 示例插图目录
STATIC_DIR = PROJECT_ROOT / "flask_server" / "static"     # Flask 静态资源目录
EXPORT_DIR = STATIC_DIR / "anatomy"                       # 插图导出的子目录
# Node 的标准安装位置（系统级安装，与工程目录解耦）
NODE_STANDARD_DIR = Path(r"C:\Program Files\nodejs")

# 构建子进程的超时（秒）。
# 自定义工具单次执行上限为 60 秒，这里留出余量给后续复制与结果输出。
BUILD_TIMEOUT = 50


def list_examples():
    """列出全部示例目录，并标注是否带已构建好的 HTML 成品与构建脚本。"""
    rows = []                                             # 结果行集合
    for d in sorted(EXAMPLES_DIR.iterdir()):              # 按名称排序遍历示例目录
        if not d.is_dir():                                # 跳过非目录项
            continue                                      # 继续下一个
        htmls = sorted(glob.glob(str(d / "*.html")))      # 收集该示例下的 HTML 文件
        rows.append({                                     # 组装一行结果
            "name": d.name,                               # 示例名称
            "has_prebuilt_html": bool(htmls),             # 是否有预构建成品
            "has_build_script": (d / "build.mjs").is_file(),  # 是否可用 build 动作
            "files": [os.path.basename(h) for h in htmls],  # 成品文件名列表
        })
    return {                                              # 返回完整结果
        "examples": rows,                                 # 全部示例
        "node_available": bool(find_node()),              # 当前环境能否执行构建
    }


def find_node():
    """查找可用的 Node 可执行文件，返回其路径；找不到返回 None。

    查找顺序：系统标准安装目录 → 系统 PATH 中的 node。
    """
    exe = "node.exe" if os.name == "nt" else "node"       # 按平台确定可执行文件名
    std = NODE_STANDARD_DIR / exe                         # 系统标准安装位置
    if std.is_file():                                     # 标准位置存在时优先使用
        return str(std)
    return shutil.which("node")                           # 回退到系统 PATH


def _pick_html(src_dir, file_name=None):
    """在示例目录中挑选要导出的 HTML 文件，返回其路径。"""
    if file_name:                                         # 指定了具体文件
        src = src_dir / file_name                         # 直接使用该文件
        if not src.exists():                              # 源文件缺失则报错
            raise SystemExit("文件不存在：%s" % src)
        return src
    htmls = sorted(glob.glob(str(src_dir / "*.html")))    # 收集所有成品
    if not htmls:                                         # 没有成品说明未构建
        raise SystemExit("示例 %s 没有预构建的 HTML，请改用 build 动作" % src_dir.name)
    plain = [h for h in htmls if "-light" not in os.path.basename(h)]  # 优先标准主题
    return Path(plain[0] if plain else htmls[0])          # 选定文件


def _export(src, example_name):
    """把选定的 HTML 复制到静态目录，返回可访问的相对网址。"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)         # 确保导出目录存在
    out_name = "anatomy_" + src.name                      # 加前缀避免与其它静态资源重名
    out_path = EXPORT_DIR / out_name                      # 导出目标路径
    shutil.copyfile(str(src), str(out_path))              # 复制文件到静态目录
    return {
        "example": example_name,                          # 示例名称
        "file": out_name,                                 # 导出后的文件名
        "url_path": "/static/anatomy/" + out_name,        # 浏览器可访问的相对网址
        "size_bytes": out_path.stat().st_size,            # 文件大小，便于调用方判断
        "note": "在浏览器打开 http://127.0.0.1:5000 加上 url_path 即可查看",  # 使用提示
    }


def export_example(name, file_name=None):
    """把某个示例的 HTML 成品复制到静态目录，返回可访问的相对网址。"""
    src_dir = EXAMPLES_DIR / name                         # 目标示例目录
    if not src_dir.is_dir():                              # 目录不存在则报错退出
        raise SystemExit("示例不存在：%s" % name)
    return _export(_pick_html(src_dir, file_name), name)  # 挑选后导出


def build_example(name, file_name=None):
    """先用 Node 重新构建某个示例，再把产物复制到静态目录。

    构建脚本为示例目录下的 build.mjs，执行后会把 HTML 写到同目录。
    """
    src_dir = EXAMPLES_DIR / name                         # 目标示例目录
    if not src_dir.is_dir():                              # 目录不存在则报错退出
        raise SystemExit("示例不存在：%s" % name)
    script = src_dir / "build.mjs"                        # 构建脚本路径
    if not script.is_file():                              # 没有构建脚本则无法构建
        raise SystemExit("示例 %s 没有 build.mjs，只能使用 export 动作" % name)
    node = find_node()                                    # 定位 Node 可执行文件
    if not node:                                          # 找不到 Node 时给出明确指引
        raise SystemExit("未找到 Node.js，无法构建；请安装 Node 20.10 以上后重试")

    # 记录构建前的文件时间戳，用于确认产物确实被重写
    before = {p: p.stat().st_mtime for p in src_dir.glob("*.html")}
    env = dict(os.environ)                                # 复制环境变量，避免污染父进程
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")  # 让构建脚本能找到 node
    try:
        proc = subprocess.run([node, str(script)], cwd=str(src_dir), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="ignore", timeout=BUILD_TIMEOUT)
    except subprocess.TimeoutExpired:                     # 构建超时
        raise SystemExit("示例 %s 构建超过 %d 秒未完成，请直接使用 export 导出已预构建的成品"
                         % (name, BUILD_TIMEOUT))
    if proc.returncode != 0:                              # 构建失败时回传错误输出
        err = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise SystemExit("示例 %s 构建失败（退出码 %d）：%s" % (name, proc.returncode, err))

    # 校验产物确有更新，避免构建脚本空跑却报成功
    after = {p: p.stat().st_mtime for p in src_dir.glob("*.html")}
    changed = any(after.get(p) != before.get(p) for p in after)

    result = _export(_pick_html(src_dir, file_name), name)  # 导出构建产物
    result["built"] = True                                # 标记本次经过构建
    result["output_changed"] = changed                    # 产物是否确实被重写
    result["build_stdout"] = (proc.stdout or "").strip()[-400:]  # 附上构建日志尾部
    return result


def main():
    """解析命令行参数并执行对应动作，结果以 JSON 打印。"""
    ap = argparse.ArgumentParser(description="Anatomy 插图导出与构建工具")  # 创建参数解析器
    ap.add_argument("--action", required=True, choices=["list", "export", "build"],
                    help="list 列出示例；export 导出已有成品；build 先用 Node 构建再导出")  # 动作参数
    ap.add_argument("--example", default="", help="示例目录名，如 dial-indicator")  # 示例名
    ap.add_argument("--file", default="", help="指定具体 HTML 文件名，默认取标准主题")  # 文件名
    args = ap.parse_args()                                # 解析传入参数

    if args.action == "list":                             # 列出动作
        result = list_examples()                          # 收集示例清单
    else:                                                 # 导出或构建动作
        if not args.example:                              # 两者都必须给示例名
            raise SystemExit("%s 动作必须提供 --example" % args.action)
        fn = export_example if args.action == "export" else build_example  # 按动作选择函数
        result = fn(args.example, args.file or None)      # 执行并取得结果

    print(json.dumps(result, ensure_ascii=False))         # 以 JSON 输出，中文不转义


if __name__ == "__main__":                               # 作为脚本直接运行时
    main()                                                # 进入主流程
