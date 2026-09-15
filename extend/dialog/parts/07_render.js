// 模块：extend/dialog/parts/07_render.js
// 用途：组件渲染函数。仅做整体装配：设置面板 + 消息镜像 + 头部。
//       具体卡片 / 设置面板渲染见 07_cards.js、08_settings.js。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、
//       parts/07_cards.js、parts/08_settings.js、Vue 全局构建
//
// 说明：Manifest V3 扩展页 CSP 禁止 unsafe-eval，因此不能用 template 字符串，
// 这里统一使用渲染函数 h()，无需运行期编译器。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /** 组件渲染函数：组装设置面板与主界面。 */
  D.render = function () {
    const ctx = this;

    // 统一时序：所有条目（文字消息、外部卡片）放进同一个数组，一律按 _ts 排序。
    // 消息与卡片都带同一个 _ts 字段、同为毫秒时间戳，因此排序规则完全相同，
    // 没有任何类型区分、没有任何先后推送设定。工具卡片是消息内的代码块，随其消息一并渲染。
    // 渲染方向为「最新在前」（倒序），与镜像对话一致。
    const entries = [];
    ctx.messages.forEach((m, i) => {
      entries.push({ ts: (m._ts != null ? m._ts : 0), node: () => D.renderMessage(ctx, m, i, i) });
    });
    ctx.externalCards.forEach((c) => {
      entries.push({ ts: (c._ts != null ? c._ts : (c.createdAt || 0)), node: () => D.renderExternalCard(ctx, c) });
    });
    entries.sort((a, b) => b.ts - a.ts);
    const mirrorItems = entries.map((e) => e.node());

    // 主界面只保留网页对话镜像（外部卡片与工具卡片一并呈现）
    const mirrorBlock = h('section', { class: 'card' }, [
      h('div', { class: 'card-head' }, [
        h('span', '网页对话镜像（' + ctx.messages.length + '）'),
        h('span', { class: 'head-actions' }, [
          h('button', { onClick: () => ctx.reparse() }, '重新解析'),
          h('button', { onClick: () => ctx.copyConversationJson() }, '复制JSON')
        ])
      ]),
      ctx.curConv.title ? h('div', { class: 'conv-title' }, '当前会话：' + ctx.curConv.title) : null,
      mirrorItems.length
        ? h('div', { class: 'mirror' }, mirrorItems)
        : h('div', { class: 'empty' }, '（等待网页对话内容…）')
    ]);

    const body = h('div', { class: 'm-body' }, [mirrorBlock]);

    return h('div', { class: 'mirror-app' }, [
      h('header', { class: 'm-header' }, [
        h('div', { class: 'title' }, [
          'AI 工具调用镜像',
          ctx.siteKey ? h('span', { class: 'site-badge' }, ctx.siteKey) : null
        ]),
        h('div', { class: 'actions' }, [
          h('button', {
            title: ctx.panelSide === 'left' ? '切换到右侧挂靠' : '切换到左侧挂靠',
            onClick: () => ctx.switchPanelSide()
          }, ctx.panelSide === 'left' ? '⇥' : '⇤'),
          h('button', { title: '设置', onClick: () => { ctx.settingsOpen = !ctx.settingsOpen; } }, '⚙'),
          h('button', { title: '关闭', onClick: () => ctx.closePanel() }, '✕')
        ])
      ]),
      D.renderSettings(ctx),
      body,
      ctx.toastMsg ? h('div', { class: 'toast' }, ctx.toastMsg) : null
    ]);
  };
})();
