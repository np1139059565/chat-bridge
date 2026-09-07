"""e2e：动态 DOM 场景——覆盖 content.js 的 MutationObserver、会话切换、容器替换逻辑。"""


class TestDynamicDomScenarios:
    def test_mutation_observer_detects_new_message(self, mock_glm_page):
        """动态插入新消息后，content.js 应检测到变化并推送到 iframe。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 记录当前消息数
        initial_count = frame.locator(".msg").count()
        assert initial_count >= 4, "初始消息数异常：%d" % initial_count

        # 在对话容器中动态插入一条新消息（匹配真实 GLM DOM 结构）
        page.evaluate("""
            () => {
                const container = document.querySelector('.detail.chatScrollContainer.conversation-list');
                const item = document.createElement('div');
                item.className = 'conversation-item';
                item.innerHTML = `
                    <div class="conversation question" id="row-question-dynamic">
                        <div class="user-name">用户</div>
                        <div class="question-txt"><p>动态插入的消息</p></div>
                    </div>
                    <div class="answer" id="row-answer-dynamic">
                        <div class="assistant-name">AI</div>
                        <div class="answer-content">
                            <div class="answer-content-wrap">
                                <p>动态插入的回答。</p>
                            </div>
                        </div>
                    </div>
                `;
                container.appendChild(item);
            }
        """)

        # 等待 MutationObserver 触发（debounce 600ms + 解析时间）
        page.wait_for_timeout(1500)

        # 消息内容应包含动态插入的文本
        mirror_text = frame.locator(".mirror").inner_text()
        assert "动态插入的消息" in mirror_text, \
            "MutationObserver 未检测到动态插入的消息"

    def test_conversation_container_replacement_reattaches_observer(self, mock_glm_page):
        """对话容器整块替换后，content.js 应重新绑定 observer。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 整块替换对话容器（模拟 GLM 切会话时的节点替换）
        page.evaluate("""
            () => {
                const oldContainer = document.querySelector('.detail.chatScrollContainer.conversation-list');
                const newContainer = document.createElement('div');
                newContainer.className = 'detail chatScrollContainer conversation-list';
                newContainer.innerHTML = `
                    <div class="conversation-item">
                        <div class="conversation question">
                            <div class="user-name">用户</div>
                            <div class="question-txt"><p>替换后的新消息</p></div>
                        </div>
                        <div class="answer">
                            <div class="assistant-name">AI</div>
                            <div class="answer-content">
                                <div class="answer-content-wrap">
                                    <p>新容器中的回答。</p>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                oldContainer.parentNode.replaceChild(newContainer, oldContainer);
            }
        """)

        # watchConversation 轮询间隔 700ms，需要等待至少一个轮询周期 + 处理时间
        page.wait_for_timeout(2500)

        # 新容器内容应被提取
        mirror_text = frame.locator(".mirror").inner_text()
        assert "替换后的新消息" in mirror_text, \
            "容器替换后未重新绑定 observer，新内容未被提取"

    def test_session_switch_via_container_change(self, mock_glm_page):
        """会话切换（容器替换）后，新消息应被提取。"""
        page = mock_glm_page
        frame = page.frame_locator("#ai-mirror-iframe")
        frame.locator(".mirror-app").wait_for(timeout=5000)

        # 第一条消息应该在
        initial_text = frame.locator(".mirror").inner_text()
        assert "请列出当前目录下的文件" in initial_text, \
            "初始消息未提取（mock 页面结构可能不正确）"

        # 替换容器模拟会话切换
        page.evaluate("""
            () => {
                const oldContainer = document.querySelector('.detail.chatScrollContainer.conversation-list');
                const newContainer = document.createElement('div');
                newContainer.className = 'detail chatScrollContainer conversation-list';
                newContainer.innerHTML = `
                    <div class="conversation-item">
                        <div class="conversation question">
                            <div class="user-name">用户</div>
                            <div class="question-txt"><p>新会话的第一条消息</p></div>
                        </div>
                        <div class="answer">
                            <div class="assistant-name">AI</div>
                            <div class="answer-content">
                                <div class="answer-content-wrap">
                                    <p>新会话回答。</p>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                oldContainer.parentNode.replaceChild(newContainer, oldContainer);
            }
        """)

        page.wait_for_timeout(2500)
        new_text = frame.locator(".mirror").inner_text()
        assert "新会话的第一条消息" in new_text, "新会话内容未被提取"


class TestBfcacheRecovery:
    def test_pageshow_bfcache_reinjection(self, mock_glm_page):
        """bfcache 恢复时（pageshow persisted），iframe 被移除后应重新注入。"""
        page = mock_glm_page

        # 手动移除 iframe 模拟 bfcache 场景
        page.evaluate("""
            () => {
                const f = document.getElementById('ai-mirror-iframe');
                if (f) f.remove();
            }
        """)

        # 触发 pageshow（模拟 bfcache 恢复）
        page.evaluate("""
            () => {
                const event = new PageTransitionEvent('pageshow', { persisted: true });
                window.dispatchEvent(event);
            }
        """)

        # 等待 content.js 重新注入 iframe
        page.wait_for_selector("#ai-mirror-iframe", timeout=5000)
        assert page.locator("#ai-mirror-iframe").count() == 1
