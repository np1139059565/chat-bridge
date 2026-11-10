# 前端覆盖率存量欠账基线
#
# 为什么需要：不同 Node 版本对内置覆盖率报告的支持不同，同一份代码在
# 两地会出现「跳过」或「逐文件判不达标」两种结果。把当前已存在的欠账
# 登记成基线后，判定口径只取决于覆盖率是否退化或是否新增欠账。
#
# 判定规则：命中基线的欠账在覆盖率不低于登记值时免拦；覆盖率低于登记值
# （退化）或基线未登记的欠账（新增）仍拦下，门禁不因此放松。
#
# 本模块只做路径归一、基线读写与欠账分类，不执行测试、不打印结果。
import json
import os

# 基线文件位于 scripts/ 下，与结构质量基线并列，由分发方统一维护
BASELINE_REL = os.path.join('scripts', 'js_coverage_baseline.json')
# 覆盖率浮点比对容差，避免同一覆盖率在不同平台产生极小误差时误报退化
COVERAGE_EPS = 0.01


# 把覆盖率报告里的文件名归一为仓库相对路径。
# 报告可能带上级目录前缀、Windows 反斜杠或绝对路径，统一成正斜杠相对
# 路径，使基线在不同机器、不同 Node 版本下指向同一份源文件。
# 入参 name 是报告中的原始文件名，返回归一后的仓库相对路径。
def normalize_path(name):
    # 统一分隔符，去掉两端空白
    text = name.strip().replace('\\', '/')
    # 反复剥离上级目录前缀与当前目录前缀
    while text.startswith('../'):
        text = text[3:]
    while text.startswith('./'):
        text = text[2:]
    # 绝对路径取仓库内已知顶层目录之后的部分
    marker = None
    for top in ('extend/', 'flask_server/', 'shared/', 'scripts/'):
        pos = text.find(top)
        if pos >= 0 and (marker is None or pos < marker[0]):
            marker = (pos, top)
    if marker is not None:
        text = text[marker[0]:]
    return text


# 把未达标项整理为结构化记录，供比对与登记共用。
# 入参 rows 是 (原始文件名, 行覆盖率, 分支覆盖率) 列表，
# 返回 (归一路径, 类型, 实测值, 阈值) 列表。
def collect_failures(rows, min_line, min_branch):
    items = []
    for name, line_pct, branch_pct in rows:
        # 同一文件两种指标分别记录，退化判定才能精确到指标
        path = normalize_path(name)
        if line_pct < min_line:
            items.append((path, 'line', line_pct, min_line))
        if branch_pct < min_branch:
            items.append((path, 'branch', branch_pct, min_branch))
    return items


# 读取基线；文件缺失或格式异常时按空基线处理。
# 入参 root 是工程根目录，返回至少含 entries 列表的基线字典。
def load_baseline(root):
    path = os.path.join(root, BASELINE_REL)
    if not os.path.isfile(path):
        return {'entries': []}
    try:
        # 显式 utf-8，避免不同系统默认编码读坏中文说明
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {'entries': []}
    if not isinstance(data, dict) or not isinstance(data.get('entries'), list):
        return {'entries': []}
    return data


# 把当前欠账写为基线，按文件与指标排序便于人工核对。
# 入参 entries 是 (归一路径, 类型, 实测值, 阈值) 列表，返回登记条目数。
def save_baseline(root, entries, min_line, min_branch):
    # 只登记判定所需的三项，阈值集中放在 thresholds 里
    rows = [
        {'file': p, 'kind': k, 'pct': round(v, 2)}
        for p, k, v, _limit in sorted(entries)
    ]
    data = {
        'note': '前端覆盖率存量欠账基线：覆盖率不退化时免拦，退化与新增欠账仍拦。',
        'thresholds': {'line': min_line, 'branch': min_branch},
        'entries': rows,
    }
    path = os.path.join(root, BASELINE_REL)
    # 缩进两格、保留中文，便于直接阅读与评审
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    return len(rows)


# 把未达标项分为「退化」与「新增」两类，命中且未退化者为已知存量。
# 入参 items 是未达标项列表，baseline 是基线字典，
# 返回 (退化项列表, 新增项列表)。
def split(items, baseline):
    # 以「文件 + 指标」为键，登记值是当时的实测覆盖率
    known = {}
    for entry in baseline.get('entries', []):
        key = (entry.get('file'), entry.get('kind'))
        try:
            known[key] = float(entry.get('pct'))
        except (TypeError, ValueError):
            continue
    degraded, fresh = [], []
    for path, kind, pct, limit in items:
        key = (path, kind)
        if key not in known:
            # 基线未登记：新冒出来的欠账，照常拦下
            fresh.append((path, kind, pct, limit))
        elif pct < known[key] - COVERAGE_EPS:
            # 比登记时更低：覆盖率退化，照常拦下并带出登记值
            degraded.append((path, kind, pct, known[key], limit))
    return degraded, fresh
