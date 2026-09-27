// 模块：extend/dialog/parts/08c_bridge.js
// 用途：设置面板「远程桥接」区块（QQ ↔ 网页 AI）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 区块内容：总开关、连接状态、QQ 凭证、三类消息推送开关、指令列表编辑器。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 渲染一个推送开关行。
   * @param {Object} ctx Vue 实例
   * @param {string} kind 类型：user / tool / ai / thinking
   * @param {string} label 显示名
   * @returns {VNode} 开关行
   */
  function pushRow(ctx, kind, label) {
    const on = !!ctx.bridgePush[kind];
    return h('div', { class: 'bridge-push-row', key: kind }, [
      h('span', { class: 'bridge-push-label' }, label),
      h('button', {
        class: 'switch ' + (on ? 'on' : 'off'),
        onClick: () => ctx.toggleBridgePush(kind)
      }, on ? '开' : '关')
    ]);
  }

  /**
   * 远程桥接区块。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderBridgeBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', {
          title: '在手机 QQ 里与网页 AI 对话：看得见回复、发得出消息、点得动指令'
        }, '远程桥接（QQ）'),
        h('button', { onClick: () => { ctx.bridgeOpen = !ctx.bridgeOpen; } },
          ctx.bridgeOpen ? '▾' : '▸')
      ]),
      ctx.bridgeOpen ? h('div', { class: 'bridge-body' }, [
        // 提示：远程功能需保持面板开启
        h('div', { class: 'hint' },
          '远程功能需保持面板开启。关闭抽屉即代表你此刻不需要远程工作。'),
        // 总开关 + 连接状态
        h('div', { class: 'bridge-row' }, [
          h('label', { class: 'bridge-toggle' }, [
            h('input', {
              type: 'checkbox',
              checked: ctx.bridgeEnabled,
              onChange: (e) => { ctx.bridgeEnabled = e.target.checked; ctx.saveBridge(); }
            }),
            '启用远程桥接'
          ]),
          h('span', {
            class: 'bridge-status ' + (ctx.bridgeConnected ? 'on' : 'off')
          }, ctx.bridgeConnected ? '● 已连接' : '○ 未连接')
        ]),
        // QQ 凭证
        h('label', ['QQ 机器人 AppID', h('input', {
          type: 'text',
          value: ctx.bridgeAppId,
          placeholder: '开放平台应用的 AppID',
          onInput: (e) => { ctx.bridgeAppId = e.target.value; }
        })]),
        h('label', ['QQ 机器人 AppSecret', h('input', {
          type: 'password',
          value: ctx.bridgeAppSecret,
          placeholder: '开放平台应用的 AppSecret',
          onInput: (e) => { ctx.bridgeAppSecret = e.target.value; }
        })]),
        h('div', [
          h('button', { onClick: () => ctx.saveBridge() }, '保存并重启桥接'),
          h('span', { class: 'hint' }, '保存后自动重建 QQ 长连接')
        ]),
        h('br'),
        // 推送开关：三类消息 + 思考过程
        h('div', { class: 'card-head' }, [h('span', '推送内容')]),
        pushRow(ctx, 'user', '用户消息'),
        pushRow(ctx, 'tool', '工具消息'),
        pushRow(ctx, 'ai', 'AI 消息'),
        pushRow(ctx, 'thinking', '思考过程（默认不推，冗长）'),
        h('br'),
        // 指令列表：内置指令说明 + 自定义指令编辑器
        h('div', { class: 'card-head' }, [h('span', 'QQ 指令')]),
        h('div', { class: 'hint' },
          '内置：/css 清空所有会话、/cms 清空当前会话消息、'
          + '/csp 复制 System Prompt 并发送、/rtime 秒数 设置回传延迟、'
          + '/stime 切换自动回传开关、/sessions 会话列表、/ss 序号 切换会话、'
          + '/screenshot 截屏、/help 指令列表'),
        // 自定义指令：命令名 + 显示名 + 选择元素（不再手填选择器）
        h('div', { class: 'bridge-cmd-new' }, [
          h('input', {
            type: 'text', placeholder: '命令名（含 /，如 /deploy）',
            value: ctx.bridgeNewCmdName,
            onInput: (e) => { ctx.bridgeNewCmdName = e.target.value; }
          }),
          h('input', {
            type: 'text', placeholder: '显示名',
            value: ctx.bridgeNewCmdLabel,
            onInput: (e) => { ctx.bridgeNewCmdLabel = e.target.value; }
          })
        ]),
        h('div', { class: 'bridge-pick-row' }, [
          h('button', {
            onClick: () => ctx.bridgePicking ? ctx.stopPickElement() : ctx.startPickElement()
          }, ctx.bridgePicking ? '取消选择' : '选择元素'),
          ctx.bridgePicked
            ? h('span', { class: 'bridge-picked', title: ctx.bridgePicked.selector },
              '已选：' + (ctx.bridgePicked.tag || '') + ' ' + ctx.bridgePicked.selector)
            : h('span', { class: 'hint' }, '点「选择元素」后，在页面上点击要触发的元素'),
          h('button', {
            disabled: !ctx.bridgePicked || !ctx.bridgeNewCmdName || !ctx.bridgeNewCmdLabel,
            onClick: () => ctx.addBridgeCommand()
          }, '添加')
        ]),
        ctx.bridgeCommands.length
          ? h('div', { class: 'bridge-cmd-list' }, ctx.bridgeCommands.map((c, i) =>
            h('div', { class: 'bridge-cmd-item', key: i }, [
              h('span', { class: 'bridge-cmd-name' }, c.name),
              h('span', { class: 'bridge-cmd-label' }, c.label),
              h('span', { class: 'bridge-cmd-sel', title: c.selector || '' },
                c.selector ? ('点击 ' + c.selector) : ''),
              h('button', {
                onClick: () => ctx.editBridgeCommandSelector(i)
              }, '改选择器'),
              h('button', {
                class: 'danger',
                onClick: () => ctx.removeBridgeCommand(i)
              }, '删除')
            ])))
          : h('div', { class: 'empty' }, '（暂无自定义指令）')
      ]) : null
    ]);
  };
})();
