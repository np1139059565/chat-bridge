// 模块：extend/dialog/parts/08c_bridge.js
// 用途：设置面板的两类区块——「远程桥接（QQ）」连接与凭证，
//       以及三通道共用的「投递策略」（推送内容、语音、质量检测）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 指令区已迁至 08f_commands.js：指令对所有通道生效，不归单条通道。
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
        // 本区块只管 QQ 自己的连接与凭证；推送内容与指令列表已移到各自归属的区块。
        renderConnBlock(ctx),
      ]) : null
    ]);
  };

  /**
   * 渲染「投递策略」区块：决定哪些内容推到手机、以什么形式推。
   *
   * 独立成块的原因：推送开关与语音配置存在配置的 bridge 顶层，对三条通道同时生效，
   * 不属于任何单条通道。质量检测同属投递策略（决定回传什么），一并放这里。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 该区块节点
   */
  D.renderDeliveryPolicyBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', { title: '三条通道共用：决定哪些内容推送到手机，以及语音的识别与合成' },
          '投递策略（全通道共用）'),
        h('button', { onClick: () => { ctx.deliveryOpen = !ctx.deliveryOpen; } },
          ctx.deliveryOpen ? '▾' : '▸')
      ]),
      ctx.deliveryOpen ? h('div', { class: 'bridge-body' }, [
        // 广播：决定「发给谁」，是投递策略的第一层，故排在推送内容之前
        renderBroadcastRow(ctx),
        h('br'),
        renderPushBlock(ctx), h('br'), D.renderCheckBlock(ctx),
      ]) : null
    ]);
  };

  /**
   * 渲染「广播」开关行。
   *
   * 独占（默认）：一条上报只发给最近说话的那条通道，避免多通道重复复读。
   * 广播：所有已启用通道各收一份，用于「怕漏看」的场景。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 开关行
   */
  function renderBroadcastRow(ctx) {
    const on = !!ctx.bridgeBroadcast;
    return h('div', { class: 'bridge-push-row', key: 'broadcast' }, [
      h('span', { class: 'bridge-push-label', title: '关：只发给最近说话的通道；开：所有已启用通道各收一份' },
        '广播到所有通道'),
      h('button', {
        class: 'switch ' + (on ? 'on' : 'off'),
        onClick: () => { ctx.bridgeBroadcast = !on; ctx.saveBridge(); }
      }, on ? '开' : '关')
    ]);
  }


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
        'data-diff': D.blockFieldClass ? D.blockFieldClass(ctx, 'bridge', 'app_id', ctx.bridgeAppId) : '',
        placeholder: '开放平台应用的 AppID',
        onInput: (e) => { ctx.bridgeAppId = e.target.value; D.markBlockField(ctx, 'bridge', 'app_id', ctx.bridgeAppId); }
      })]),
      h('label', ['QQ 机器人 AppSecret', h('input', {
        type: 'text',
        value: ctx.bridgeAppSecret,
        'data-diff': D.blockFieldClass ? D.blockFieldClass(ctx, 'bridge', 'app_secret', ctx.bridgeAppSecret) : '',
        placeholder: '开放平台应用的 AppSecret',
        onInput: (e) => { ctx.bridgeAppSecret = e.target.value; D.markBlockField(ctx, 'bridge', 'app_secret', ctx.bridgeAppSecret); }
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
   * 四类引擎的音色来源完全不同，选项由后端 /api/bridge/voices 按引擎给出：
   *   pyttsx3 —— Windows 系统语音（读注册表，经 pyttsx3）
   *   sapi    —— Windows 自带系统语音（读 System.Speech 清单）
   *   piper   —— 本地模型文件（每个 .onnx 一个音色）
   *   edge_tts—— 在线固定音色名
   * 因此切换引擎后必须重新拉取选项，否则下拉里还是上一个引擎的音色。
   *
   * 保存时按引擎写入各自字段：pyttsx3_voice / sapi_voice / piper_model / edge_tts_voice。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 选择行
   */
  function renderVoiceToneRow(ctx) {
    const engine = ctx.bridgePush.voice_engine || 'auto';
    const list = ctx._voiceToneList || [];
    // 当前值按实际生效的引擎取对应配置字段
    const real = ctx._voiceToneEngine || engine;
    // 引擎 → 音色字段的映射：四类引擎各存各的，切换引擎不会互相覆盖。
    // 用映射表而非三元表达式，新增引擎时只改这里一处。
    const TONE_FIELD = {
      piper: 'piper_model',
      edge_tts: 'edge_tts_voice',
      sapi: 'sapi_voice',
      pyttsx3: 'pyttsx3_voice'
    };
    const field = TONE_FIELD[real] || 'pyttsx3_voice';
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

})();

// ctx.bridgeAppId_TRACKED

// ctx.bridgeAppSecret_TRACKED
