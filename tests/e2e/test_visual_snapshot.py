"""CSS/HTML 视觉测试：分组件截图 + computed style 验证。

覆盖策略：
- 分组件截图比对（顶栏、设置面板、对话镜像、代码卡片）
- 关键 CSS 规则的 computed style 断言
- 关键 HTML 元素的存在性与可见性
"""
import hashlib
from pathlib import Path

import pytest

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _screenshot_component(frame, selector: str, name: str):
    """截图组件并保存，首次生成基线，之后比对。"""
    snapshots = SNAPSHOTS_DIR / name
    snapshot = snapshots / "baseline.png"
    actual = snapshots / "actual.png"

    if not snapshot.exists():
        snapshots.mkdir(parents=True, exist_ok=True)
        frame.locator(selector).screenshot(path=str(snapshot))
        pytest.skip("已生成 %s 基线快照，下次运行将进行比对" % name)

    frame.locator(selector).screenshot(path=str(actual))
    assert _md5(snapshot) == _md5(actual), \
        "%s 视觉快照不一致，请检查 style.css 变更" % name


class TestHtmlCoverage:
    """HTML 关键元素存在性断言（dialog.html 渲染出的 DOM）。"""

    def test_mirror_app_root_structure(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 根结构
        assert frame.locator("#app").count() == 1
        assert frame.locator(".mirror-app").count() == 1
        assert frame.locator(".m-header").count() == 1
        assert frame.locator(".m-body").count() == 1

    def test_header_contains_title_and_actions(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 顶栏：标题、站点徽章、设置按钮
        assert frame.locator(".m-header .title").count() == 1
        assert frame.locator(".m-header .site-badge").count() == 1
        assert frame.locator(".m-header .actions button").count() == 1

        title = frame.locator(".m-header .title").inner_text()
        assert "AI 工具调用镜像" in title

    def test_messages_area_renders_conversation(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 对话镜像区域
        assert frame.locator(".mirror").count() == 1
        assert frame.locator(".msg").count() >= 2
        assert frame.locator(".msg.user").count() >= 1
        assert frame.locator(".msg.assistant").count() >= 1

        # 消息内结构
        assert frame.locator(".msg .avatar").count() >= 2
        assert frame.locator(".msg .bubble").count() >= 2
        assert frame.locator(".msg .who").count() >= 2

    def test_code_card_renders_tool_call(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 工具卡片
        tool_cards = frame.locator(".code-card", has_text="工具调用")
        assert tool_cards.count() >= 1

        # 卡片内部结构
        first_card = tool_cards.first
        assert first_card.locator(".code-head").count() == 1
        assert first_card.locator(".toolname").count() == 1
        assert first_card.locator(".badge").count() == 1
        assert first_card.locator(".params-json").count() == 1
        assert first_card.locator("button").count() >= 1

    def test_settings_panel_structure(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 打开设置面板
        frame.locator(".m-header .actions button").click()
        frame.locator(".settings").wait_for(timeout=3000)

        # 设置面板内部结构
        assert frame.locator(".settings-bar").count() == 1
        assert frame.locator(".settings-body").count() == 1
        assert frame.locator(".tool-list").count() == 1
        assert frame.locator(".tool-row").count() >= 9

        # 工具行结构
        first_tool = frame.locator(".tool-row").first
        assert first_tool.locator(".tree-node").count() == 1
        assert first_tool.locator(".switch").count() == 1


class TestCssComputedStyle:
    """关键 CSS 规则的 computed style 断言。"""

    def test_header_background_is_primary(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        bg = frame.locator(".m-header").evaluate(
            "(el) => getComputedStyle(el).backgroundColor")
        assert bg == "rgb(45, 108, 223)", \
            "顶栏背景应为主色 var(--cb-primary) = #2d6cdf，实际 %s" % bg

    def test_header_text_is_white(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        color = frame.locator(".m-header").evaluate(
            "(el) => getComputedStyle(el).color")
        assert color == "rgb(255, 255, 255)", \
            "顶栏文字应为白色，实际 %s" % color

    def test_params_json_uses_subtle_background(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        bg = frame.locator(".params-json").first.evaluate(
            "(el) => getComputedStyle(el).backgroundColor")
        assert bg == "rgb(247, 249, 252)", \
            "参数 JSON 背景应为浅色 var(--cb-bg-subtle) = #f7f9fc，实际 %s" % bg

    def test_body_font_family(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        font = frame.locator("body").evaluate(
            "(el) => getComputedStyle(el).fontFamily")
        assert "Segoe UI" in font or "Microsoft YaHei" in font or "-apple-system" in font, \
            "正文字体应包含系统字体栈，实际 %s" % font


class TestComponentScreenshots:
    """分组件截图比对。"""

    def test_header_screenshot(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)
        _screenshot_component(frame, ".m-header", "header")

    def test_messages_screenshot(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)
        _screenshot_component(frame, ".mirror", "messages")

    def test_code_card_screenshot(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)
        _screenshot_component(frame, ".code-card >> nth=0", "code-card")

    def test_settings_screenshot(self, mock_glm_page):
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)
        frame.locator(".m-header .actions button").click()
        frame.locator(".settings").wait_for(timeout=3000)
        _screenshot_component(frame, ".settings", "settings")
