// 模块：extend/dialog/parts/05_messages.js
// 用途：消息与工具卡片相关逻辑：工具列表拉取、System Prompt 生成、
//       网页消息接收与解析、卡片构建、对话记录导出、格式化辅助。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /** 拉取后端工具目录；失败时回退内置列表。随后刷新技能说明段落与 System Prompt。 */
  M.fetchTools = async function () {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/tools', { headers: { 'Accept': 'application/json' } });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      this.tools = data.tools || data;
      this.flaskOk = true;
    } catch (e) {
      this.tools = D.FALLBACK_TOOLS;
      this.flaskOk = false;
      this.flaskError = String(e);
    }
    // 工具上下线会改变技能说明段落的生效集合，故一并刷新后再生 System Prompt
    await this.loadPromptSections();
  };

  /** 生成 System Prompt：含工具清单、调用格式、规则列表与技能说明。 */
  M.generateSystemPrompt = function () {
    const tools = this.tools || [];
    // 工具列表只展示名称与描述；参数定义由 AI 在调用前通过 get_tool_params 自行查询。
    // 这样 prompt 体积随工具数增长可控，也避免 AI 凭直觉臆造参数名。
    const listLines = tools.map((t, i) => {
      return `${i + 1}. ${t.name} — ${t.description}`;
    }).join('\n');
    // 规则列表：展示规则名、读取优先级与摘要；内容由 AI 通过 read_rule 按需读取。
    // off 的规则不写入（视为关闭，AI 不应主动读取）。
    const ruleLabel = (p) => ({ always: '总是', 'on-demand': '按需', off: '关闭' }[p] || '按需');
    const ruleActive = (this.rules || []).filter((r) => r.priority !== 'off');
    const ruleLines = ruleActive.map((r, i) => {
      return `${i + 1}. [${ruleLabel(r.priority)}] ${r.name} — ${r.summary || ''}`;
    }).join('\n') || '（暂无规则）';
    return `本会话通过「AI 工具调用镜像插件」与本地工具服务联动。\n\n【工具调用格式】\n当你需要调用工具时，请在一个独立的代码块中返回 JSON，代码块语言标记为 tool，\n且必须携带 "type": "bridge-chat-call" 标记（插件仅识别带此标记的代码块）：\n\`\`\`tool\n{\n  "tool": "工具名称",\n  "type": "bridge-chat-call",\n  "parameters": { "参数名": "参数值" }\n}\n\`\`\`\n插件会自动提取该代码块、调用本地服务执行，并把执行结果作为下一条消息回传给你，请据此继续完成任务。\n\n【执行结果回传格式】\n插件回传的结果是一段 JSON 文本，以 { 开始，无代码块围栏，形如（你无需再次调用，直接基于结果继续）：\n{\n  "tool": "工具名称",\n  "type": "bridge-chat-res",\n  "success": true,\n  "result": ...\n}\n失败时同一结构返回，字段为 success: false 与 error 等诊断信息。\n\n【支持的工具】\n${listLines}\n\n【工具参数查询】\n工具的完整参数定义（参数名、类型、必填性、说明）不直接列在此处。\n调用任何工具前，请先用 get_tool_params 工具查询该工具的参数定义（传入参数 tool_id = 工具名称），获得完整 schema 后再用正确的参数名调用。\n\n【单次只生成一个代码块】\n每次回复只允许包含一个工具调用代码块（即一个 \`\`\`tool 块）。\n不要在一次回复里并列多个代码块，也不要把解释文字与工具调用混在同一回复中。\n完成当前工具调用、收到插件回传的结果后，再决定并执行下一步；需要多步操作时请分步进行，每一步单独回复一个代码块。\n这样插件才能稳定地以「提取 → 执行 → 回传结果」逐轮推进，避免并发多个调用导致结果错乱。\n\n请在涉及文件读取、搜索、写入、删除等需求时，主动使用上述工具，并始终以 tool 代码块格式发起调用。\n\n【规则 Rules】\n- 先调用 list_rules 查看有哪些规则（规则名 + 优先级 + 摘要）；\n- 再用 read_rule（参数 name=规则名）读取对应规则的完整内容，并遵守它。\n每条规则前标注了读取优先级：\n- [总是]：必须读取并始终遵守，开始任务前先用 read_rule 读取其内容。\n- [按需]：在相关场景下先调用 read_rule 读取后再执行，不要凭记忆臆测。\n- （优先级为「关闭」的规则不会出现在此列表，也不应主动读取。）\n\n\n【规则列表】\n${ruleLines}\n${this.promptSectionText()}`;
  };

  /** 技能说明区域：置于 System Prompt 最末尾，无段落时整块省略。 */
  M.promptSectionText = function () {
    const secs = this.promptSections || [];
    if (!secs.length) return '';
    const body = secs.map((s) => '### ' + (s.skill || '') + '\n' + (s.text || '')).join('\n\n');
    return '\n【技能说明】\n' + body + '\n';
  };

  /** 接收来自内容脚本的窗口消息（会话切换、页面结构化内容等）。 */
  M.onPageMessage = function (e) {
    const d = e.data;
    if (!d || !d.type) return;
    if (d.type === 'panel_side') {
      this.panelSide = d.side === 'left' ? 'left' : 'right';
      return;
    }
    if (d.type === 'auto_send_result') {
      this.toast(d.ok ? (d.msg || '已回传结果到网页 AI') : ('回传失败：' + (d.msg || '')));
      return;
    }
    if (d.type === 'page_blocks') {
      // 先按站点切换（数据与设置都按站点隔离），再切会话，最后灌内容
      // 注意：profileId 要在 applySite 之前赋值 —— applySite 内部会 loadConfig，
      // 该站尚无存档时用内容脚本自动识别到的规则作为下拉框默认值。
      if (d.profileId) this.profileId = d.profileId;
      this.applySite(d.siteKey);
      this.applyConversation(d.conversationId, d.conversationTitle, d.url);
      this.ingestMessages(d.messages);
    }
  };

  /** 判断某工具是否为 silent（一次性副作用，结果不回传网页 AI）。 */
  M.toolSilent = function (name) {
    const t = (this.tools || []).find((x) => x.name === name);
    return !!(t && t.silent);
  };

  /**
   * 判断代码块是否为一次工具调用：内容是 { tool, parameters } 即算。
   * 不再依赖语言标记 —— DeepSeek 的代码块是 .md-code-block > pre，
   * 根本没有 language 标记，按 lang 过滤会导致工具调用完全识别不出来。
   * 安全性由调用方保证：只有「助手消息」里的代码块才会被判为工具调用。
   */
  M.parseToolCall = function (block) {
    if (!block || block.type !== 'code') return null;
    const src = String(block.code || '').trim();
    if (!src || src.charAt(0) !== '{') return null; // 快速排除非 JSON
    try {
      const obj = JSON.parse(src);
      // type 过滤：只有 bridge-chat-call 才是工具调用，其余代码块按普通代码渲染
      if (obj && typeof obj === 'object' && obj.tool && obj.type === 'bridge-chat-call') {
        return { tool: String(obj.tool), parameters: obj.parameters || {} };
      }
    } catch (e) { /* 不是工具调用，按普通代码块渲染 */ }
    return null;
  };

  /** 灌入一批网页消息：打时间戳并为助手代码块建立卡片。 */
  M.ingestMessages = function (messages) {
    const conv = this.curConv;
    log('ingestMessages 收到', (messages || []).length, '条消息（会话=' + this.activeConv + '）');
    conv.messages = messages || [];
    // 给每条消息打统一时间戳：首次出现时取当前时间，之后沿用（网页重绘不打乱顺序）。
    // 消息与外部卡片共用同一时间源，渲染时统一排序、不做任何类型区分。
    this.assignMsgTs(conv);
    conv.messages.forEach((m) => {
      (m.blocks || []).forEach((b) => {
        if (b.type !== 'code' || !b.id) return;
        // 已存在：保留执行状态（结果 / 错误 / 是否已执行过）
        if (conv.cardMap[b.id]) return;
        // 只把「助手回答」里的代码块当成可执行的工具调用。
        // 用户消息里的 System Prompt 自带 ```tool 示例块，绝不能生成卡片。
        const call = m.role === 'assistant' ? this.parseToolCall(b) : null;
        // silent 工具（如推送消息）为一次性副作用：执行后不回传结果，避免多一轮 AI 请求
        const silent = !!(call && this.toolSilent(call.tool));
        conv.cardMap[b.id] = {
          id: b.id,
          lang: b.lang || '',
          phase: '',   // 自动流程阶段：'' / 'exec'(执行倒计时) / 'send'(回传倒计时)
          code: b.code || '',
          isTool: !!call,
          silent: silent,
          tool: call ? call.tool : '',
          parameters: call ? call.parameters : {},
          status: 'pending',
          result: null,
          error: null,
          executed: false,   // 是否已被执行过（切换会话 / 刷新后据此恢复）
          stack: null,       // 本地工具代码完整堆栈（失败自愈用）
          errorType: '',
          origin: '',        // parameter / environment / tool_internal
          location: null,
          hint: '',
          createdAt: Date.now()
        };
        // 开启自动回传时，新建的工具卡片自动倒计时触发执行（无需点击）
        if (this.autoSendEnabled && !!call && !conv.cardMap[b.id].skipped) this.scheduleExecute(conv.cardMap[b.id]);
        log('新建卡片', b.id, call ? '工具:' + call.tool : '代码:' + (b.lang || '无'));
      });
    });
    // 恢复进行中先不写盘：等 mergeCardMap 合并完再写，
    // 避免把「尚未恢复的 pending 状态」写进存档把执行记录冲掉
    if (this._restoring > 0) return;
    if (this._persist) this._persist();
  };

  /** 重新解析当前网页对话。 */
  M.reparse = function () {
    window.parent.postMessage({ type: 'request_page' }, '*');
    this.toast('已重新解析当前网页对话');
  };

  /** 导出对话记录：纯 JSON，不含任何样式 / DOM 信息，便于存档与排查问题。 */
  M.buildLogJson = function () {
    const cards = [];
    Object.keys(this.cardMap).forEach((id) => {
      const c = this.cardMap[id];
      cards.push({
        id: c.id,
        type: c.isTool ? 'tool_call' : 'code',
        language: c.lang,
        tool: c.tool || undefined,
        parameters: c.isTool ? c.parameters : undefined,
        code: c.isTool ? undefined : c.code,
        status: c.status,
        executed: !!c.executed,          // 该卡片是否已被执行过
        origin: c.origin || undefined,   // 失败分类（parameter / environment / tool_internal）
        result: c.result,
        error: c.error
      });
    });
    return {
      source: 'ai-mirror',
      pageUrl: this.pageUrl,
      conversationId: this.activeConv,
      exportedAt: new Date().toISOString(),
      messageCount: this.messages.length,
      messages: this.messages.map((m) => ({
        role: m.role,
        name: m.name,
        blocks: (m.blocks || []).map((b) => {
          const base = { type: b.type };
          if (b.type === 'code') {
            base.language = b.lang;
            base.code = b.code;
            const c = this.cardMap[b.id];
            if (c && c.isTool) {
              base.tool = c.tool;
              base.parameters = c.parameters;
              base.status = c.status;
              if (c.result != null) base.result = c.result;
              if (c.error != null) base.error = c.error;
            }
          } else if (b.type === 'list') {
            base.ordered = b.ordered;
            base.items = b.items;
          } else if (b.type === 'table') {
            base.rows = b.rows;
          } else if (b.type === 'heading') {
            base.level = b.level;
            base.text = b.text;
          } else {
            base.text = b.text;
          }
          return base;
        })
      })),
      cards: cards
    };
  };

  /** 复制对话记录 JSON 到剪贴板。 */
  M.copyConversationJson = function () {
    const json = JSON.stringify(this.buildLogJson(), null, 2);
    this.copy(json);
    log('已导出对话记录 JSON，长度=' + json.length);
    this.toast('对话记录已复制为 JSON');
  };

  /** 展开 / 收起某个内置工具。 */
  M.toggleTool = function (name) {
    this.expanded[name] = !this.expanded[name];
  };

  /** 生成某工具的调用用法示例（JSON 文本）。 */
  M.usageOf = function (tool) {
    const params = {};
    (tool.parameters || []).forEach((p) => {
      params[p.name] = p.type === 'integer' || p.type === 'boolean' ? `<${p.type}>` : `<${p.type}>`;
    });
    return JSON.stringify({ tool: tool.name, parameters: params }, null, 2);
  };

  /** 卡片状态码 → 中文。 */
  M.statusText = function (s) {
    return ({ pending: '待执行', running: '执行中', done: '完成', error: '失败' })[s] || s;
  };

  /** 把值格式化为可读文本（字符串原样，其它 JSON 化）。 */
  M.fmt = function (val) {
    if (val == null) return '';
    return typeof val === 'string' ? val : JSON.stringify(val, null, 2);
  };

  /**
   * 回传给 AI 的结果：bridge-chat-res 结构化 JSON 代码块。
   * 失败时务必带上「错误分类 + 完整堆栈」，让 AI 能一眼分清是
   * 「参数写错」还是「本地工具代码缺陷」。
   */
  M.resultText = function (card) {
    const payload = { tool: card.tool, type: 'bridge-chat-res' };
    if (card.status === 'done') {
      payload.success = true;
      payload.result = card.result;
    } else {
      payload.success = false;
      payload.origin = card.origin || 'unknown';
      payload.originNote = 'parameter=参数问题，改参数重试即可；environment=路径/权限问题；'
        + 'tool_internal=本地工具代码缺陷，必须用 hot_reload_fix 修代码，改参数无效';
      if (card.errorType) payload.errorType = card.errorType;
      if (card.error) payload.error = card.error;
      if (card.location && card.location.file) payload.location = card.location;
      if (card.hint) payload.hint = card.hint;
      if (card.stack) payload.stack = card.stack;
    }
    return JSON.stringify(payload, null, 2);
  };

  /** 复制文本到剪贴板；不支持时回退到 execCommand 方案。 */
  M.copy = function (text) {
    const t = String(text);
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(() => this.toast('已复制'), () => this.fallbackCopy(t));
    } else {
      this.fallbackCopy(t);
    }
  };

  /** 兼容旧环境的复制实现：临时 textarea + execCommand。 */
  M.fallbackCopy = function (t) {
    const ta = document.createElement('textarea');
    ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); this.toast('已复制'); }
    catch (e) { this.toast('复制失败，请手动选择'); }
    document.body.removeChild(ta);
  };
})();
