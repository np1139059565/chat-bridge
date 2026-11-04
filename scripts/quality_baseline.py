"""工程质量检查 —— 存量基线

为什么需要基线：质量检查脚本对「存量欠账」与「新增欠账」一视同仁，
只要存量还在，闸门永远红。红着的闸门没有信息量——看不出这一轮有没有
把新增问题挡在门外，也看不出存量是否真的在减少。

本模块把当前存量登记为已知项：命中基线的违规照常打印（标记为已知），
但不计入失败；超出基线的部分才算新增，由调用方据此返回失败。

基线粒度：按「检查项 + 文件」记录违规条数。

为什么不用「检查项 + 文件 + 函数名 + 行号」：行号一动就失效，函数改名
也失效，基线会频繁误报；而按条数记录对代码搬动不敏感，维护成本低。
代价是同一文件内「新增一条、修掉一条」会互相抵消。对存量债务治理而言，
这个粒度够用，且不会因为误报逼人反复改基线文件。

基线文件改动约定：只允许两种改动——还清债务后把数字调小或删除条目，
以及首次登记存量。调大数字意味着接受新增欠账，须在提交信息里说明原因。
"""
import collections
import json
import os

# 基线文件相对工程根的位置
BASELINE_REL = os.path.join("scripts", "quality_baseline.json")


def baseline_path(root):
    """返回基线文件的绝对路径。

    @param root 工程根目录
    @returns 基线文件路径
    """
    return os.path.join(root, BASELINE_REL)


def load(root):
    """读取基线；文件不存在或损坏时按空基线处理。

    读不到基线不能当成「全部是新增」——那会让第一次运行就把闸门刷红。
    按空基线处理，等价于「尚未登记存量」，此时全部条目都算新增，
    由调用方决定是否要生成基线。

    @param root 工程根目录
    @returns {(检查项, 文件): 已知条数} 字典
    """
    path = baseline_path(root)
    # 基线文件缺失：视为尚未登记
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        # 解析失败同样按空基线处理，避免因基线损坏卡死提交
        return {}
    out = {}
    # 条目形如 {"check": ..., "file": ..., "count": N}
    for item in data.get("entries", []):
        check = item.get("check")
        rel = item.get("file")
        count = item.get("count")
        # 缺字段或条数非正数的条目直接跳过
        if not check or not rel or not isinstance(count, int) or count <= 0:
            continue
        out[(check, rel)] = count
    return out


def save(root, baseline, note=""):
    """把基线写回文件（按检查项、文件排序，便于 diff 阅读）。

    @param root     工程根目录
    @param baseline {(检查项, 文件): 条数} 字典
    @param note     写入文件头的说明
    """
    path = baseline_path(root)
    entries = []
    # 排序后输出：同一检查项聚在一起，文件名字典序，便于人工核对与 diff
    for (check, rel) in sorted(baseline):
        count = baseline[(check, rel)]
        # 非正数的条目不写入
        if count > 0:
            entries.append({"check": check, "file": rel, "count": count})
    data = {
        "note": note or "存量欠账基线：命中条目的违规不计入失败，超出部分算新增。",
        "entries": entries,
    }
    # 目录不存在时先建（首次生成基线可能遇到）
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build(root, results):
    """从一次全量扫描结果生成基线。

    @param root    工程根目录
    @param results {检查项: 违规列表} 字典
    @returns {(检查项, 文件): 条数} 字典
    """
    counts = collections.Counter()
    # 逐项统计每个文件有多少条违规
    for check, items in results.items():
        for it in items:
            rel = _file_of(check, it)
            # 取不到文件名的不登记（极少数结构异常的返回）
            if rel:
                counts[(check, rel)] += 1
    return dict(counts)


def _file_of(check, item):
    """从一条违规记录里取出所属文件（相对路径）。

    九项检查的返回结构不统一，此处按检查项分派。

    @param check 检查项名
    @param item  一条违规记录
    @returns 相对路径；取不到返回空串
    """
    # 循环导入返回的是 (模块A, 模块B) 两个模块名，不含文件名
    if check == "cycle":
        return "<import-cycle>"
    # 其余检查的首元素都是相对路径
    if isinstance(item, (tuple, list)) and item:
        return str(item[0])
    return ""


def split(check, items, baseline):
    """把一次检查的违规分成「已知」与「新增」两部分。

    已知条数以基线登记的数字为上限：某文件基线登记 3 条、实际仍是 3 条，
    则这 3 条全部算已知；实际 5 条则 3 条已知、2 条新增。

    @param check    检查项名
    @param items    本次扫描得到的违规列表
    @param baseline 基线字典
    @returns (已知列表, 新增列表)
    """
    # 先按文件分组，保留原有顺序
    grouped = collections.defaultdict(list)
    for it in items:
        grouped[_file_of(check, it)].append(it)
    known, fresh = [], []
    for rel, group in grouped.items():
        allowed = baseline.get((check, rel), 0)
        # 前 allowed 条算已知，其余算新增
        known.extend(group[:allowed])
        fresh.extend(group[allowed:])
    return known, fresh
