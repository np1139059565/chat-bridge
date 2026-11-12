// 模块：extend/lib/translator.js
// 用途：阶段 2 翻译员本体 —— 标准 tool_calls / tool 消息双向翻译、提示词拼装、
//       语言包与指令定义的取回入口（规格 4.3 / 4.4，阶段 2 范围 1~5）。
// 对外接口：window.AIMirrorTranslator = { ... }
// 依赖：lib/dialects.js（须先加载）。纯逻辑 + 注入式 apiFetch，不持有界面状态。
//
// 边界：本模块「新增」标准协议适配能力；网页 AI 侧既有建卡/执行/回传链路
//       在阶段 2 保持原样（行为与改造前一致），旧直调路径由阶段 3 删除（决策 2）。
//       一刀切：不提供任何新旧切换开关。
(function (global) {
  'use strict';

  var D = global.AIMirrorDialects;

  // 翻译员本体的共享上下文：抽屉启动时异步取回，generateSystemPrompt 同步读。
  // 初值即兜底态，后端不可达时全流程不中断（阶段 2 验收：行为与改造前一致）。
  var state = {
    standard: '',       // /v1/system_prompt 返回的标准四段全文
    pack: null,         // 当前站点语言包（/api/clients 的 custom_config）
    commands: [],       // /api/commands 下发的服务端指令定义
    commandHelp: '',    // /api/commands/help 的分组帮助文本
    siteKey: ''         // 最近一次取回所用的站点标识
  };

  // 标准四段的本机等价兜底：/v1/system_prompt 不可达时用它，保证提示词不空、
  // 网页 AI 全流程不中断。段落名与服务端 MARK_* 一致，便于分发方核对。
  var FALLBACK_STANDARD = [
    '【身份】',
    '你是本地工具服务的标准对话客户端，按规则与技能说明完成任务，',
    '需要外部能力时通过标准工具接口调用本地工具。',
    '',
    '【规则】',
    '规则名与读取优先级由工具服务下发；正文按需用 read_rule 读取。',
    '',
    '【技能】',
    '技能清单由工具服务下发，仅含已上线技能。',
    '',
    '【调用前先查参数】',
    '调用任何工具前，先用 get_tool_params 查询该工具的准确参数名。'
  ].join('\n');

  /** 取回标准四段：注入式 apiFetch 便于纯逻辑测试；失败返回空串由拼装层兜底。 */
  function fetchStandard(apiFetch, ctx) {
    return Promise.resolve()
      .then(function () {
        return apiFetch(ctx, '/v1/system_prompt', { headers: { Accept: 'application/json' } });
      })
      .then(function (data) { return String((data && data.system_prompt) || ''); })
      .catch(function () { return ''; });
  }

  /** 取回语言包：按 site_key 走 /api/clients 的 custom_config，原样不解释。 */
  function fetchLanguagePack(apiFetch, ctx, siteKey) {
    var key = String(siteKey || '').trim();
    if (!key) return Promise.resolve(null);
    var path = '/api/clients?site_key=' + encodeURIComponent(key);
    return Promise.resolve()
      .then(function () { return apiFetch(ctx, path, { headers: { Accept: 'application/json' } }); })
      .then(function (data) { return D.languagePack(data && data.custom_config); })
      .catch(function () { return null; });
  }

  /** 对接服务端下发的指令定义：清单 + 帮助文本同批取回，失败给空值不阻断。 */
  function fetchCommands(apiFetch, ctx) {
    return Promise.all([
      Promise.resolve().then(function () { return apiFetch(ctx, '/api/commands', {}); })
        .catch(function () { return {}; }),
      Promise.resolve().then(function () { return apiFetch(ctx, '/api/commands/help', {}); })
        .catch(function () { return {}; })
    ]).then(function (pair) {
      return {
        commands: (pair[0] && pair[0].commands) || [],
        help: String((pair[1] && pair[1].help) || '')
      };
    });
  }

  /** 方言说明（规格 4.3）：调用格式 / 回传格式 / 语音朗读稿约定 / 工具清单。 */
  function defaultDialect(opts) {
    var o = opts || {};
    var lines = [
      '【方言·工具调用格式】',
      '需要调用工具时，在一个独立 JSON 代码块中返回，',
      '且必须携带 "type": "bridge-chat-call" 标记：',
      '{"tool":"工具名称","type":"bridge-chat-call","parameters":{}}',
      '每次回复只允许一个调用代码块；解释文字放在调用上方。',
      '',
      '【方言·结果回传格式】',
      '执行结果作为一段 JSON 文本回传（无代码围栏），',
      '形如 {"tool":"工具名称","type":"bridge-chat-res","nonce":"...","success":true,"result":...}。',
      '',
      '【方言·工具清单】',
      String(o.toolLines || '（暂无工具）')
    ];
    if (o.voiceOn) {
      lines.push('', '【方言·朗读稿约定】',
        '每轮另附一个 {"type":"bridge-voice","text":"纯口语文本"} 代码块，仅一个。');
    }
    return lines.join('\n');
  }

  /** 拼装：取回的标准四段 + 追加方言说明（阶段 2 提示词口径）。 */
  function composePrompt(standard, dialect) {
    var base = String(standard || '').trim() || FALLBACK_STANDARD;
    var tail = String(dialect || '').trim() || defaultDialect({});
    return base + '\n\n' + tail;
  }

  /** bridge-chat-call 代码块 → 标准 tool_calls 项。 */
  function toToolCalls(block) {
    if (!block || typeof block !== 'object') return [];
    if (block.type !== 'bridge-chat-call' || !block.tool) return [];
    var id = 'call_' + String(block.nonce || '0');
    var args = block.parameters && typeof block.parameters === 'object'
      ? block.parameters : {};
    return [{
      id: id, type: 'function',
      function: { name: String(block.tool), arguments: JSON.stringify(args) }
    }];
  }

  /** 一轮里的多个调用块：网页 AI 单线程，取首个并给出拦截告警（规格 4.4）。 */
  function fromBlocks(blocks) {
    var arr = Array.isArray(blocks) ? blocks : [];
    var calls = [];
    for (var i = 0; i < arr.length; i++) {
      var one = toToolCalls(arr[i]);
      if (one.length) calls.push(one[0]);
    }
    return {
      calls: calls.slice(0, 1),
      warning: calls.length > 1 ? 'multiple_tool_calls' : ''
    };
  }

  /** 执行信封 → 标准 tool 消息（成败由 content 内 JSON 判断，无额外布尔字段）。 */
  function toToolMessage(callId, name, envelope) {
    return {
      role: 'tool',
      tool_call_id: String(callId || ''),
      name: String(name || ''),
      content: JSON.stringify(envelope == null ? {} : envelope)
    };
  }

  /** 标准 tool 消息 → bridge-chat-res 文本，贴回网页对话（工具服务 → 网页 AI）。 */
  function fromToolMessage(msg) {
    if (!msg || msg.role !== 'tool') return '';
    var body = {};
    try { body = JSON.parse(String(msg.content || '{}')); } catch (e) { body = {}; }
    var out = {
      tool: String(msg.name || (body && body.tool) || ''),
      type: 'bridge-chat-res',
      nonce: String(msg.tool_call_id || ''),
      success: body.success !== false
    };
    if (out.success) out.result = body.result == null ? body : body.result;
    else { out.error = body.error || ''; if (body.hint) out.hint = body.hint; }
    return JSON.stringify(out);
  }

  /** 按站点取方言策略：薄包装 dialects.pick，本体不重复实现分派。 */
  function dialectFor(siteKey) {
    return D.pick(siteKey);
  }

  var api = {
    state: state,
    FALLBACK_STANDARD: FALLBACK_STANDARD,
    fetchStandard: fetchStandard,
    fetchLanguagePack: fetchLanguagePack,
    fetchCommands: fetchCommands,
    defaultDialect: defaultDialect,
    composePrompt: composePrompt,
    toToolCalls: toToolCalls,
    fromBlocks: fromBlocks,
    toToolMessage: toToolMessage,
    fromToolMessage: fromToolMessage,
    dialectFor: dialectFor
  };
  global.AIMirrorTranslator = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
