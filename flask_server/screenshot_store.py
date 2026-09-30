"""截图存盘：统一入口。

此前存盘有两份独立实现：
    - routes/bridge.py 的 _save_data_url（QQ「/sp」指令用）
    - routes/tools.py 的 _save_screenshot_data_url（debug_chrome 的 get_page_snapshot 用）
两份逻辑相同、命名与格式却不同（PNG vs JPEG、有无毫秒），
同一目录下混着两种文件，难以分辨。此模块统一为一处实现，两处调用它。

存放目录：flask_server/screenshots/
文件名：shot_年月日_时分秒_毫秒.扩展名
"""
import base64
import os
import time


def _screenshots_dir():
    """返回截图目录的绝对路径（flask_server/screenshots/）。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "screenshots")


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
        name = "shot_" + time.strftime("%Y%m%d_%H%M%S") + "_" + str(int(time.time() * 1000) % 1000) + ext
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(raw)
        return {"name": name, "path": path}
    except Exception as e:
        print("[screenshot] 保存失败：", e)
        return None
