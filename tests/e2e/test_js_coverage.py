"""e2e：JS 行覆盖率采集与门槛断言。"""
import json
import sys
from pathlib import Path

import pytest

# 将当前目录加入 sys.path，使 js_coverage.py 可导入
sys.path.insert(0, str(Path(__file__).parent))

from js_coverage import collect_js_coverage, assert_js_coverage_threshold


class TestJsCoverage:
    def test_collect_and_assert_js_coverage(self, mock_glm_page):
        """在 GLM 模拟页上执行后，采集扩展脚本覆盖率并断言门槛。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 模拟一段用户交互：打开设置面板、点击工具列表，触发更多 app.js 代码执行
        settings_btn = frame.locator(".m-header .actions button")
        if settings_btn.count() == 1:
            settings_btn.click()
            frame.locator(".settings").wait_for(timeout=3000)

        report = collect_js_coverage(page)

        # 保存报告供 CI 读取
        output_dir = Path(__file__).parent / "artifacts"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "js_coverage.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        # 断言门槛（当前目标：60%）
        assert_js_coverage_threshold(report, threshold=60.0)
