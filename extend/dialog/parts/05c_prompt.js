// 模块：extend/dialog/parts/05c_prompt.js
// 用途：System Prompt 生成、当前对话重新解析、会话导出。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /** 生成 System Prompt：含工具清单、调用格式、规则列表与技能说明。 */
  M.generateSystemPrompt = function () {
    const tools = this.tools || [];
    // 工具列表只展示名称与描述；参数定义由 AI 在调用前通过 get_tool_params 自行查询。
    const listLines = tools.map((t, i) => {
      return `${i + 1}. ${t.name} — ${t.description}`;
    }).join('\n');
    // 规则列表：展示规则名、读取优先级与摘要；内容由 AI 通过 read_rule 按需读取。
    const ruleLabel = (p) => ({ always: '总是', 'on-demand': '按需', off: '关闭' }[p] || '按需');
    const ruleActive = (this.rules || []).filter((r) => r.priority !== 'off');
    const ruleLines = ruleActive.map((r, i) => {
      return `${i + 1}. [${ruleLabel(r.priority)}] ${r.name} — ${r.summary || ''}`;
    }).join('\n') || '（暂无规则）';
    // 技能列表：展示技能名、摘要与所含工具；已上线技能附加其统一说明。
    const sectionBySkill = {};
    (this.promptSections || []).forEach((s) => { sectionBySkill[s.skill] = s.text || ''; });
    const skillLines = (this.skills || []).map((s, i) => {
      let line = `${i + 1}. ${s.name} — ${s.summary || ''}`;
      const note = sectionBySkill[s.name];
      if (note) line += `\n   说明：${note}`;
      return line;
    }).join('\n') || '（暂无技能）';
    // 语音约定：仅当语音开关打开时注入。
    // 开关在浏览器侧，System Prompt 也在此生成，无需跨端传递。
    const voiceOn = !!(this.bridgePush && this.bridgePush.voice);
    const voiceBlock = voiceOn
      ? `\n\n【语音·朗读文本约定】\n你的回复正文照常书写；此外，每一轮回复都必须另用一个代码块，\n块内为 JSON，形如：{"type":"bridge-voice","text":"适合朗读的纯口语文本"}，\n供系统合成语音发回用户。要点：\n- text 内只放自然口语，不出现代码、表格、Markdown 符号、链接、括号注释；\n- 代码或术语请用口语描述其作用，而非照抄符号；\n- text 应自成一个完整、可独立听懂的口头说明；\n- 每一轮回复都必须包含且仅包含一个 bridge-voice 块。`
      : '';
    // 记忆使用约定：把「先检索、后抽检」写进固定上下文，降低对临时提醒的依赖。
    const memoryBlock = `\n\n【记忆·使用约定】\n- 收到用户新任务时，先调用 memory_search（query 用当前任务原文）检索历史记忆，\n  取回最近相关记忆的蒸馏精华，据此校准当前处境、消除臆测，再规划任务。\n- 检索后，按提醒节奏用 memory_inspect 抽检蒸馏质量；发现精华失真或关键词无效时，\n  用 memory_refine 修正。检索与抽检是两件事：检索用于「用记忆」，抽检用于「保质量」。`;
    return `本会话通过「AI 工具调用镜像插件」与本地工具服务联动。${memoryBlock}\n\n【Tool·调用说明】\n需要调用工具时，请在一个独立的 JSON 代码块中返回，\n且必须携带 "type": "bridge-chat-call" 标记（插件仅识别带此标记的代码块）：\n\`\`\`json\n{\n  "tool": "工具名称",\n  "type": "bridge-chat-call",\n  "parameters": { "参数名": "参数值" }\n}\n\`\`\`\n插件会自动提取该代码块、调用本地服务执行，并把执行结果作为下一条消息回传给你，请据此继续完成任务。\n结果回传为一段 JSON 文本（无代码块围栏），形如：\n{\n  "tool": "工具名称",\n  "type": "bridge-chat-res",\n  "nonce": "本次调用唯一标记",\n  "success": true,\n  "result": ...\n}\n每次回复只允许包含一个工具调用代码块（即一个 JSON 代码块），不要并列多个，要把解释文字放到调用的上面，与卡片混在同一回复中；收到回传结果后再决定下一步，需要多步操作时每一步单独回复一个代码块。\n调用任何工具前，先用 get_tool_params 查询该工具的准确参数名（传入 tool_id = 工具名称），不要臆造参数名。\n\n【Tool·工具列表】\n${listLines}\n\n【Rule·读取说明】\n- 先调用 list_rules 查看有哪些规则（规则名 + 优先级 + 摘要）；\n- 再用 read_rule（参数 name=规则名）读取对应规则的完整内容，并遵守它。\n每条规则前标注了读取优先级：\n- [总是]：必须读取并始终遵守，开始任务前先用 read_rule 读取其内容。\n- [按需]：在相关场景下先调用 read_rule 读取后再执行，不要凭记忆臆测。\n- （优先级为「关闭」的规则不会出现在此列表，也不应主动读取。）\n\n【Rule·规则列表】\n${ruleLines}\n\n【SKILL·读取说明】\n- 先调用 list_skills 查看本机有哪些技能（名称 + 摘要 + 所含工具）；\n- 再用 read_skill（参数 skill=技能名、file=技能内相对路径，如 SKILL.md）读取技能文档，按其规定处理。\n\n【SKILL·技能列表】\n${skillLines}${voiceBlock}`;
  };

  /** 重新解析当前网页对话。 */
  M.reparse = function () {
    window.parent.postMessage({ type: 'request_page' }, '*');
    this.toast('已重新解析当前网页对话');
  };

  /**
   * 把一个会话导出为纯 JSON。
   * 条目 key 即消息树 key（'父id-子id'）：消息用其树 key；外部卡片用其自身 key（同构）。
   * @param {string} id 会话 id
   * @param {Object} conv 会话记录
   * @param {Function|null} rangeFilter 条目过滤器：入参条目 key，返回是否包含
   * @param {string} [source] 'history'（累积分支，默认）或 'visible'（可见区切片）
   * @returns {Object} 可序列化的导出对象
   */
  M.buildConvExport = function (id, conv, rangeFilter, source) {
    const keep = typeof rangeFilter === 'function' ? rangeFilter : function () { return true; };
    const tree = conv.msgTree || {};
    const keys = source === 'visible' ? (conv.visibleKeys || []) : (conv.branchKeys || []);
    const messages = [];
    // 结构顺序：消息按 keys 顺序，外部卡片按锚点插入
    let timeline = D.buildTimeline(conv, keys);
    // 切片与历史断裂（未入树）时 keys 为空：改用 orphanSlice 导出，
    // 否则导出空结构，而镜像区却有内容。
    if (!timeline.length && (conv.orphanSlice || []).length) {
      timeline = conv.orphanSlice.map(function (m, i) {
        return { kind: 'message', key: 'orphan-' + i, node: m };
      });
    }
    timeline.forEach((it) => {
      if (it.kind === 'external') {
        const c = it.card;
        if (!c || !keep(D.externalCardKey(c))) return;
        messages.push({
          id: c.id,
          role: 'external',
          name: '用户',
          blocks: [{
            type: 'external',
            title: c.title || '',
            cardType: c.type || '',
            content: c.content || '',
            status: c.status,
            executed: !!c.executed,
            skipped: !!c.skipped,
            result: c.result,
            error: c.error
          }]
        });
        return;
      }
      const k = it.key;
      const node = it.node;
      if (!keep(k)) return;
      const mid = this.msgId(node);
      const item = {
        id: mid,
        role: node.role,
        name: node.name,
        blocks: window.AIMirrorDomUtils.toArray(node.blocks)
          .map((b) => this._exportBlock(b, node))
          .filter((b) => b !== null)
      };
      if (!item.blocks.length) return;
      messages.push(item);
    });
    return {
      source: 'ai-mirror',
      conversationId: id,
      title: conv.title || '',
      page_url: conv.page_url || '',
      exportedAt: new Date().toISOString(),
      messageCount: messages.length,
      messages: messages
    };
  };

  /**
   * 把单个内容块转成可序列化的导出对象；思考块返回 null（不导出）。
   * 工具代码块额外附带其卡片状态与结果。
   * @param {Object} b 内容块
   * @param {Object} node 该块所属消息节点（用于取卡片表）
   * @returns {Object|null} 导出块对象；不导出返回 null
   */
  M._exportBlock = function (b, node) {
    if (b.type === 'thinking') return null;   // 思考过程不导出
    const base = { type: b.type };
    if (b.type === 'code') {
      base.language = b.lang;
      base.code = b.code;
      const c = (node.cards || {})[b.id];
      if (c && c.isTool) {
        base.tool = c.tool;
        base.parameters = c.parameters;
        base.status = c.status;
        base.skipped = !!c.skipped;
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
  };

  /**
   * 导出镜像区当前可见的消息切片。
   * source 传 'visible'：只取 visibleKeys，即镜像区实际渲染的那几个节点，
   * 不涉及分支历史与已滚出视野的消息。
   */
  M.buildLogJson = function () {
    return this.buildConvExport(this.activeConv, this.curConv, null, 'visible');
  };

  /** 复制镜像区可见消息切片的 JSON 到剪贴板。 */
  M.copyConversationJson = function () {
    const json = JSON.stringify(this.buildLogJson(), null, 2);
    this.copy(json);
    log('已导出镜像区可见切片 JSON，长度=' + json.length);
    this.toast('镜像区可见消息已复制为 JSON');
  };

  /** 展开 / 收起某个内置工具。 */
  M.toggleTool = function (name) {
    this.expanded[name] = !this.expanded[name];
  };

  /** 生成某工具的调用用法示例（JSON 文本）。 */
  M.usageOf = function (tool) {
    const params = {};
    (tool.parameters || []).forEach((p) => {
      params[p.name] = '<' + p.type + '>';
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
   * 回传给 AI 的结果：bridge-chat-res 结构化 JSON。
   * 失败时带上「错误分类 + 完整堆栈」，让 AI 能分清参数写错还是工具代码缺陷。
   */
  M.resultText = function (card) {
    const nonce = this.ensureNonce(card);
    const payload = { tool: card.tool, type: 'bridge-chat-res', nonce: nonce };
    if (card.status === 'done') {
      payload.success = true;
      payload.result = card.result;
    } else {
      payload.success = false;
      payload.origin = card.origin || 'unknown';
      payload.originNote = 'parameter=参数问题，改参数重试即可；environment=路径/权限问题；'
        + 'tool_internal=本地工具代码缺陷，改参数无效，需检查工具实现';
      if (card.errorType) payload.errorType = card.errorType;
      if (card.error) payload.error = card.error;
      if (card.location && card.location.file) payload.location = card.location;
      if (card.hint) payload.hint = card.hint;
      if (card.stack) payload.stack = card.stack;
    }
    return JSON.stringify(payload, null, 2);
  };

  /**
   * 复制图片到剪贴板。
   * 用 ClipboardItem 写二进制；环境不支持时提示用户右键另存。
   * @param {string} dataUrl 图片 dataURL
   */
  M.copyImage = function (dataUrl) {
    if (typeof ClipboardItem === 'undefined' || !navigator.clipboard || !navigator.clipboard.write) {
      this.toast('当前环境不支持复制图片，请右键图片另存');
      return;
    }
    fetch(dataUrl).then((r) => r.blob()).then((blob) => {
      const item = new ClipboardItem({ [blob.type]: blob });
      return navigator.clipboard.write([item]);
    }).then(() => this.toast('已复制图片'), () => this.toast('复制图片失败，请右键另存'));
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
