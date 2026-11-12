#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_bus.py - Git 文档总线 v1（四方共用，单 ref = origin/main）。

子命令：
  init --me X                       校验游标与四份总线文件是否齐全
  send --me X --to Y --kind K --text T [--reply-to ID]   发消息
  read --me X                       一次性打印所有未读消息并推进游标
  wait --me X [--round 60] [--tick 10]   单轮监听：立即探测一次，之后每 tick 秒
                                   fetch 比对；有更新立即打印返回（HIT），
                                   满一轮无更新打印 NO_UPDATE 退出，外层再起下一轮。

设计要点：
  - 四个身份各写 docs/bus/<me>.md，只追加、文件级零冲突；
  - send 用 git 底层对象（临时 index + commit-tree）构造只含自己文件的提交，
    不 checkout / 不 rebase / 不碰工作区，不会把执行方代码分支推到 main；
  - 并发 push 被拒时自动基于最新 main 重建提交重试（最多 3 次），不丢他人消息；
  - 统一 utf-8 + errors=replace，单进程串行、带超时；游标存 git 内部目录不入库。
"""
import argparse, json, os, subprocess, sys, tempfile, time, uuid
from datetime import datetime

NL = chr(10)
ACTORS = ("a", "b", "c", "dispatcher")
KINDS = ("question", "answer", "report", "task", "broadcast")
MAIN = "origin/main"
ENC = dict(encoding="utf-8", errors="replace", text=True)


def git(args, cwd, timeout=20, stdin_data=None, extra_env=None):
    """跑 git；stdin 与输出均走 bytes，避免 Windows text 模式把 LF 写成 CRLF。"""
    kw = dict(cwd=cwd, capture_output=True, timeout=timeout)
    if stdin_data is not None:
        kw["input"] = stdin_data.encode("utf-8") if isinstance(stdin_data, str) else stdin_data
    if extra_env:
        env = os.environ.copy()
        env.update(extra_env)
        kw["env"] = env
    p = subprocess.run(["git"] + list(args), **kw)
    out = (p.stdout or b"").decode("utf-8", "replace")
    err = (p.stderr or b"").decode("utf-8", "replace")
    return p.returncode, out + err


def fetch(cwd):
    return git(["fetch", "origin", "main"], cwd, timeout=25)


def bus_path(who):
    return "docs/bus/%s.md" % who


def show_remote(cwd, path):
    """读远端对象，只取 stdout 并把 CRLF 归一为 LF（stderr 警告不混入正文）。"""
    try:
        p = subprocess.run(["git", "show", MAIN + ":" + path], cwd=cwd,
                           capture_output=True, timeout=15, **ENC)
        if p.returncode != 0:
            return ""
        return (p.stdout or "").replace(chr(13)+chr(10), chr(10))
    except subprocess.TimeoutExpired:
        return ""


def parse_blocks(text):
    out, cur_id, cur = [], None, []
    for line in text.splitlines():
        if line.startswith("### [") and "]" in line:
            if cur_id is not None:
                out.append((cur_id, NL.join(cur).rstrip()))
            cur_id = line[5:line.index("]")].strip()
            cur = [line]
        elif cur_id is not None:
            cur.append(line)
    if cur_id is not None:
        out.append((cur_id, NL.join(cur).rstrip()))
    return out


def cursor_file(cwd, me):
    return os.path.join(cwd, ".git", "doc_bus_cursor_%s.json" % me)


def load_cursor(cwd, me):
    p = cursor_file(cwd, me)
    if not os.path.exists(p):
        return {"seen": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d.get("seen"), list) else {"seen": []}
    except Exception:
        return {"seen": []}


def save_cursor(cwd, me, d):
    p = cursor_file(cwd, me)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def collect_new(cwd, cur):
    fetch(cwd)
    seen = set(cur["seen"])
    changed, blocks = [], []
    for who in ACTORS:
        for mid, block in parse_blocks(show_remote(cwd, bus_path(who))):
            if mid not in seen:
                seen.add(mid)
                blocks.append((who, mid, block))
                changed.append(bus_path(who))
    cur["seen"] = sorted(seen)
    return sorted(set(changed)), blocks, cur


def render(changed, blocks):
    lines = ["UPDATE files=" + ",".join(changed) + " new=" + str(len(blocks))]
    for who, mid, block in blocks:
        lines.append("")
        lines.append(block)
    return NL.join(lines)


def do_init(cwd, me):
    fetch(cwd)
    missing = [bus_path(w) for w in ACTORS if not show_remote(cwd, bus_path(w))]
    print("actor=" + me)
    print("remote=" + MAIN)
    print("cursor=" + cursor_file(cwd, me))
    print("bus_files_missing=" + (",".join(missing) if missing else "none"))
    print("seen=" + str(len(load_cursor(cwd, me)["seen"])))
    print("INIT_OK")


def do_read(cwd, me):
    cur = load_cursor(cwd, me)
    changed, blocks, cur = collect_new(cwd, cur)
    save_cursor(cwd, me, cur)
    print(render(changed, blocks) if blocks else "NO_UNREAD")


def do_wait(cwd, me, round_s, tick_s):
    deadline = time.monotonic() + round_s
    n = 0
    while time.monotonic() < deadline:
        n += 1
        cur = load_cursor(cwd, me)
        changed, blocks, cur = collect_new(cwd, cur)
        if blocks:
            save_cursor(cwd, me, cur)
            print(render(changed, blocks))
            print("HIT probe=" + str(n))
            return 0
        rest = deadline - time.monotonic()
        if rest <= 0:
            break
        time.sleep(min(tick_s, rest))
    print("NO_UPDATE round=" + str(round_s) + "s tick=" + str(tick_s) + "s probes=" + str(n))
    return 0


def must(args, cwd, env, label, stdin_data=None):
    """跑一条 git 底层命令，失败即抛带标签的异常，成功返回去除首尾空白的输出。"""
    rc, o = git(args, cwd, stdin_data=stdin_data, extra_env=env)
    if rc:
        raise RuntimeError(label + ": " + o[:160])
    return o.strip()


def _new_index():
    """建一个空的临时索引文件，返回 (路径, 环境)。"""
    fd, idx = tempfile.mkstemp(prefix="doc_bus_index_")
    os.close(fd)
    os.remove(idx)
    return idx, {"GIT_INDEX_FILE": idx}


def _cleanup_index(idx):
    """清理临时索引文件，缺失时静默。"""
    try:
        os.remove(idx)
    except OSError:
        pass


def build_commit(cwd, path, new, me, to, mid):
    """用临时索引构造只含自己那份消息文件的提交，返回 commit 哈希。"""
    idx, env = _new_index()
    try:
        must(["read-tree", MAIN], cwd, env, "read-tree")
        blob = must(["hash-object", "-w", "--stdin"], cwd, env, "hash", new)
        if not blob:
            raise RuntimeError("hash-object: empty blob")
        must(["update-index", "--add", "--cacheinfo",
             "100644," + blob + "," + path], cwd, env, "update-index")
        tree = must(["write-tree"], cwd, env, "write-tree")
        return must(["commit-tree", tree, "-p", MAIN,
                    "-m", "bus(" + me + "): " + to + " [" + mid + "]"],
                   cwd, env, "commit-tree")
    finally:
        _cleanup_index(idx)


def _sync_local_main(cwd):
    """send 成功后：仅当当前检出 main 时，用标准 ff-only 快进同步本地。"""
    rc, head = git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    if rc or head.strip() != "main":
        return
    rc, _ = git(["fetch", "origin", "main"], cwd, timeout=25)
    if rc:
        print("SYNC_SKIPPED fetch failed")
        return
    rc, _ = git(["merge", "--ff-only", "FETCH_HEAD"], cwd, timeout=20)
    if rc:
        print("SYNC_SKIPPED local not clean; run git merge --ff-only origin/main manually")
    else:
        print("SYNCED main ff-only")


def do_send(cwd, me, to, kind, text, reply_to):
    if to not in ACTORS + ("all",):
        raise SystemExit("bad --to: " + to)
    if kind not in KINDS:
        raise SystemExit("bad --kind: " + kind)
    path = bus_path(me)
    mid = me + "-" + datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    head = "### [" + mid + "] " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + me + " -> " + to + " . " + kind
    if reply_to:
        head += " (reply-to: " + reply_to + ")"
    entry = head + NL + text.strip() + NL
    last = ""
    for attempt in range(3):
        fetch(cwd)
        old = show_remote(cwd, path)
        new = old.rstrip(NL) + NL + NL + entry if old.strip() else entry
        commit = build_commit(cwd, path, new, me, to, mid)
        rc, o = git(["push", "origin", commit + ":refs/heads/main"], cwd, timeout=30)
        if rc == 0:
            _sync_local_main(cwd)
            print("SENT id=" + mid + " file=" + path + " commit=" + commit[:8])
            return 0
        last = o.strip()[:160]
    raise SystemExit("send failed after 3 attempts: " + last)


def _actor_from_branch(branch):
    """按当前分支判身份；判不出返回 unknown。"""
    return {"main": "dispatcher", "work/ai-a": "a",
            "work/ai-b": "b", "work/ai-c": "c"}.get((branch or "").strip(), "unknown")


def _actor_from_env():
    """显式环境变量优先；返回 (actor, source)。"""
    v = os.environ.get("DOC_BUS_ACTOR", "").strip()
    return (v, "env:DOC_BUS_ACTOR") if v in ACTORS else ("unknown", "branch")


def _whoami_verdict(actor, expect):
    """expect 不符时返回非零退出码。"""
    if expect and expect in ACTORS and actor != expect:
        print("MISMATCH: 期望 " + expect + " 但判出 " + actor + "；先切到自己的 work/ai-* 分支或设置 DOC_BUS_ACTOR，别以错身份开工")
        return 2
    return 0


def _whoami_hints(actor):
    """按身份打印提示；unknown 时返回 True 表示需停下。"""
    if actor == "unknown":
        print("HINT: 判不出身份，停下来问分发方，别自作主张（见 docs/START_HERE.md 第 1 节）")
        return True
    if actor == "dispatcher":
        print("HINT: 若你是执行方 AI，说明还在默认 main 分支；按 START_HERE 第 1.1 节切到自己的 work/ai-* 再继续，不要以分发方身份动手")
    print("HINT: 后续 doc_bus 命令用 --me " + actor)
    return False


def do_whoami(cwd, branch, expect=""):
    """打印当前分支与身份；判错或判不出即停下。"""
    actor, src = _actor_from_env()
    if not branch:
        rc, o = git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
        branch = o.strip() if rc == 0 else "(detached)"
    if actor == "unknown":
        actor = _actor_from_branch(branch)
    print("branch=" + branch)
    print("source=" + src)
    print("actor=" + actor)
    rc = _whoami_verdict(actor, expect)
    if rc:
        return rc
    return 2 if _whoami_hints(actor) else 0


def main():
    ap = argparse.ArgumentParser(description="Git 文档总线 v1")
    ap.add_argument("cmd", nargs="?", default="wait", choices=["init", "send", "read", "wait", "whoami"])
    ap.add_argument("--me", default="")
    ap.add_argument("--to", default="all")
    ap.add_argument("--kind", default="report", choices=KINDS)
    ap.add_argument("--text", default="")
    ap.add_argument("--reply-to", dest="reply_to", default="")
    ap.add_argument("--round", dest="round_s", type=int, default=60)
    ap.add_argument("--tick", dest="tick_s", type=int, default=10)
    ap.add_argument("--branch", default="", help="whoami 用：覆盖当前分支（自测用）")
    ap.add_argument("--expect", default="", help="whoami 用：期望身份，不符则拒绝")
    a = ap.parse_args()
    if a.cmd != "whoami" and a.me not in ACTORS:
        ap.error("--me 必须是 a/b/c/dispatcher（whoami 不需要）")
    cwd = git(["rev-parse", "--show-toplevel"], os.getcwd())[1].strip()
    if a.cmd == "whoami":
        sys.exit(do_whoami(cwd, a.branch, a.expect))
    if a.cmd == "init":
        do_init(cwd, a.me)
    elif a.cmd == "read":
        do_read(cwd, a.me)
    elif a.cmd == "wait":
        sys.exit(do_wait(cwd, a.me, a.round_s, a.tick_s))
    else:
        sys.exit(do_send(cwd, a.me, a.to, a.kind, a.text, a.reply_to))


if __name__ == "__main__":
    main()
