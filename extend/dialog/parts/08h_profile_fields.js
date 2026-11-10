// 模块：extend/dialog/parts/08h_profile_fields.js
// 用途：站点档案的字段元表——每个已知字段的分组、展示名、测试方式与默认值。
//
// 拆出原因：08g_site_profiles.js 承载渲染与交互逻辑，字段表随站点类型增加不断变长，
// 2026-11-09 因新增 atBottomCheck 使该文件达到 457 行、超出仓库 450 行上限。
// 元表是纯数据，与渲染逻辑无耦合，单独成文件后两边都可独立演进。
//
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）。须在 08g 之前加载。
//
// 字段 kind 含义：
//   click    = 可点击元素（真点击一次，与 QQ 指令同链路）
//   selector = 结构选择器（定位测试：查命中数并高亮首个，不点击）
//   list     = 选择器清单（多行编辑，逐行定位）
//   regex    = 会话 id 正则（对当前 URL 试匹配）
//   hosts    = 域名清单（多行编辑，无测试）
//   bool     = 布尔开关（复选框；defaultOn 为真时缺省即勾选）
//   无 kind  = 纯文本或状态信号，无测试按钮
(function () {
  'use strict';
  const D = window.AIMirrorDialog;

  // 字段元表：已知字段的分组、展示名与测试方式。自定义字段（不在表内）按
  // 「自定义字段」分组渲染，支持定位与点击两种测试。
  //   kind 含义：click=可点击元素（真点击一次，与指令同链路）；selector=结构
  //   选择器（定位测试：查命中数并高亮首个，不点击）；list=选择器清单（多行
  //   编辑，逐行定位）；regex=会话 id 正则（对当前 URL 试匹配）；hosts=域名
  //   清单（多行编辑，无测试）；无 kind=纯文本或布尔信号，无测试按钮。
  D.PROFILE_FIELD_GROUPS = [
    { id: 'meta', title: '元信息' },
    { id: 'structure', title: '消息结构（采集与解析）' },
    { id: 'history', title: '会话与历史' },
    { id: 'input', title: '输入与发送' },
    { id: 'actions', title: '按钮与恢复' },
    { id: 'state', title: '生成状态信号' }
  ];

  D.PROFILE_FIELD_META = {
    label: { group: 'meta', label: '站点显示名', hint: '设置页与日志中的名称' },
    hosts: { group: 'meta', label: '域名清单', kind: 'hosts', hint: '每行一个，按网址自动识别站点' },
    split: { group: 'meta', label: '问答拆分模式', hint: '一个条目内同时含提问与回答时开启' },
    container: { group: 'structure', label: '对话区容器', kind: 'selector' },
    reverseItems: { group: 'structure', label: '消息倒序排列', kind: 'bool', hint: '列表 DOM 为「新→旧」时开启（如 flex-col-reverse）' },
    item: { group: 'structure', label: '消息条目', kind: 'selector' },
    userItem: { group: 'structure', label: '用户提问容器', kind: 'selector' },
    userContent: { group: 'structure', label: '提问正文', kind: 'selector' },
    userName: { group: 'structure', label: '用户名', kind: 'selector' },
    assistantItem: { group: 'structure', label: 'AI 回答容器', kind: 'selector' },
    assistantMark: { group: 'structure', label: 'AI 回答标记', kind: 'selector' },
    assistantContent: { group: 'structure', label: '回答正文', kind: 'selector' },
    answerContent: { group: 'structure', label: '回答正文（单块）', kind: 'selector' },
    answerWrap: { group: 'structure', label: '回答正文块', kind: 'selector', hint: '回答拆成多个块时全部收集' },
    thinking: { group: 'structure', label: '思考区', kind: 'selector' },
    thinkingArea: { group: 'structure', label: '思考区容器', kind: 'selector' },
    convIdUrl: { group: 'history', label: '会话 id 正则', kind: 'regex', hint: '从当前 URL 提取会话 id' },
    historyContainer: { group: 'history', label: '会话列表容器', kind: 'selector' },
    historyItem: { group: 'history', label: '会话列表条目', kind: 'selector' },
    historySelectedMark: { group: 'history', label: '选中项标记', kind: 'selector' },
    inputSelector: { group: 'input', label: '输入框', kind: 'selector' },
    sendButton: { group: 'input', label: '发送按钮', kind: 'selector', hint: '仅定位测试（避免误发送）' },
    sendButtonDisabledMark: { group: 'input', label: '发送禁用类名', hint: '按钮未就绪时带的类名' },
    newConversation: { group: 'actions', label: '开启新对话按钮', kind: 'click', hint: '对应 /new 指令' },
    regenerateExpr: { group: 'actions', label: '重新生成表达式', kind: 'click', hint: '风控恢复用；可为裸选择器或完整 JS 表达式' },
    retrySendExpr: { group: 'actions', label: '重发按钮表达式', kind: 'click', hint: '限流恢复用' },
    scrollToBottomButton: { group: 'actions', label: '滚动到底部按钮', kind: 'list', hint: '按钮存在=不在底部' },
    atBottomCheck: { group: 'actions', label: '启用底部判定', kind: 'bool', defaultOn: true, hint: '关闭后不看是否在底部，自动执行不再受其限制' },
    generatingSelectors: { group: 'state', label: '生成中标记', kind: 'list', hint: '命中任一即视为 AI 正在输出' },
    generatingRequireEmptyInput: { group: 'state', label: '生成中须输入框为空', kind: 'bool', defaultOn: true, hint: '开启后仅当输入框为空才算生成中，避免多行输入被误判' },
    sendButtonStopMark: { group: 'state', label: '停止图标签名', hint: 'SVG path 片段，无测试' }
  };
})();
