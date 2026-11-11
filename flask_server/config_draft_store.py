"""按 siteKey 隔离的后端草稿 + 改完即时生效（不写母版 yaml）。

- 母版 definition.yaml / runtime.yaml：唯一一份、入库、可分发。
- 草稿 config/drafts/<siteKey>.json：每页面一份、本机、不入库。
- 界面改 -> 存该站草稿并立即 apply 到 runtime.CONFIG；【覆盖】才写母版并清该站草稿。
"""
import copy
import json
import re
import threading
from pathlib import Path

_DRAFT_DIR = Path(__file__).resolve().parent / "config" / "drafts"
_LOCK = threading.RLock()
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

def _path(site):
    key = _SAFE.sub("_", str(site or "unknown-site"))[:120] or "unknown-site"
    _DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    return _DRAFT_DIR / (key + ".json")

def load(site):
    try:
        p = _path(site)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None

def save(site, cfg):
    with _LOCK:
        _path(site).write_text(json.dumps(cfg or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    return True

def init_from_master(site, master):
    """草稿默认空：新 siteKey 首次访问，才用唯一母版拷出该站草稿。"""
    d = copy.deepcopy(master)
    save(site, d)
    return d

def clear(site):
    with _LOCK:
        try:
            _path(site).unlink(missing_ok=True)
        except Exception:
            pass

def _vals(spec, tool):
    out = {}
    cur = (spec or {}).get(tool) if isinstance(spec, dict) else None
    if isinstance(cur, list):
        for r in cur:
            if isinstance(r, dict) and "key" in r:
                out[r["key"]] = r.get("value")
    elif isinstance(cur, dict):
        out = dict(cur)
    return out

def apply_to_runtime(draft):
    """草稿即时作用到运行时内存（不调用 save_config_to_yaml），改完即生效。"""
    if not isinstance(draft, dict):
        return False
    try:
        import runtime
        cfg = runtime.CONFIG
        lim = draft.get("limits")
        if isinstance(lim, dict) and str(lim.get("max_json_chars", "")).isdigit():
            v = int(lim["max_json_chars"])
            if v > 0:
                cfg.setdefault("limits", {})["max_json_chars"] = v
        tools = draft.get("tools")
        if isinstance(tools, dict):
            for name, tv in tools.items():
                if isinstance(tv, dict) and name in getattr(runtime, "TOOLS", {}):
                    cfg.setdefault("tools", {}).setdefault(name, {})["enabled"] = bool(tv.get("enabled", True))
        tc = draft.get("tool_config")
        if isinstance(tc, dict):
            store = cfg.setdefault("tool_config", {})
            for tool in tc:
                vals = _vals(tc, tool)
                if vals:
                    store.setdefault(tool, {}).update(vals)
        if isinstance(draft.get("system_config"), list):
            cfg["system_config"] = draft["system_config"]
        prof = draft.get("profiles")
        if isinstance(prof, dict) and prof:
            try:
                from config_store import sanitize_profiles, derive_site_profiles
                merged = dict(cfg.get("profiles") or {})
                merged.update(sanitize_profiles(prof))
                cfg["profiles"] = merged
                cfg["site_profiles"] = derive_site_profiles(merged)
            except Exception:
                cfg.setdefault("profiles", {}).update(prof)
        if draft.get("default_profile"):
            cfg["default_profile"] = draft["default_profile"]
        # 兜底：受管区块对象（bridge / skills / rules 等）即时进运行时内存，不落盘
        skip = set(("flask", "limits", "tools", "tool_config", "system_config",
                    "profiles", "default_profile", "site_profiles", "available_tools",
                    "pending", "blockFields", "master", "site", "site_key", "success"))
        for k, v in draft.items():
            if k not in skip and isinstance(v, (dict, list)):
                cfg[k] = v
        try:
            import memory_switch
            memory_switch.invalidate()
        except Exception:
            pass
        return True
    except Exception:
        return False
