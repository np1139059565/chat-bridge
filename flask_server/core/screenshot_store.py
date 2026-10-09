"""截图存盘：统一入口。

此前存盘有两份独立实现：
    - routes/bridge.py 的 _save_data_url（QQ「/sp」指令用）
    - routes/tools.py 的 _save_screenshot_data_url（debug_chrome 的 get_page_snapshot 用）
两份逻辑相同、命名与格式却不同（PNG vs JPEG、有无毫秒），
同一目录下混着两种文件，难以分辨。此模块统一为一处实现，两处调用它。

存放目录：flask_server/data/screenshots/
文件名：shot_年月日_时分秒_毫秒.扩展名
"""
import base64
import os
import threading
import time

import paths
import app_log

# 进程内自增序号：仅靠「毫秒」做文件名后缀，同一毫秒内连续保存两次会撞名，
# 后一张覆盖前一张（实测两张图同名、磁盘只剩一个文件即此因）。
# 加锁保护自增，保证多线程下序号不重复。
_seq_lock = threading.Lock()
_seq = 0


def _next_seq():
    """取下一个进程内唯一序号（线程安全）。"""
    global _seq
    with _seq_lock:
        _seq += 1
        return _seq


def _screenshots_dir():
    """返回截图目录的绝对路径（flask_server/data/screenshots/）。"""
    return str(paths.SCREENSHOTS_DIR)


def save_data_url(data_url):
    """把图片 dataURL 保存到本地，返回 {name, path}；失败返回 None。

    dataURL 形如 data:image/png;base64,xxxx 或 data:image/jpeg;base64,xxxx。
    扩展名按 MIME 推断；文件名带毫秒，避免同秒内多次截图互相覆盖。
    @param data_url 图片 dataURL
    @returns {name, path} 或 None
    """
    try:
        if not data_url or "," not in data_url:
            return None
        head, b64 = data_url.split(",", 1)
        ext = ".jpg" if "image/jpeg" in head else ".png"
        raw = base64.b64decode(b64)
        out_dir = _screenshots_dir()
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        name = "shot_" + time.strftime("%Y%m%d_%H%M%S") + "_" + str(int(time.time() * 1000) % 1000) + "_" + str(_next_seq()) + ext
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(raw)
        return {"name": name, "path": path}
    except Exception as e:
        app_log.warn("[screenshot]", "保存失败：", e)
        return None


def save_web_image(data_url):
    """把指令结果的图片 dataURL 存到网页图片目录，返回 {name, path}；失败 None。

    与 QQ 截图分开存放：网页版的结果图片由网页经 /api/web/image-file/<name>
    直接读取展示，不与截图目录混在一起。
    @param data_url 图片 dataURL
    @returns {name, path} 或 None
    """
    _t0 = time.perf_counter()
    try:
        if not data_url or "," not in data_url:
            return None
        head, b64 = data_url.split(",", 1)
        ext = ".jpg" if "image/jpeg" in head else ".png"
        raw = base64.b64decode(b64)
        out_dir = str(paths.WEB_IMAGES_DIR)
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        name = "web_" + time.strftime("%Y%m%d_%H%M%S") + "_" + str(int(time.time() * 1000) % 1000) + "_" + str(_next_seq()) + ext
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(raw)
        # 落盘耗时埋点：本函数在网页发图的请求线程里同步执行（base64 解码 + 写盘），
        # 大图可能耗时明显，记录下来便于排查「界面请求被落盘拖慢」。
        _ms = (time.perf_counter() - _t0) * 1000.0
        if _ms >= 200:
            app_log.warn("[screenshot]", "网页图片保存耗时=%.0fms 大小=%.0fKB" % (_ms, len(raw) / 1024.0))
        return {"name": name, "path": path}
    except Exception as e:
        app_log.warn("[screenshot]", "网页图片保存失败：", e)
        return None
