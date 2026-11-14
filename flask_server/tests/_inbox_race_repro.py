"""A-8 diagnostic: deterministic reproduction of the two races that made
flask_server/tests/test_inbox_site_isolation.py flaky.

Not collected by pytest (leading underscore in module name).
Run standalone:  python flask_server/tests/_inbox_race_repro.py

RC1  read-during-async-write  ->  "read inbox failed, treat as empty"
     Root cause: web_inbox_store._write_state_now runs on a background
     daemon thread WITHOUT holding web_inbox._lock, and Path.write_text
     is not atomic (open 'w' truncates first, writes later). A read
     landing inside that window parses a truncated/empty file,
     read_state falls back to an EMPTY state and overwrites the
     in-memory cache with it.

RC2  cross-test path leak  ->  site-filter/count assertion flakiness
     Root cause: the background writer resolves paths.WEB_INBOX_PATH at
     WRITE time, while the test setUp/tearDown swaps that path without
     any synchronisation with the writer and never flushes pending
     state. A late write lands in the NEXT test's fresh temp dir.
"""
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: F401


def _fresh(tag):
    """Point the inbox paths at a brand-new temp dir (like setUp does)."""
    tmp = tempfile.mkdtemp(prefix="inbox_repro_%s_" % tag)
    web = os.path.join(tmp, "web")
    os.makedirs(web, exist_ok=True)
    paths.WEB_DIR = pathlib.Path(web)
    paths.WEB_INBOX_PATH = paths.WEB_DIR / "inbox.json"


def _reset_cache():
    """Drop the in-memory inbox cache (like setUp does)."""
    from web_bridge import web_inbox_store
    web_inbox_store._cache = None
    web_inbox_store._cache_sig = None


def _patch_slow_write(delay=0.4):
    """Replace Path.write_text with a truncate-pause-write variant.

    Mimics the non-atomic real write window: open('w') truncates first,
    the body arrives only after the delay. Returns the original method.
    """
    orig = pathlib.Path.write_text

    def tearing(self, data, **kw):
        with open(self, "w", encoding="utf-8") as f:
            time.sleep(delay)
            f.write(data)

    pathlib.Path.write_text = tearing
    return orig


def _wait_truncated(timeout=5.0):
    """Wait until the writer has truncated the inbox to 0 bytes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if paths.WEB_INBOX_PATH.stat().st_size == 0:
                return True
        except OSError:
            pass
        time.sleep(0.01)
    return False


def rc1_read_during_write():
    """RC1: read inside the async-write window (healthy=2, race=0)."""
    from web_bridge import web_inbox
    from web_bridge import web_inbox_store

    _fresh("rc1")
    _reset_cache()
    web_inbox.append("ai", "first", extra={"site_key": "glm"})
    assert web_inbox_store.flush_pending(5.0), "flush timeout before RC1"

    orig = _patch_slow_write()
    try:
        web_inbox.append("ai", "second", extra={"site_key": "glm"})
        assert _wait_truncated(), "writer never entered its write window"
        n = len(web_inbox.recent(10, "glm")["messages"])
        print("RC1 messages seen during async write window = %d (healthy=2, race=0)" % n)
        return n == 2
    finally:
        pathlib.Path.write_text = orig
        web_inbox_store.flush_pending(5.0)


def rc2_cross_case_leak():
    from web_bridge import web_inbox
    from web_bridge import web_inbox_store

    _fresh("rc2a")
    _reset_cache()
    orig_set = web_inbox_store._pending_event.set
    # hold the writer asleep: simulates the OS scheduler delaying it past
    # tearDown / next setUp, exactly like the real flaky runs
    web_inbox_store._pending_event.set = lambda: None
    try:
        web_inbox.append("ai", "case-A message", extra={"site_key": "glm"})
        # what the real test does next: swap to a fresh temp dir, never
        # syncing with the writer (no flush of _pending)
        _fresh("rc2b")
        _reset_cache()
    finally:
        web_inbox_store._pending_event.set = orig_set
    # writer finally wakes up -- and writes into the CURRENT path (case B)
    web_inbox_store._pending_event.set()
    assert web_inbox_store.flush_pending(5.0), "flush timeout after RC2"

    leaked = paths.WEB_INBOX_PATH.exists()
    texts = []
    if leaked:
        raw = json.loads(paths.WEB_INBOX_PATH.read_text(encoding="utf-8"))
        texts = [m["text"] for m in raw["messages"]]
    print("RC2 late write leaked into next case dir = %s texts=%s" % (leaked, texts))
    return not leaked


if __name__ == "__main__":
    ok1 = rc1_read_during_write()
    ok2 = rc2_cross_case_leak()
    print("RC1 healthy=%s  RC2 healthy=%s" % (ok1, ok2))
    print("expect both False on untreated code: this is the root-cause proof")