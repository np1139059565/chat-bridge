// qianwen 输入适配器 —— 安装到页面主世界（经调试扩展 exec_js 注入执行）
// 用法：
//   ① 安装：exec_js 执行本文件全部内容（幂等：已安装则只更新定义）
//   ② 发送：return await window.__qianwenAdapter.send('消息文本')
//   ③ 状态：return window.__qianwenAdapter.state()  → 'idle' | 'generating'
// 注意：exec_js 总超时 15s，send 内部所有等待上限都据此收紧（空闲等待 8s）；
//       长生成请用两次调用模式：先 send，再单独轮询 state() 等完成。
(function () {
  const SEL_EDITOR = 'div[contenteditable=true][role=textbox]'; // 必须带 role 区分预览/占位节点
  const BTN_SEND = '发送消息';  // 空闲态按钮 aria-label
  const BTN_STOP = '停止回答';  // 生成态按钮 aria-label

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const findBtn = (label) => [...document.querySelectorAll('button')]
    .find((b) => (b.getAttribute('aria-label') || '') === label);

  /** 当前生成状态：存在「停止回答」按钮即生成中 */
  function state() {
    return findBtn(BTN_STOP) ? 'generating' : 'idle';
  }

  /** 等待页面回到空闲态（上一次生成结束才注入，避免打字机期间状态错乱） */
  async function waitIdle(timeout) {
    const t0 = Date.now();
    while (state() === 'generating') {
      if (Date.now() - t0 > timeout) throw new Error('WAIT_IDLE_TIMEOUT');
      await sleep(300);
    }
  }

  /** 注入文本到输入框：contenteditable 唯一可靠路径是 paste 事件（实测第 8 条） */
  async function inject(text) {
    const ed = document.querySelector(SEL_EDITOR);
    if (!ed) throw new Error('EDITOR_NOT_FOUND');
    ed.focus();
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    ed.dispatchEvent(new ClipboardEvent('paste', {
      clipboardData: dt, bubbles: true, cancelable: true,
    }));
    // React 状态同步窗口：实测约 300ms 后按钮解禁，留 400ms 余量
    await sleep(400);
    const btn = findBtn(BTN_SEND);
    if (!btn || btn.disabled) throw new Error('INJECT_NOT_APPLIED');
    return btn;
  }

  /**
   * 完整发送：等空闲 → 注入 → 确认解禁 → 点击发送 → 确认进入生成态。
   * @returns {{sent: string, generating: boolean}}
   */
  async function send(text, opts) {
    const o = opts || {};
    await waitIdle(o.idleTimeout || 8000);
    const btn = await inject(text);
    btn.click();
    await sleep(1200); // 等页面进入生成态（实测 1.8s 内必切换）
    const confirmed = state() === 'generating'
      || document.body.innerText.includes(text);
    if (!confirmed) throw new Error('SEND_NOT_CONFIRMED');
    // 可选等待完成：默认关闭。开启时注意 exec_js 15s 总超时。
    if (o.waitDone) {
      const t0 = Date.now();
      while (state() === 'generating') {
        if (Date.now() - t0 > (o.doneTimeout || 8000)) {
          throw new Error('WAIT_DONE_TIMEOUT');
        }
        await sleep(500);
      }
    }
    return { sent: text, generating: state() === 'generating' };
  }

  window.__qianwenAdapter = { send, inject, state, SEL_EDITOR, BTN_SEND, BTN_STOP };
})();
