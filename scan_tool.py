# 用返回行（含耗时）反推开始时刻，看相邻请求是否重叠
import re

path = r'D:/projects/chat-bridge-main/flask_server/data/logs/app-2026-11-06.log'
reqs = []
with open(path, encoding='utf-8', errors='ignore') as f:
    for line in f:
        m = re.match(r'(\d\d):(\d\d):(\d\d) WARN \[req\]\[\w+\] <- POST /tool 200 ([\d.]+)ms', line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            end = h*3600 + mi*60 + s
            dur = float(m.group(4)) / 1000.0
            reqs.append((end - dur, end, dur))

print('共 %d 次 /tool' % len(reqs))
for i in range(1, len(reqs)):
    prev_start, prev_end, prev_dur = reqs[i-1]
    cur_start, cur_end, cur_dur = reqs[i]
    # 本次开始时刻早于上一次结束 = 重叠 = 并发执行
    if cur_start < prev_end:
        print('重叠! 上次 %.1fs 结束于 %.1fs, 本次开始于 %.1fs' % (
            prev_dur, prev_end, cur_start))
        print('  -> 并发 %.1f 秒' % (prev_end - cur_start))
