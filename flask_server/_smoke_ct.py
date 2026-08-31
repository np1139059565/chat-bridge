import os, tempfile, json, shutil
import custom_tools as ct

root = tempfile.mkdtemp(prefix="skill_smoke_")
try:
    sd = os.path.join(root, "demo_skill")
    os.makedirs(os.path.join(sd, "scripts"))
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

    parsed = ct.parse_skill(sd)
    assert parsed[0]["name"] == "demo_echo", parsed
    assert parsed[0]["parameters"][0]["name"] == "msg"

    installed = ct.install(sd)
    assert installed == ["demo_echo"], installed

    # YAML 往返：写盘后重新读回
    loaded = ct.load_tools()
    assert loaded["demo_echo"]["description"] == "回声测试工具 # 含井号", loaded["demo_echo"]["description"]
    assert loaded["demo_echo"]["enabled"] is False

    # 上线后执行
    ct.update("demo_echo", {"enabled": True})
    assert ct.is_enabled("demo_echo") is True
    res = ct.run(loaded["demo_echo"], {"msg": "你好", "repeat": True})
    assert res == {"msg": "你好你好", "repeat": True}, res

    # 缺必填参数应抛 ValueError（被分类为 parameter）
    try:
        ct.run(loaded["demo_echo"], {})
        raise AssertionError("应因缺参抛错")
    except ValueError as e:
        pass

    # 扫描：默认根目录无内容，但 scan_dir 对 demo 父目录应能发现
    scanned = ct.scan_dir(root)
    assert any(s["skill_name"] == "demo_skill" for s in scanned), scanned

    # 删除
    assert ct.remove("demo_echo") is True
    assert "demo_echo" not in ct.load_tools()
    print("SMOKE OK")
finally:
    shutil.rmtree(root, ignore_errors=True)
    # 清理可能写出的 custom_tools.yaml
    try:
        os.remove(ct.CT_PATH)
    except OSError:
        pass
