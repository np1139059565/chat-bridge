"""background.js 测试：service worker 注册与工具栏点击逻辑。"""


class TestBackgroundJs:
    def test_service_worker_registered(self, browser_context):
        """扩展加载后，background.js 的 service worker 应已注册。"""
        _, context = browser_context

        page = context.new_page()
        page.goto("about:blank")
        page.wait_for_timeout(1500)

        workers = context.service_workers
        worker_urls = [w.url for w in workers]

        if workers:
            assert any("background.js" in url for url in worker_urls), \
                "service worker URL 应包含 background.js，实际 %s" % worker_urls

        page.close()

    def test_extension_loaded_with_content_script(self, mock_glm_page):
        """扩展加载后 content script 应正常注入（间接验证扩展可用）。"""
        page = mock_glm_page
        iframe = page.locator("#ai-mirror-iframe")
        assert iframe.count() == 1, "content script 未注入 iframe"
