"""e2e 测试夹具：启动真实 Flask 服务 + Playwright 加载扩展。

运行前需安装浏览器：
    python -m playwright install chromium
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
EXT_DIR = ROOT / "chrome extension"
FLASK_DIR = ROOT / "flask_server"
MOCK_PAGES = ROOT / "tests" / "fixtures" / "mock_pages"
CONFIG_PATH = FLASK_DIR / "config.yaml"

DEFAULT_E2E_PORT = 5000


def _port_in_use(port: int) -> bool:
    """Windows 上 connect_ex 对 TIME_WAIT 端口可能误判，
    改用绑定尝试来可靠检测端口是否真正被监听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return False  # 绑定成功 = 端口空闲
        except OSError:
            return True   # 绑定失败 = 端口被占用


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _patch_config_port(port: int):
    text = CONFIG_PATH.read_text(encoding="utf-8")
    original = text
    import re
    patched = re.sub(r"(port\s*:\s*)\d+", r"\g<1>%d" % port, text, count=1)
    CONFIG_PATH.write_text(patched, encoding="utf-8")
    return original


def _restore_config(original: str):
    CONFIG_PATH.write_text(original, encoding="utf-8")


@pytest.fixture(scope="session")
def flask_server():
    """启动真实 Flask 服务（独立进程），e2e 期间一直运行。

    强制使用 5000 端口：dialog 前端硬编码 flaskUrl=http://127.0.0.1:5000，
    若用随机端口前端将无法连通、工具执行失败。
    """
    port = int(os.environ.get("CB_TEST_PORT", "5000"))
    if _port_in_use(port):
        pytest.skip("端口 %d 已被占用，e2e 测试需要该端口" % port)

    original_config = _patch_config_port(port)

    env = dict(os.environ)
    env["CB_TEST_PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, str(FLASK_DIR / "server.py")],
        cwd=str(FLASK_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = "http://127.0.0.1:%s" % port

    deadline = time.time() + 10
    import urllib.request
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base_url + "/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.terminate()
        _restore_config(original_config)
        raise RuntimeError("Flask 测试服务启动超时")

    yield {"proc": proc, "base_url": base_url, "port": port}

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    _restore_config(original_config)


@pytest.fixture(scope="session")
def browser_context(flask_server):
    """使用 launch_persistent_context + 完整 Chromium 加载扩展。

    关键：必须显式指定 executable_path 指向完整 Chromium（非 headless shell），
    否则 Chrome 扩展在 headless shell 中不会被加载。
    """
    pw = sync_playwright().start()

    user_data_dir = tempfile.mkdtemp(prefix="cb-e2e-profile-")
    chromium_path = pw.chromium.executable_path
    context = pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,
        executable_path=chromium_path,
        args=[
            "--disable-extensions-except=%s" % str(EXT_DIR),
            "--load-extension=%s" % str(EXT_DIR),
        ],
        viewport={"width": 1280, "height": 800},
    )

    # 先打开空白页，给扩展上下文初始化留出时间
    warmup = context.new_page()
    warmup.goto("about:blank")
    warmup.wait_for_timeout(1500)
    warmup.close()

    yield pw, context
    context.close()
    pw.stop()


@pytest.fixture(scope="session")
def _extension_id(browser_context):
    """获取扩展 ID（访问 chrome://extensions 不可行，通过 service worker 推断）。"""
    _, context = browser_context
    # MV3 扩展加载后，service worker 会在后台自动启动
    # 通过等待扩展的 background service worker 就绪来确认扩展已加载
    yield None


def _load_mock_page_with_host(context, html_path: Path, host: str):
    """通过路由拦截，用真实域名加载 mock 页面，保证 content.js 的站点识别正确。

    同时在页面加载前启动 JS 覆盖率采集器，确保采集到 content.js 和 iframe 内
    dialog/app.js 的完整执行数据。
    """
    from js_coverage import CoverageCollector

    page = context.new_page()
    body = html_path.read_text(encoding="utf-8")

    # 页面加载前启动覆盖率采集（iframe 与顶层共享同一 CDP session）
    collector = CoverageCollector(page, context)
    collector.start()
    page._coverage_collector = collector

    def _handle(route):
        route.fulfill(status=200, content_type="text/html", body=body)

    page.route("http://%s/**" % host, _handle)
    page.route("https://%s/**" % host, _handle)
    page.goto("http://%s/chat/test-conversation" % host)

    # content.js 异步初始化：getConfig → storage 读取 → inject → startObserver
    # 等待 iframe 出现（最长 10 秒）
    page.wait_for_selector("#ai-mirror-iframe", timeout=10000)

    # 等待 Vue 应用挂载、discoverFlask 完成端口探测、首次提取完成
    # discoverFlask 会依次探测多个候选端口（5000/8080/8000/localhost:5000），
    # 未连接端口会快速失败（connection refused），实测约需 2~2.5 秒。
    # 等待不足会导致测试点击执行时 flaskUrl 尚未就绪、fetch 挂起。
    page.wait_for_timeout(2500)
    return page


@pytest.fixture
def mock_glm_page(browser_context):
    _, context = browser_context
    page = _load_mock_page_with_host(
        context, MOCK_PAGES / "glm_chat.html", "chatglm.cn")
    yield page
    page.close()


@pytest.fixture
def mock_deepseek_page(browser_context):
    _, context = browser_context
    page = _load_mock_page_with_host(
        context, MOCK_PAGES / "deepseek_chat.html", "deepseek.com")
    yield page
    page.close()
