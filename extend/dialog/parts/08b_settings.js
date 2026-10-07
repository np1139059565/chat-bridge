// 模块：extend/dialog/parts/08b_settings.js
// 用途：设置面板渲染（二）：会话记录区块、条目展开体、外部卡片、设置面板整体。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 会话记录区块：列出当前会话的全部条目（对话消息 + 工具卡片 + 外部卡片），
   * 按时间统一排序；每条带复选框，可勾选范围并复制 JSON。
   * 未勾选任何条目时，「复制」导出整个会话。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderSessionBlock = function (ctx) {
    const allList = ctx.sessionEntries || [];
    // 应用 id 搜索过滤：只影响展示，不影响导出范围（导出按勾选态决定）。
    const list = ctx.filteredSessionEntries || allList;
    return h('div', { class: 'sp-block conv-split' }, [
      renderConvListPane(ctx),
      // 中：可拖动分隔条，左右调节两栏宽度
      h('div', {
        class: 'conv-resizer',
        title: '拖动调节宽度',
        onPointerdown: (e) => ctx.startConvResize(e)
      }),
      // 右：消息记录栏
      h('div', { class: 'conv-record-pane' }, [
        renderRecordHead(ctx, allList, list),
        renderSearchBox(ctx),
        renderEntryList(ctx, list, allList)
      ])
    ]);
  };

  /**
   * 渲染左栏会话列表：标题行 + 各项（标题、消息数、更新时间）。
   * 宽度由 convListWidth 控制，可拖动分隔条调节；点某项即切换会话。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 左栏节点
   */
  function renderConvListPane(ctx) {
    return h('div', {
      class: 'conv-list-pane',
      style: { width: (ctx.convListWidth || 180) + 'px' }
    }, [
      h('div', { class: 'conv-list-head' }, [
        h('span', '会话（' + (ctx.convList || []).length + '）'),
        h('button', {
          class: 'danger',
          disabled: !(ctx.convList || []).length,
          title: '清空全部会话的聊天记录与卡片',
          onClick: () => ctx.clearAllConversations()
        }, '清空')
      ]),
      h('div', { class: 'conv-list' },
        (ctx.convList || []).map((c) => h('div', {
          class: 'conv-list-item' + (c.id === ctx.activeConv ? ' active' : ''),
          key: c.id,
          title: c.title,
          onClick: () => ctx.selectConversation(c.id)
        }, [
          h('span', { class: 'conv-list-title' }, c.title),
          h('span', { class: 'conv-list-meta' }, [
            h('span', { class: 'conv-list-count', title: '该会话消息树中的消息总数' },
              (c.msgCount || 0) + ' 条'),
            h('span', { class: 'conv-list-date' },
              c.updatedAt ? new Date(c.updatedAt).toLocaleDateString() : '')
          ])
        ])))
    ]);
  }

  /**
   * 渲染右栏头部：消息总数 + 清空 / 复制 JSON 按钮。
   * @param {Object} ctx Vue 实例
   * @param {Array} allList 全部条目
   * @param {Array} list 过滤后的条目（供按钮计数）
   * @returns {VNode} 头部节点
   */
  function renderRecordHead(ctx, allList, list) {
    const checkedCount = ctx.checkedEntryKeys.length;
    return h('div', { class: 'card-head' }, [
      h('span', '消息（' + allList.length + '）'),
      h('span', { class: 'head-actions' }, [
        h('button', {
          disabled: !allList.length,
          onClick: () => ctx.clearSession()
        }, '清空'),
        h('button', {
          onClick: () => ctx.exportSessionJson()
        }, checkedCount ? ('复制 JSON（' + checkedCount + '）') : '复制')
      ])
    ]);
  }

  /**
   * 渲染按 id 搜索的搜索框（带清除按钮）。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 搜索框节点
   */
  function renderSearchBox(ctx) {
    return h('div', { class: 'conv-search' }, [
      h('input', {
        type: 'text',
        placeholder: '按 id 搜索条目（消息指纹 / 卡片 id）',
        value: ctx.sessionSearch,
        onInput: (e) => { ctx.sessionSearch = e.target.value; }
      }),
      ctx.sessionSearch
        ? h('button', { class: 'h-del', title: '清除搜索', onClick: () => { ctx.sessionSearch = ''; } }, '✕')
        : null
    ]);
  }

  /**
   * 渲染条目列表（倒序）：勾选提示行 + 每条记录。
   * 展示倒序只在渲染层反转，sessionEntries 本身保持时间正序，导出与勾选不受影响。
   * @param {Object} ctx Vue 实例
   * @param {Array} list 过滤后的条目
   * @param {Array} allList 全部条目
   * @returns {VNode} 列表节点
   */
  function renderEntryList(ctx, list, allList) {
    if (!list.length) {
      return h('div', { class: 'empty' },
        allList.length ? '（没有匹配该 id 的条目）' : '（当前会话暂无内容）');
    }
    const checkedCount = ctx.checkedEntryKeys.length;
    const ordered = list.slice().reverse();
    const head = h('div', { class: 'conv-head', key: 'entry-head' }, [
      h('span', { class: 'conv-hint' },
        checkedCount ? ('已选 ' + checkedCount + ' 项') : '未勾选，将复制全部')
    ]);
    return h('div', { class: 'history-list' }, [head].concat(ordered.map((e) => renderEntryRow(ctx, e))));
  }

  /**
   * 渲染单条会话记录：复选框、展开开关、标题、id、删除按钮，展开态附内容。
   * @param {Object} ctx Vue 实例
   * @param {Object} e 条目
   * @returns {VNode} 条目节点
   */
  function renderEntryRow(ctx, e) {
    const isCard = e.kind !== 'message';
    const open = !!ctx.entryOpen[e.key];
    // 条目样式类：外部卡片与分支父节点各加一个标记类，便于着色区分。
    const entryCls = 'conv-entry'
      + (isCard ? ' is-external' : '')
      + (e.isExternalCall ? ' is-external-call' : '')
      + (e.isBranchParent ? ' is-branch-parent' : '');
    return h('div', {
      class: entryCls,
      key: e.key,
      'data-entry-key': e.key   // 供镜像区点击 pid-id 时定位到本条目
    }, [
      h('div', { class: 'history-item conv-item' }, [
        h('label', { class: 'conv-check' }, [
          h('input', {
            type: 'checkbox',
            checked: !!ctx.entryChecked[e.key],
            onChange: () => ctx.toggleEntryChecked(e.key)
          })
        ]),
        // 展开 / 收起：与镜像区「思考过程」同一交互，箭头指示折叠态
        h('button', {
          class: 'h-toggle',
          title: open ? '收起' : '展开查看',
          onClick: () => { ctx.entryOpen[e.key] = !open; }
        }, open ? '▾' : '▸'),
        h('span', { class: 'conv-title', title: e.preview || kindLabel(e) }, kindLabel(e)),
        // 条目 id：内容指纹 / 卡片 id，按原样显示。
        // 悬浮显示完整 key，点击复制 key，便于排查父子关系与幽灵卡片。
        h('span', {
          class: 'conv-id',
          title: 'key：' + e.key + '（点击复制）',
          onClick: () => ctx.copy(e.key)
        }, e.id),
        e.kind === 'message' && e.preview && !open
          ? h('span', { class: 'conv-meta', title: e.preview }, e.preview)
          : null,
        h('button', {
          class: 'h-del',
          title: '删除该卡片',
          onClick: () => ctx.removeEntry(e.key)
        }, '✕')
      ]),
      // 展开区：复用镜像区已有的块渲染与卡片渲染，保证两处呈现一致。
      open ? h('div', { class: 'conv-body' }, D.renderEntryBody(ctx, e)) : null
    ]);
  }

  /** 条目类型 → 展示用标签。只显示角色（用户/AI），省略块数以节省横向空间。 */
  function kindLabel(e) {
    if (e.kind === 'message') return e.role === 'user' ? '用户' : 'AI';
    return e.label || '';
  }

  /**
   * 渲染一个会话记录条目的完整内容（展开态）。
   * 消息：按块类型逐块渲染，复用镜像区的 renderBlock；
   * 工具 / 代码卡片：复用 renderCodeCard；
   * 外部卡片：复用 renderExternalCard。
   * 条目本身只带轻量摘要，这里按 key 回查真实对象，避免把重对象放进响应式列表。
   * @param {Object} ctx Vue 实例
   * @param {Object} e 条目摘要（含 key / kind）
   * @returns {Array} VNode 数组
   */
  D.renderEntryBody = function (ctx, e) {
    const conv = ctx.curConv;
    if (e.kind === 'message') {
      // key 即消息树 key（'父id-子id'），直接回树取节点
      const node = (conv.msgTree || {})[e.key];
      if (!node) return [h('div', { class: 'empty' }, '（该消息已不存在）')];
      // external-call 信封：与镜像区一致，展开时还原为外部卡片，而非普通代码块。
      const ext = ctx.parseExternalCall ? ctx.parseExternalCall(node) : null;
      if (ext) return [D.renderExternalCallMessage(ctx, node, ext)];
      const mKey = 'entry-' + e.key;
      // 只读模式：会话记录是留档展示，不提供执行 / 跳过 / 复制等交互，
      // 思考与堆栈直接展开，保证内容完整可见。
      return D.toArray(node.blocks).map((b, j) => D.renderBlock(ctx, b, j, mKey, { readonly: true }));
    }
    if (e.kind === 'external') {
      // 按卡片自身的 key 匹配：key 与消息的 'pid-id' 同构，不靠解析前缀反推 id。
      const c = (conv.externalCards || []).find((x) => x && D.externalCardKey(x) === e.key);
      if (!c) return [h('div', { class: 'empty' }, '（该外部卡片已不存在）')];
      return [D.renderExternalCard(ctx, c, { readonly: true })];
    }
    return [h('div', { class: 'empty' }, '（未知条目）')];
  };

  /**
   * 设置面板整体：System Prompt + 规则 + 工具 + 通用配置 + 历史卡片。
   * @param {Object} ctx Vue 实例
   * @returns {VNode|null} 设置面板节点；未打开时返回 null
   */
  D.renderSettings = function (ctx) {
    if (!ctx.settingsOpen) return null;
    // 已安装的自定义工具名集合：内置工具列表需排除它们，避免「上线后」与自定义列表重复出现两条同名
    const customNames = new Set(ctx.customTools.map((t) => t.name));
    return h('div', { class: 'settings' }, [
      h('div', { class: 'settings-bar' }, [
        h('span', '设置'),
        h('button', { class: 'close', title: '返回对话镜像', onClick: () => { ctx.settingsOpen = false; } }, '←')
      ]),
      h('div', { class: 'settings-body' }, [
        // 1) System Prompt：供复制粘贴到网页 AI 对话框
        D.renderSystemPromptBlock(ctx),
        // 2) 规则：用户自定义约定文件，AI 按需读取
        D.renderRulesBlock(ctx),
        // 2.5) 技能：工具的容器；一键控制其下全部工具的上 / 下线。
        //      技能内的工具同时出现在下方「工具」区块，两处开关同源。
        D.renderSkillsBlock(ctx),
        // 3) 工具（内置 + 自定义）：合并「支持的工具」与「后端工具上 / 下线」，
        //    开关写回后端，立即影响 System Prompt。默认折叠。
        h('div', { class: 'sp-block' }, [
          h('div', { class: 'card-head' }, [
            h('span', { title: '内置 + 自定义；点名称展开参数，开关控制是否上线到 System Prompt' }, '工具'),
            h('button', { onClick: () => { ctx.toolsOpen = !ctx.toolsOpen; } }, ctx.toolsOpen ? '▾' : '▸')
          ]),
          ctx.toolsOpen ? h('div', { class: 'tool-list' }, [
            ...ctx.tools.filter((t) => !customNames.has(t.name)).map((t) => D.renderUnifiedToolRow(ctx, t)),
            ...ctx.customTools.map((t) => D.renderCustomToolRow(ctx, t)),
            (ctx.tools.length === 0 && ctx.customTools.length === 0)
              ? h('div', { class: 'hint' }, '（未读取到工具列表，请先连接后端）')
              : null
          ]) : null
        ]),
        // 4) 远程桥接：QQ 凭证、推送开关、指令列表
        D.renderBridgeBlock(ctx),
        // 4.5) 通用配置：连接地址 / 端口 / 自动回传延迟
        D.renderGeneralSettings(ctx),
        // 5) 历史会话：列出全部会话，勾选后复制 JSON（对话记录 + 全部卡片）
        D.renderSessionBlock(ctx)
      ])
    ]);
  };

  /**
   * 外部卡片：与工具卡片同一套视觉与按钮能力（发送 / 重新发送、跳过、复制结果）。
   * 差异仅在语义：工具卡片把结果回传网页 AI，外部卡片把请求送进网页 AI，送完即结束。
   * @param {Object} ctx Vue 实例
   * @param {Object} c 外部卡片
   * @param {Object} [opts] 可选配置
   * @param {boolean} [opts.readonly] 只读模式：不渲染任何交互控件。
   *   用于「消息」这类只作留档展示的场景。
   * @returns {VNode} 卡片节点
   */
  D.renderExternalCard = function (ctx, c, opts) {
    const readonly = !!(opts && opts.readonly);
    const kids = [
      h('div', { class: 'code-head' }, [
        h('span', { class: 'toolname' }, '用户 · ' + (c.title || '')),
        h('span', { class: 'head-controls' }, [
          // 跳过的卡片状态独立显示：status 仍为 pending，直接用 statusText 会误显示「待执行」
          h('span', { class: 'badge ' + (c.skipped ? 'skipped' : (c.status || 'pending')) },
            c.skipped ? '已跳过' : ctx.statusText(c.status)),
          // 只读模式不提供「自动」开关与倒计时：没有可执行的动作，显示它们只会误导
          readonly ? null : D.renderAutoSwitch(ctx),
          (!readonly && c.countdown > 0) ? h('span', { class: 'countdown' }, '发送 ' + c.countdown + 's') : null
        ])
      ]),
      h('pre', { class: 'params-json' }, c.content)
    ];
    // 操作行仅在非只读模式渲染
    if (!readonly) {
      kids.push(h('div', { class: 'row' }, [
        h('button', {
          onClick: () => ctx.onExternalSendClick(c),
          disabled: c.status === 'running'
        }, c.executed ? '重新发送' : '发送到网页 AI'),
        // 跳过：取消该卡片的倒计时与自动发送，用户可自行决定不发送
        (!c.skipped && !c.executed) ? h('button', { class: 'secondary', onClick: () => ctx.skipExternalCard(c) }, '跳过') : null,
        c.skipped ? h('span', { class: 'hint' }, '已跳过') : null,
        (c.result != null) ? h('button', { onClick: () => ctx.copy(ctx.fmt(c.result)) }, '复制结果') : null
      ]));
    } else if (c.skipped) {
      // 只读模式没有按钮行，跳过状态改为独立提示，避免状态信息丢失
      kids.push(h('div', { class: 'hint' }, '已跳过'));
    }
    if (c.status === 'error') kids.push(h('pre', { class: 'error' }, c.error || ctx.fmt(c.result)));
    return h('div', { class: 'code-card', key: c.id }, kids);
  };
})();
