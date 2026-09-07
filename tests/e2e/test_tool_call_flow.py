"""e2e：端到端工具调用链路。"""
import json
import re

import pytest


class TestToolCallFlow:
    def test_extract_tool_code_block_from_mock_page(self, mock_glm_page):
        """content.js 应从模拟对话页提取 tool 代码块。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")

        # 等待 Vue 应用挂载
        frame.locator(".mirror-app").wait_for(timeout=5000)
        # 消息项应有内容
        messages = frame.locator(".msg")
        assert messages.count() >= 2, "应提取到至少两条消息"

    def test_card_executes_tool_and_shows_result(self, mock_glm_page, flask_server):
        """第一张工具卡片调用 list_dir，应显示执行结果。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 找到工具卡片（含「工具调用 · list_dir」的 .code-card）
        tool_cards = frame.locator(".code-card", has_text="工具调用 · list_dir")
        assert tool_cards.count() >= 1, "未找到 list_dir 工具卡片"

        # 点击执行按钮
        run_btn = tool_cards.first.locator("button", has_text="执行")
        assert run_btn.count() >= 1, "未找到执行按钮"
        run_btn.first.click()

        # 等待结果出现（.result 元素）
        frame.locator(".code-card .result").wait_for(timeout=5000)
        result_text = frame.locator(".code-card .result").first.inner_text()
        assert "flask_server" in result_text or "directory" in result_text, \
            "执行结果应包含目录信息"

    def test_deepseek_page_extracts_tool_block(self, mock_deepseek_page):
        """DeepSeek 模拟页应提取 search_content 工具代码块。"""
        page = mock_deepseek_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        tool_cards = frame.locator(".code-card", has_text="工具调用 · search_content")
        assert tool_cards.count() >= 1, "DeepSeek 页未生成 search_content 工具卡片"
