"""自定义工具子系统的冒烟测试

用途：在不启动 Flask 服务的前提下，端到端验证 custom_tools 的核心链路：
    解析 tool.json → 安装 → 落盘 → 回读 → 上线 → 执行 → 缺参报错 → 扫描 → 删除

运行方式（在 flask_server/ 目录下）：
    python _smoke_ct.py
输出 SMOKE OK 表示全部断言通过；任一断言失败会抛异常并以非 0 退出码结束。

隔离策略：本脚本先建一个临时工作目录，并通过环境变量
CHAT_BRIDGE_CUSTOM_TOOLS_YAML 把 custom_tools 的落盘路径指向该目录下的
tools.yaml，随后才导入 custom_tools。因此测试全程只读写临时文件，
不会触碰 flask_server/config/custom_tools.yaml，结束后整个临时目录被删除。
"""
import os
import sys
import tempfile
import json
import shutil

# 把服务根目录（flask_server/）加入模块搜索路径：
# 本脚本位于 flask_server/scripts/ 下，直接运行时其上一级不在 sys.path 中，
# 需手动补上，才能 import custom_tools。
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

# 临时工作目录：存放测试用的 skill 与 custom_tools 落盘文件
root = tempfile.mkdtemp(prefix="skill_smoke_")
# 关键：在导入 custom_tools 之前重定向落盘路径，确保测试不触碰真实配置
os.environ["CHAT_BRIDGE_CUSTOM_TOOLS_YAML"] = os.path.join(root, "tools.yaml")

import custom_tools as ct

try:
    # 断言落盘路径确实落在临时目录内，避免误操作真实文件。
    # 两侧都做真实路径归一：tempfile.mkdtemp 可能返回 8.3 短路径（如 ADMINI~1），
    # 而 ct.CT_PATH 经 Path.resolve() 展开为长路径，直接字符串比较会误判不等。
    assert os.path.realpath(os.path.dirname(str(ct.CT_PATH))) == os.path.realpath(root), ct.CT_PATH

    # ---------- 1) 构造测试用 skill ----------
    sd = os.path.join(root, "demo_skill")
    os.makedirs(os.path.join(sd, "scripts"))
    # tool.json：声明一个名为 demo_echo 的工具，含必填与可选参数各一个
    with open(os.path.join(sd, "tool.json"), "w", encoding="utf-8") as f:
        json.dump({
            "tools": [{
                "name": "demo_echo",
                "description": "回声测试工具 # 含井号",
                "script": "scripts/echo.py",
                "interpreter": "python",
                "arg_style": "flag",
                "parameters": [
                    {"name": "msg", "type": "string", "required": True, "description": "回显内容"},
                    {"name": "repeat", "type": "boolean", "required": False, "description": "重复"}
                ]
            }]
        }, f, ensure_ascii=False)
    # 回声脚本：解析 --msg / --repeat，repeat 为真时把 msg 重复一次后以 JSON 输出
    with open(os.path.join(sd, "scripts", "echo.py"), "w", encoding="utf-8") as f:
        f.write(
            "import sys, json\n"
            "args = sys.argv[1:]\n"
            "out = {}\n"
            "i = 0\n"
            "while i < len(args):\n"
            "    if args[i] == '--msg':\n"
            "        out['msg'] = args[i+1]; i += 2\n"
            "    elif args[i] == '--repeat':\n"
            "        out['repeat'] = True; i += 1\n"
            "    else:\n"
            "        i += 1\n"
            "if out.get('repeat'):\n"
            "    out['msg'] = out.get('msg','') * 2\n"
            "print(json.dumps(out, ensure_ascii=False))\n"
        )

    # ---------- 2) 解析：校验 name 与参数被正确读出 ----------
    parsed = ct.parse_skill(sd)
    assert parsed[0]["name"] == "demo_echo", parsed
    assert parsed[0]["parameters"][0]["name"] == "msg"

    # ---------- 3) 安装：应只安装 demo_echo ----------
    installed = ct.install(sd)
    assert installed == ["demo_echo"], installed

    # ---------- 4) YAML 往返：写盘后重新读回，含井号的描述不被截断 ----------
    loaded = ct.load_tools()
    assert loaded["demo_echo"]["description"] == "回声测试工具 # 含井号", loaded["demo_echo"]["description"]
    # 新安装的工具默认未上线
    assert loaded["demo_echo"]["enabled"] is False

    # ---------- 5) 上线后执行：repeat=true 应把 msg 重复一次 ----------
    ct.update("demo_echo", {"enabled": True})
    assert ct.is_enabled("demo_echo") is True
    res = ct.run(loaded["demo_echo"], {"msg": "你好", "repeat": True})
    assert res == {"msg": "你好你好", "repeat": True}, res

    # ---------- 6) 缺必填参数应抛 ValueError（被分类为 parameter） ----------
    try:
        ct.run(loaded["demo_echo"], {})
        raise AssertionError("应因缺参抛错")
    except ValueError as e:
        pass

    # ---------- 7) 扫描：默认根目录无内容，但 scan_dir 对 demo 父目录应能发现 ----------
    scanned = ct.scan_dir(root)
    assert any(s["skill_name"] == "demo_skill" for s in scanned), scanned

    # ---------- 8) 删除：删除后不应再出现在工具表中 ----------
    assert ct.remove("demo_echo") is True
    assert "demo_echo" not in ct.load_tools()
    print("SMOKE OK")
finally:
    # 清理整个临时工作目录（含测试 skill 与临时落盘文件），不触碰真实配置
    shutil.rmtree(root, ignore_errors=True)
