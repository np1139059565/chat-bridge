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
        renderConnBlock(ctx),
        h('br'),
        renderPushBlock(ctx),
        h('br'),
        renderCheckBlock(ctx),
        h('br'),
        renderCmdBlock(ctx),
      ]) : null
    ]);
  };

  /**
   * 渲染「连接与凭证」区块：提示、总开关与状态、AppID/AppSecret、Markdown 选择器、保存按钮。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  function renderConnBlock(ctx) {
    return h('div', [
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
      // Markdown 复制按钮选择器：内置指令 /md 使用它采集带格式原文。
      // 推送 QQ 时优先用采集到的 Markdown，没有则退回纯文本。留空则关闭。
      h('label', ['Markdown 复制按钮选择器（对应内置指令 /md，留空则关闭）', h('input', {
        type: 'text', class: 'bridge-sel-input',
        value: ctx.bridgeMdSelector,
        placeholder: '如 .ds-virtual-list--printable ... :has(.ds-cross-fade)',
        onInput: (e) => { ctx.bridgeMdSelector = e.target.value; }
      })]),
      h('div', { class: 'bridge-pick-row' }, [
        h('button', { onClick: () => ctx.testMdSelector() }, '采集测试'),
        h('span', { class: 'hint' }, '用当前选择器试采一次，看能否取到内容')
      ]),
      h('div', [
        h('button', { onClick: () => ctx.saveBridge() }, '保存并重启桥接'),
        h('span', { class: 'hint' }, '保存后自动重建 QQ 长连接')
      ])
    ]);
  }

  /**
   * 渲染「推送内容」区块：用户 / 工具 / AI / 思考四类开关。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  function renderPushBlock(ctx) {
    return h('div', [
      h('div', { class: 'card-head' }, [h('span', '推送内容')]),
      pushRow(ctx, 'user', '用户消息'),
      pushRow(ctx, 'tool', '工具消息'),
      pushRow(ctx, 'ai', 'AI 消息'),
      pushRow(ctx, 'thinking', '思考过程（默认不推，冗长）'),
      pushRow(ctx, 'voice', '语音（识别 + 合成，关闭则丢弃语音）')
    ]);
  }

  /**
   * 渲染「质量检测」区块：各类检测各自独立开关。
   * 关闭某类即不检测该类（默认全开）。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  function renderCheckBlock(ctx) {
    return h('div', [
      h('div', { class: 'card-head' }, [h('span', '质量检测（关闭则不检测该类）')]),
      pushRow(ctx, 'check_code_only', '只含代码块、无文字说明'),
      pushRow(ctx, 'check_thinking', '思考内容非中文'),
      pushRow(ctx, 'check_multi_call', '多个工具调用块'),
      pushRow(ctx, 'check_memory', '记忆滞后（连续多轮未写记忆）')
    ]);
  }

  /**
   * 渲染「QQ 指令」区块：内置指令说明 + 自定义指令编辑器 + 指令列表。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  function renderCmdBlock(ctx) {
    return h('div', [
      h('div', { class: 'card-head' }, [h('span', 'QQ 指令')]),
      // 指令说明从后端拉取（与 /h 同源），不再手写，避免与指令表漂移
      h('div', { class: 'hint' }, '内置指令（与 /h 同源）：'),
      h('pre', { class: 'bridge-help' }, ctx.bridgeHelpText || '（未加载，检查后端连接）'),
      renderCmdEditor(ctx),
      renderCmdList(ctx)
    ]);
  }

  /**
   * 渲染自定义指令编辑器：命令名 / 显示名、类型切换、步骤或选择器、添加 / 取消按钮。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 编辑器节点
   */
  function renderCmdEditor(ctx) {
    return h('div', [
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
      // 类型切换：点击元素 / 组合指令
      h('div', { class: 'bridge-type-row' }, [
        h('label', { class: 'bridge-toggle' }, [
          h('input', {
            type: 'checkbox',
            checked: ctx.bridgeNewCmdIsCombo,
            onChange: (e) => { ctx.bridgeNewCmdIsCombo = e.target.checked; }
          }),
          '组合指令'
        ])
      ]),
      renderComboEditor(ctx),
      renderPickerRow(ctx),
      renderCmdSaveRow(ctx)
    ]);
  }

  /** 渲染组合指令的步骤编辑器（仅组合类型显示，否则返回 null）。 */
  function renderComboEditor(ctx) {
    if (!ctx.bridgeNewCmdIsCombo) return null;
    return h('div', { class: 'bridge-combo-editor' }, [
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
    ]);
  }

  /** 渲染元素选择行与选择器输入框（组合类型下给出提示，否则提供选择按钮与输入框）。 */
  function renderPickerRow(ctx) {
    return h('div', [
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
      }) : null
    ]);
  }

  /** 渲染添加 / 保存修改按钮行（编辑中时附取消按钮）。 */
  function renderCmdSaveRow(ctx) {
    return h('div', { class: 'bridge-pick-row' }, [
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
    ]);
  }

  /** 渲染自定义指令列表；无指令时给出空态提示。 */
  function renderCmdList(ctx) {
    if (!ctx.bridgeCommands.length) return h('div', { class: 'empty' }, '（暂无自定义指令）');
    return h('div', { class: 'bridge-cmd-list' }, ctx.bridgeCommands.map((c, i) =>
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
      ])));
  }
})();
