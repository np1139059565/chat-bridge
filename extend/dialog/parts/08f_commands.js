// 模块：extend/dialog/parts/08f_commands.js
// 用途：设置页「指令」区块的渲染——自定义指令编辑器、指令列表、
//       内置指令参数与可点击的指令按钮。
//       指令经 message_router 对所有通道生效，不限于某一条通道，故独立成块。
//       从 08c_bridge.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 渲染「指令」区块：自定义指令编辑、内置指令参数与可点击的指令按钮。
   *
   * 独立成块的原因：指令经 message_router 对所有通道生效，不属于任何单条通道，
   * 挂进「远程桥接（QQ）」会让人误以为只有 QQ 能用。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  D.renderCommandBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', { title: '指令对所有通道生效：可在 QQ / 微信 / 企业微信里直接发送' }, '指令'),
        h('button', { onClick: () => { ctx.cmdOpen = !ctx.cmdOpen; } },
          ctx.cmdOpen ? '▾' : '▸')
      ]),
      ctx.cmdOpen ? h('div', { class: 'bridge-body' }, [renderCmdBlock(ctx)]) : null
    ]);
  };

  /**
   * 渲染指令区主体：编辑器、自定义列表、内置参数、可点击指令按钮。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块内容节点
   */
  function renderCmdBlock(ctx) {
    return h('div', [
      // 先放指令编辑器与自定义指令列表，最后再列可用内置指令的提示文本：
      // 用户添加/查看自定义指令是主要动作，内置指令说明属参考信息，放末尾不挡路。
      renderCmdEditor(ctx),
      renderCmdList(ctx),
      // 内置指令参数：通用渲染，声明来自后端，前端不写死任何指令名。
      renderBuiltinParams(ctx),
      // 内置指令：渲染成可点击按钮，点一下即执行，便于用户逐条测试。
      h('div', { class: 'hint' }, '可用指令（点击即执行）：'),
      renderHelpGroups(ctx)
    ]);
  }

  /**
   * 渲染内置指令按钮：按后端返回的分组铺开，每条形如「快捷键 描述」。
   *
   * 点击即调 runBridgeCommand，与在手机里敲指令走同一条链路，
   * 回执落网页收件箱，用户能直接看到执行结果。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 分组容器
   */
  function renderHelpGroups(ctx) {
    const groups = ctx.bridgeHelpGroups || [];
    // 未加载：给出提示，避免用户以为没有可用指令
    if (!groups.length) {
      return h('div', { class: 'hint' }, '（未加载，检查后端连接）');
    }
    return h('div', { class: 'bridge-help-groups' }, groups.map((g) =>
      h('div', { class: 'bridge-help-group', key: 'g-' + g.group }, [
        h('div', { class: 'bridge-help-title' }, g.group),
        h('div', { class: 'bridge-help-items' }, (g.items || []).map((it) =>
          h('button', {
            class: 'bridge-cmd-btn',
            key: 'c-' + it.key,
            title: it.name + ' — ' + (it.desc || ''),
            onClick: () => ctx.runBridgeCommand(it.key),
          }, [
            h('span', { class: 'k' }, it.key),
            h('span', { class: 'd' }, it.desc || ''),
          ])
        )),
      ])
    ));
  }

  /**
   * 渲染「内置指令参数」区：遍历后端返回的参数声明，逐项渲染输入框。
   *
   * 关键：这是通用机制——前端不写死「/md」或「选择器」，只按声明渲染。
   * 参数值统一存在 ctx.bridgeCmdParams[cmd][key]，与设置页保存的 command_params 同构。
   * @param {Object} ctx Vue 实例
   * @returns {VNode|null} 参数区节点；无声明时返回 null
   */
  function renderBuiltinParams(ctx) {
    const defs = ctx.bridgeCmdParamDefs || [];
    if (!defs.length) return null;
    return h('div', { class: 'bridge-builtin-params' }, [
      h('div', { class: 'hint' }, '内置指令参数：'),
      ...defs.map((d) => h('label', { key: d.cmd + '.' + d.key }, [
        d.label + '（指令 /' + d.cmd + '）',
        h('input', {
          type: 'text', class: 'bridge-sel-input',
          value: ((ctx.bridgeCmdParams[d.cmd] || {})[d.key]) || '',
          placeholder: d.placeholder || '',
          onInput: (e) => {
            if (!ctx.bridgeCmdParams[d.cmd]) ctx.bridgeCmdParams[d.cmd] = {};
            ctx.bridgeCmdParams[d.cmd][d.key] = e.target.value;
          }
        }),
        d.hint ? h('span', { class: 'hint' }, d.hint) : null
      ])),
      // 采集测试：验证当前选择器能否取到内容。放参数区末尾，不单独特殊化展示。
      h('div', { class: 'bridge-pick-row' }, [
        h('button', { onClick: () => ctx.testMdSelector() }, '测试采集'),
        h('span', { class: 'hint' }, '用当前参数试采一次，看能否取到内容')
      ])
    ]);
  }

  /**
   * 渲染自定义指令编辑器：命令名 / 显示名、类型切换、步骤或选择器、添加 / 取消按钮。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 编辑器节点
   */
  function renderCmdEditor(ctx) {
    // 仅「点具体指令进入编辑态」才纳入覆盖检测；新建表单不检测
    const editProps = ctx.bridgeEditIdx === null ? { 'data-cfg-skip': '1' } : {};
    return h('div', editProps, [
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
          }, ctx.bridgePicking ? '取消选择' : '选择元素')
      ]),
      // 选择器输入框：点「选择元素」会自动填入，也可直接打字修改。
      // 内容原样传给执行端求值，写法不限。
      (!ctx.bridgeNewCmdIsCombo) ? h('input', {
        type: 'text', class: 'bridge-sel-input',
        placeholder: '选择器或表达式',
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
