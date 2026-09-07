"""e2e：扩展加载、iframe 注入、HTML 关键元素渲染。"""
import pytest


class TestExtensionLoaded:
    def test_iframe_injected(self, mock_glm_page):
        page = mock_glm_page
        frame = page.locator("#ai-mirror-iframe")
        assert frame.count() == 1, "悬浮对话框 iframe 未注入"

    def test_dialog_html_elements_exist(self, mock_glm_page):
        page = mock_glm_page
        frame_el = page.locator("#ai-mirror-iframe")
        assert frame_el.count() == 1

        # 进入 iframe 断言对话框关键元素
        frame = page.frame_locator("#ai-mirror-iframe")
        # 等待 Vue 应用挂载
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # HTML 覆盖：关键元素存在
        assert frame.locator(".m-header").count() == 1, "标题栏缺失"
        title_text = frame.locator(".m-header .title").inner_text()
        assert "AI 工具调用镜像" in title_text, "标题文本错误"
        assert "chatglm.cn" in title_text, "标题应显示站点徽章"
        assert frame.locator(".m-body").count() == 1, "消息区缺失"

    def test_dialog_visible_by_default(self, mock_glm_page):
        page = mock_glm_page
        frame = page.locator("#ai-mirror-iframe")
        display = frame.evaluate("(el) => el.style.display")
        assert display != "none", "对话框默认应该可见"

    def test_settings_panel_tool_list(self, mock_glm_page):
        """设置面板应渲染工具列表（HTML 覆盖）。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 点击设置按钮打开设置面板
        settings_btn = frame.locator(".m-header .actions button")
        assert settings_btn.count() == 1
        settings_btn.click()

        frame.locator(".settings").wait_for(timeout=3000)
        tool_list = frame.locator(".tool-list")
        assert tool_list.count() == 1, "工具列表未渲染"

        tools_text = tool_list.inner_text()
        assert "list_dir" in tools_text, "工具列表缺少 list_dir"
        assert "read_file" in tools_text, "工具列表缺少 read_file"


class TestToolCallCard:
    def test_tool_code_block_generates_card(self, mock_glm_page):
        """模拟对话页中的 tool 代码块应被提取并在对话框中生成执行卡片。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 卡片应出现在对话框消息区（`.code-card` 用于普通代码和工具卡片）
        cards = frame.locator(".code-card")
        assert cards.count() >= 2, "未生成足够的代码卡片"

        # 第一张工具卡片应包含工具名
        first_card_text = cards.first.inner_text()
        assert "工具调用 · list_dir" in first_card_text, "卡片未显示工具名"
