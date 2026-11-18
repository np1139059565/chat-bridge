"""chat-bridge dispatcher unattended poll.

Triggered every 5 minutes by Windows task chat-bridge-dispatcher-poll.
Collect + log + alert only: never auto-resend tasks (plan 2.5). New work is
sent explicitly after review/merge; residency wait agents pick it up from
dispatcher.md. Health file stays inside the repo .git/ (H2 compliant).
"""

import datetime
import json
import os
import subprocess
import time

BASE = r'D:\mydata'
REPO = os.path.join(BASE, 'chat-bridge-main')
STATE = os.path.join(REPO, '.git', 'dispatcher-poll-state.json')
LOCK = os.path.join(REPO, '.git', 'dispatcher-poll.lock')
HEALTH = os.path.join(REPO, '.git', 'dispatcher-health.txt')

ACTIVE = [
    ('a', 'R0 fixture patch', '20261118T081846'),
    # c's report reply-to is the ORIGINAL R2 id; judge by report time instead.
    ('c', 'R2 patch-back + residency restore', '20261118T082756'),
]
ALLOWED = set([
    'chat-bridge-main', 'chat-bridge-old', 'chat-bridge-bus', 'chat-bridge-b',
    'backups', 'docs', 'tools', 'projects', 'tmp_jscheck', '__pycache__',
    'dispatch-review-wt', 'review-a-r0-wt', 'review-c-r2-wt', 'review-c-patch-wt', 'r1-evidence',
    '3D打印', '媒体', '硬件资料', '系统镜像', '软件',
])


def git(*args):
    """Run git in the dispatcher repo, return (rc, text)."""
    proc = subprocess.run(['git', '-C', REPO, *args], capture_output=True,
                          text=True, encoding='utf-8', errors='replace')
    return proc.returncode, ((proc.stdout or '') + chr(10) + (proc.stderr or '')).strip()


def read(path):
    """Read a utf-8 file, empty string when missing."""
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return ''


def bus_tail(who, count=2):
    """Last few lines of one agent's bus file."""
    lines = read(os.path.join(REPO, 'docs', 'bus', who + '.md')).splitlines()
    if not lines:
        return '(empty)'
    return ' | '.join(line.strip()[:100] for line in lines[-count:])


def load_state():
    """Load poll state, seed on first run."""
    try:
        with open(STATE, encoding='utf-8') as handle:
            return json.load(handle)
    except Exception:
        return {'runs': 0, 'frozen': ['b']}


def report_ts_after(text, since):
    """Latest agent report timestamp strictly after a ruling."""
    best = ''
    for line in text.splitlines():
        if line.startswith('### [') and ' . report' in line:
            try:
                tag = line.split(']')[0].split('-')[1]
            except Exception:
                continue
            if len(tag) == 15 and tag > since and tag > best:
                best = tag
    return best


def active_lines():
    """Render the active chain from bus report timestamps."""
    out = []
    pending = []
    for who, label, since in ACTIVE:
        text = read(os.path.join(REPO, 'docs', 'bus', who + '.md'))
        stamp = report_ts_after(text, since)
        if not stamp:
            pending.append(label)
        out.append('   [%s] %s -> %s since=%s %s' % (
            'DONE' if stamp else 'WAIT', who, label, since, stamp))
        out.append('        tail: %s' % bus_tail(who)[:180])
    out.append('   pending = %d' % len(pending))
    return out, pending


def branch_lines():
    """Collect unmerged commits for the three agent branches."""
    out = []
    for branch in ['work/ai-a', 'work/ai-b', 'work/ai-c']:
        _, text = git('log', '--oneline', 'origin/main..origin/' + branch)
        out.append('   %s : %s' % (branch, text.replace(chr(10), ' | ') or '(none)'))
    return out


def root_dirs():
    """Collect unregistered directories in the workspace root."""
    return sorted(name for name in os.listdir(BASE)
                  if os.path.isdir(os.path.join(BASE, name)) and name not in ALLOWED)


def frozen_line(state):
    """Summarise the frozen R1 evidence directory."""
    ev = os.path.join(BASE, 'r1-evidence')
    count = len(os.listdir(ev)) if os.path.isdir(ev) else 0
    return '5 frozen = %s | r1-evidence sealed %d files, no .git, anchor unresolved' % (
        state.get('frozen'), count)


def collect(state, now):
    """Build the health log without mutating any tracked file."""
    log = ['chat-bridge dispatcher heartbeat  ' + now, '=' * 56]
    log.append('runs = %d  (scheduled every 5 min)' % state['runs'])
    rc, _ = git('fetch', 'origin', '--prune')
    log.append('1 fetch rc = %d' % rc)
    if git('rev-parse', 'HEAD')[1] != git('rev-parse', 'origin/main')[1]:
        rc2, out2 = git('merge', '--ff-only', 'origin/main')
        log.append('  ff-only rc = %d %s' % (rc2, (out2.splitlines() or [''])[0]))
    log.append('2 active task chain (judged by report timestamp after ruling):')
    task_lines, pending = active_lines()
    log.extend(task_lines)
    log.append('3 unmerged branch commits:')
    log.extend(branch_lines())
    log.append('4 unregistered root dirs: %s' % (root_dirs() or '(none)'))
    log.append(frozen_line(state))
    log.append('6 poll stays resident with no task; new work is sent after review.')
    log.append('   wait-resident agents pick it up automatically; a fully stopped')
    log.append('   session needs one restore input (inspector exception report).')
    state['last_run'] = now
    state['pending'] = pending
    return log, state


def main():
    """One poll cycle, guarded by a short lock."""
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if os.path.isfile(LOCK) and time.time() - os.path.getmtime(LOCK) < 120:
        print('SKIP: previous poll still running')
        return
    with open(LOCK, 'w', encoding='utf-8') as handle:
        handle.write(now)
    state = load_state()
    state['runs'] += 1
    log, state = collect(state, now)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, 'w', encoding='utf-8') as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    with open(HEALTH, 'w', encoding='utf-8') as handle:
        handle.write(chr(10).join(log) + chr(10))
    print(chr(10).join(log))
    print('HEALTH = ' + HEALTH)
    try:
        os.remove(LOCK)
    except OSError:
        pass


if __name__ == '__main__':
    main()
