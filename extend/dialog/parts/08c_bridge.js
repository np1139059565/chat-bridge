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
          '内置（快捷键 — 作用）：/css 清空所有会话、/cms 清空当前会话消息、'
          + '/csp 复制 System Prompt 并发送、/rt 秒数 设置回传延迟、'
          + '/sa on|off 自动回传开关、/ls 会话列表、/ss 序号 切换会话、'
          + '/sp 截屏、/cp 复制结果、/rp 重新解析、/rr 重新执行、'
          + '/rs 重启服务、/rf 刷新页面、/h 指令列表'),
        // 自定义指令：命令名 + 显示名 + 类型（点击元素 / 组合指令）
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
        // 类型切换：点击元素 / 组合指令 / 采集 Markdown（三者互斥）
        h('div', { class: 'bridge-type-row' }, [
          h('label', { class: 'bridge-toggle' }, [
            h('input', {
              type: 'checkbox',
              checked: ctx.bridgeNewCmdIsCombo,
              onChange: (e) => {
                ctx.bridgeNewCmdIsCombo = e.target.checked;
                if (e.target.checked) ctx.bridgeNewCmdCollect = false;
              }
            }),
            '组合指令'
          ]),
          h('label', { class: 'bridge-toggle' }, [
            h('input', {
              type: 'checkbox',
              checked: ctx.bridgeNewCmdCollect,
              onChange: (e) => {
                ctx.bridgeNewCmdCollect = e.target.checked;
                if (e.target.checked) ctx.bridgeNewCmdIsCombo = false;
              }
            }),
            '采集 Markdown'
          ])
        ]),
        // 组合指令：步骤列表（每行一条）。仅组合类型显示。
        ctx.bridgeNewCmdIsCombo
          ? h('div', { class: 'bridge-combo-editor' }, [
            h('div', { class: 'hint' }, '每行一条指令，按顺序执行。例如：'),
            h('pre', { class: 'bridge-combo-sample' }, '/cms\n/reparse\n/copy'),
            h('textarea', {
              placeholder: '每行一条指令',
              value: ctx.bridgeNewCmdSteps,
              onInput: (e) => { ctx.bridgeNewCmdSteps = e.target.value; }
            }),
            // 执行间隔：可配置，默认 1 秒
            h('label', { class: 'bridge-interval' }, [
              '步骤间隔（秒）',
              h('input', {
                type: 'number', min: '0.2', step: '0.1',
                value: ctx.bridgeNewCmdInterval,
                onInput: (e) => { ctx.bridgeNewCmdInterval = e.target.value; }
              })
            ])
          ])
          : null,
        h('div', { class: 'bridge-pick-row' }, [
          // 「选择元素」只在点击类型下显示
          ctx.bridgeNewCmdIsCombo
            ? h('span', { class: 'hint' }, '组合指令无需选择元素')
            : h('button', {
              onClick: () => ctx.bridgePicking ? ctx.stopPickElement() : ctx.startPickElement()
            }, ctx.bridgePicking ? '取消选择' : '选择元素'),
          (!ctx.bridgeNewCmdIsCombo)
            ? h('span', { class: 'hint' }, '也可直接在下方输入/编辑选择器')
            : null
        ]),
        // 选择器输入框：点「选择元素」会自动填入，也可直接打字修改
        (!ctx.bridgeNewCmdIsCombo) ? h('input', {
          type: 'text', class: 'bridge-sel-input',
          placeholder: '选择器，如 #btn-go 或 .submit-btn',
          value: ctx.bridgePicked ? (ctx.bridgePicked.selector || '') : '',
          onInput: (e) => {
            // 直接编辑选择器：保留原 page_url，清掉 tag（不再对应某个具体元素）
            ctx.bridgePicked = {
              selector: e.target.value,
              page_url: (ctx.bridgePicked && ctx.bridgePicked.page_url) || '',
              tag: ''
            };
          }
        }) : null,
        h('div', { class: 'bridge-pick-row' }, [
          h('button', {
            disabled: !ctx.bridgeNewCmdName || !ctx.bridgeNewCmdLabel
              || (ctx.bridgeNewCmdIsCombo
                ? !ctx.bridgeNewCmdSteps.trim()
                : !(ctx.bridgePicked && ctx.bridgePicked.selector)),
            onClick: () => ctx.saveBridgeCommand()
          }, ctx.bridgeEditIdx === null ? '添加' : '保存修改'),
          // 编辑中时提供取消按钮，避免误存
          ctx.bridgeEditIdx !== null
            ? h('button', { onClick: () => ctx.cancelEditBridgeCommand() }, '取消')
            : null
        ]),
        ctx.bridgeCommands.length
          ? h('div', { class: 'bridge-cmd-list' }, ctx.bridgeCommands.map((c, i) =>
            h('div', { class: 'bridge-cmd-item', key: i }, [
              h('span', { class: 'bridge-cmd-name' }, c.name),
              h('span', { class: 'bridge-cmd-label' }, c.label),
              h('span', { class: 'bridge-cmd-sel', title: c.selector || '' },
                (c.steps && c.steps.length)
                  ? ('组合 ' + c.steps.length + ' 步：' + c.steps.join(' → '))
                  : (c.collect
                    ? ('采集 Markdown：' + (c.selector || ''))
                    : (c.selector ? ('点击 ' + c.selector) : ''))),
              h('button', {
                onClick: () => ctx.editBridgeCommand(i)
              }, '编辑'),
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
