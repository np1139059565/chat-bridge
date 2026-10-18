"""Anatomy 技能 —— 网页 AI 可调用的插图导出工具

职责：
把 Anatomy 技能 examples/ 下已构建好的等距插图 HTML，导出到 Flask 服务的静态目录，
并返回一个可直接在浏览器打开的网址，供网页 AI 在回答里引用。

为什么需要它：
Anatomy 本身是「给 AI 看的技能文档」，不含对外可执行接口；要让它被网页 AI 调用，
必须有一个能产出可访问资源的脚本，本文件就是这层适配。

运行环境约束：
本脚本只用 Python 标准库，不依赖 Node.js —— 因而只能导出 examples/ 中已经预构建好的
HTML 成品；需要现场构建新插图的场景，仍需本机安装 Node.js 20.10 以上。
"""
import argparse        # 命令行参数解析
import glob            # 按通配符查找文件
import json            # 输出 JSON 结果
import os              # 文件名与路径操作
import shutil          # 文件复制
from pathlib import Path  # 面向对象的路径处理

# ---------- 路径推导 ----------
# 本文件位于 <工程根>/skills/anatomy/scripts/anatomy_tool.py，
# 向上四级即工程根，其余目录全部由它推导，避免写死绝对路径。
PROJECT_ROOT = Path(__file__).resolve().parents[3]        # 工程根目录
SKILL_DIR = PROJECT_ROOT / "skills" / "anatomy"           # 本技能目录
EXAMPLES_DIR = SKILL_DIR / "examples"                     # 示例插图目录
STATIC_DIR = PROJECT_ROOT / "flask_server" / "static"     # Flask 静态资源目录
EXPORT_DIR = STATIC_DIR / "anatomy"                       # 插图导出的子目录


def list_examples():
    """列出全部示例目录，并标注是否带已构建好的 HTML 成品。"""
    rows = []                                             # 结果行集合
    for d in sorted(EXAMPLES_DIR.iterdir()):              # 按名称排序遍历示例目录
        if not d.is_dir():                                # 跳过非目录项
            continue                                      # 继续下一个
        htmls = sorted(glob.glob(str(d / "*.html")))      # 收集该示例下的 HTML 文件
        rows.append({                                     # 组装一行结果
            "name": d.name,                               # 示例名称
            "has_prebuilt_html": bool(htmls),             # 是否有预构建成品
            "files": [os.path.basename(h) for h in htmls],  # 成品文件名列表
        })
    return {                                              # 返回完整结果
        "examples": rows,                                 # 全部示例
        "note": "has_prebuilt_html 为 false 的示例需要本机安装 Node.js 才能构建",  # 提示
    }


def export_example(name, file_name=None):
    """把某个示例的 HTML 成品复制到静态目录，返回可访问的相对网址。"""
    src_dir = EXAMPLES_DIR / name                         # 目标示例目录
    if not src_dir.is_dir():                              # 目录不存在则报错退出
        raise SystemExit("示例不存在：%s" % name)          # 明确提示错误原因
    if file_name:                                         # 指定了具体文件
        candidates = [src_dir / file_name]                # 直接使用该文件
    else:                                                 # 未指定则自动挑选
        htmls = sorted(glob.glob(str(src_dir / "*.html")))  # 收集所有成品
        if not htmls:                                     # 没有成品说明未构建
            raise SystemExit("示例 %s 没有预构建的 HTML，需要本机 Node.js 构建" % name)
        plain = [h for h in htmls if "-light" not in os.path.basename(h)]  # 优先标准主题
        candidates = [Path(plain[0] if plain else htmls[0])]               # 选定文件

    src = candidates[0]                                   # 取第一个候选作为源文件
    if not src.exists():                                  # 源文件缺失则报错
        raise SystemExit("文件不存在：%s" % src)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)         # 确保导出目录存在
    out_name = "anatomy_" + src.name                      # 加前缀避免与其它静态资源重名
    out_path = EXPORT_DIR / out_name                      # 导出目标路径
    shutil.copyfile(str(src), str(out_path))              # 复制文件到静态目录

    return {                                              # 返回可供网页使用的信息
        "example": name,                                  # 示例名称
        "file": out_name,                                 # 导出后的文件名
        "url_path": "/static/anatomy/" + out_name,        # 浏览器可访问的相对网址
        "size_bytes": out_path.stat().st_size,            # 文件大小，便于调用方判断
        "note": "在浏览器打开 http://127.0.0.1:5000 加上 url_path 即可查看",  # 使用提示
    }


def main():
    """解析命令行参数并执行对应动作，结果以 JSON 打印。"""
    ap = argparse.ArgumentParser(description="Anatomy 插图导出工具")  # 创建参数解析器
    ap.add_argument("--action", required=True, choices=["list", "export"],
                    help="list 列出示例；export 导出某个示例")            # 动作参数
    ap.add_argument("--example", default="", help="示例目录名，如 dial-indicator")  # 示例名
    ap.add_argument("--file", default="", help="指定具体 HTML 文件名，默认取标准主题")  # 文件名
    args = ap.parse_args()                                # 解析传入参数

    if args.action == "list":                             # 列出动作
        result = list_examples()                          # 收集示例清单
    else:                                                 # 导出动作
        if not args.example:                              # 导出必须给示例名
            raise SystemExit("export 动作必须提供 --example")  # 报错退出
        result = export_example(args.example, args.file or None)  # 执行导出

    print(json.dumps(result, ensure_ascii=False))         # 以 JSON 输出，中文不转义


if __name__ == "__main__":                               # 作为脚本直接运行时
    main()                                                # 进入主流程
