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
      pushRow(ctx, 'voice', '语音（识别 + 合成，关闭则丢弃语音）'),
      // 语音引擎选择：仅当语音开关打开时才有意义，但始终显示便于预先配置
      renderVoiceEngineRow(ctx),
      // 音色选择：选项随当前引擎变化（系统语音 / 本地模型 / 在线音色）
      renderVoiceToneRow(ctx)
    ]);
  }

  /**
   * 渲染「音色」选择行。
   *
   * 三类引擎的音色来源完全不同，选项由后端 /api/bridge/voices 按引擎给出：
   *   pyttsx3 —— Windows 系统语音（读注册表）
   *   piper   —— 本地模型文件（每个 .onnx 一个音色）
   *   edge_tts—— 在线固定音色名
   * 因此切换引擎后必须重新拉取选项，否则下拉里还是上一个引擎的音色。
   *
   * 保存时按引擎写入各自字段：pyttsx3_voice / piper_model / edge_tts_voice。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 选择行
   */
  function renderVoiceToneRow(ctx) {
    const engine = ctx.bridgePush.voice_engine || 'auto';
    const list = ctx._voiceToneList || [];
    // 当前值按实际生效的引擎取对应配置字段
    const real = ctx._voiceToneEngine || engine;
    const field = real === 'piper' ? 'piper_model'
      : (real === 'edge_tts' ? 'edge_tts_voice' : 'pyttsx3_voice');
    const cur = ctx.bridgePush[field] || '';
    const opts = list.map((v) => h('option', {
      value: v.id, selected: v.id === cur
    }, v.name));
    if (!opts.length) {
      // 拉取中或该引擎无可选音色：给一个占位项，避免下拉空白
      opts.push(h('option', { value: cur, selected: true }, cur || '（暂无可选音色）'));
    }
    return h('div', { class: 'bridge-push-row', key: 'voice_tone' }, [
      h('span', { class: 'bridge-push-label' }, '语音音色'),
      h('select', {
        class: 'bridge-sel-input',
        value: cur,
        onChange: (e) => ctx.setBridgePushField(field, e.target.value)
      }, opts)
    ]);
  }

  /**
   * 渲染「语音合成引擎」选择行。
   *
   * 引擎说明（与后端 voice_tts.py 一致）：
   *   auto    按下方顺序逐个尝试，前一个失败自动降级到下一个（推荐）
   *   piper   本地神经网络，离线、音质较好，需先跑 scripts/setup_piper.py
   *   pyttsx3 系统语音，离线，需 pip 安装 pyttsx3 + pywin32
   *   sapi    Windows 自带语音，离线、零安装，不依赖任何第三方包
   *   edge_tts 微软在线合成，目前接口已失效，仅作历史保留
   *
   * 选择后立即保存（与开关行为一致），保存后后端重启桥接生效。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 选择行
   */
  function renderVoiceEngineRow(ctx) {
    const cur = ctx.bridgePush.voice_engine || 'auto';
    const opts = [
      ['auto', '自动（按顺序降级）'],
      ['piper', 'Piper（本地，需安装）'],
      ['pyttsx3', '系统语音（需装包）'],
      ['sapi', '系统语音（零安装）'],
      ['edge_tts', 'edge-tts（在线，当前失效）']
    ];
    return h('div', { class: 'bridge-push-row', key: 'voice_engine' }, [
      h('span', { class: 'bridge-push-label' }, '语音合成引擎'),
      h('select', {
        class: 'bridge-sel-input',
        value: cur,
        onChange: (e) => ctx.setBridgePushField('voice_engine', e.target.value)
      }, opts.map(([v, label]) => h('option', { value: v, selected: v === cur }, label)))
    ]);
  }

  /**
   * 渲染「质量检测」区块：各类检测各自独立开关。
   * 关闭某类即不检测该类（默认全开）。
   * 本区块挂在「通用配置」下渲染（见 08_settings.js 的 renderGeneralSettings），
   * 定义留在本文件是为了复用同文件的 pushRow 开关行组件。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  D.renderCheckBlock = function (ctx) {
    return h('div', [
      h('div', { class: 'card-head' }, [h('span', '质量检测（关闭则不检测该类）')]),
      pushRow(ctx, 'check_code_only', '只含代码块、无文字说明'),
      pushRow(ctx, 'check_thinking', '思考内容非中文'),
      pushRow(ctx, 'check_multi_call', '多个工具调用块'),
      pushRow(ctx, 'check_memory', '记忆滞后（连续多轮未写记忆）')
    ]);
  };

  /**
   * 渲染「QQ 指令」区块：内置指令说明 + 自定义指令编辑器 + 指令列表。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  function renderCmdBlock(ctx) {
    return h('div', [
      h('div', { class: 'card-head' }, [h('span', 'QQ 指令')]),
      // 先放指令编辑器与自定义指令列表，最后再列可用内置指令的提示文本：
      // 用户添加/查看自定义指令是主要动作，内置指令说明属参考信息，放末尾不挡路。
      renderCmdEditor(ctx),
      renderCmdList(ctx),
      // 内置指令参数：通用渲染，声明来自后端，前端不写死任何指令名。
      renderBuiltinParams(ctx),
      // 内置指令：渲染成可点击按钮，点一下即执行，便于用户逐条测试。
      // 分组与条目均来自后端结构化数据，前端不写死任何指令名。
      h('div', { class: 'hint' }, '可用指令（点击即执行）：'),
      renderHelpGroups(ctx)
    ]);
  }

  /**
   * 渲染内置指令按钮：按后端返回的分组铺开，每条形如「快捷键 描述」。
   *
   * 点击即调 runBridgeCommand，与 QQ 里敲指令走同一条链路，
   * 回执落网页收件箱，用户能直接看到执行结果。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 分组容器
   */
  function renderHelpGroups(ctx) {
    const groups = ctx.bridgeHelpGroups || [];
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
   * 这样内置指令的配置项展示不再特殊化，新增带参数的内置指令时后端登记一行即可。
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
