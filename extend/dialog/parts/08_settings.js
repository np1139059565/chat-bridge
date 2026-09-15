// 模块：extend/dialog/parts/08_settings.js
// 用途：设置面板相关渲染：System Prompt 块、工具列表行、自定义工具行、
//       自定义工具安装块、规则块、通用配置与历史卡片管理、设置面板整体。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 说明：这些渲染函数原先定义在 D.render 内部，依赖 Vue 实例上下文（this）。
// 拆分后统一改为 D.renderXxx(ctx, ...) 形式，ctx 即 Vue 实例，语义与原实现一致。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * System Prompt 区块：只提供复制（设置面板本身已由 ⚙ 开合）。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderSystemPromptBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', 'System Prompt（请复制粘贴到网页 AI 对话框）'),
        h('button', { onClick: () => ctx.copy(ctx.systemPrompt) }, '复制')
      ]),
      h('pre', { class: 'sysprompt' }, ctx.systemPrompt)
    ]);
  };

  /**
   * 内置工具行：合并「支持的工具」与「后端工具上 / 下线」为同一区块。
   * @param {Object} ctx Vue 实例
   * @param {Object} tool 工具定义
   * @returns {VNode} 列表项节点
   */
  D.renderUnifiedToolRow = function (ctx, tool) {
    const name = tool.name;
    const on = !ctx.configTools[name] || ctx.configTools[name].enabled !== false;
    return h('li', { class: 'tool-row', key: 'b:' + name }, [
      h('div', { class: 'tree-node', onClick: () => ctx.toggleTool(name) }, [
        h('span', { class: 'caret' }, ctx.expanded[name] ? '▾' : '▸'),
        h('b', name),
        h('span', { class: 'desc' }, tool.description)
      ]),
      h('div', { class: 'tool-btns' }, [
        h('button', {
          class: 'switch ' + (on ? 'on' : 'off'),
          onClick: () => ctx.setToolEnabled(name, !on)
        }, on ? '已上线' : '已下线')
      ]),
      ctx.expanded[name] ? h('div', { class: 'tree-detail' }, [
        h('p', tool.description),
        h('table', { class: 'params' }, [
          h('thead', h('tr', [h('th', '参数'), h('th', '类型'), h('th', '必填'), h('th', '说明')])),
          h('tbody', (tool.parameters || []).map((p) => h('tr', { key: p.name }, [
            h('td', h('code', p.name)),
            h('td', p.type),
            h('td', p.required ? '是' : '否'),
            h('td', p.description)
          ])))
        ]),
        name === 'run_command' ? ctx.renderRunCommandLanguages(tool) : null,
        h('pre', { class: 'usage' }, ctx.usageOf(tool))
      ]) : null
    ]);
  };

  /**
   * 自定义工具行：含编辑 / 删除 / 上下线，以及内联编辑区。
   * @param {Object} ctx Vue 实例
   * @param {Object} t 自定义工具
   * @returns {VNode} 列表项节点
   */
  D.renderCustomToolRow = function (ctx, t) {
    const name = t.name;
    return h('li', { class: 'tool-row custom', key: 'c:' + name }, [
      h('div', { class: 'tree-node', onClick: () => ctx.toggleCustom(name) }, [
        h('span', { class: 'caret' }, ctx.customExpanded[name] ? '▾' : '▸'),
        h('b', name),
        h('span', { class: 'desc' }, '[自定义] ' + t.description)
      ]),
      h('div', { class: 'tool-btns' }, [
        h('div', { class: 'tool-actions' }, [
          h('span', { class: 'badge custom' }, 'skill: ' + t.skill_name),
          h('button', { onClick: () => ctx.editCustom(name) }, '编辑'),
          h('button', { class: 'danger', onClick: () => ctx.removeCustom(name) }, '删除')
        ]),
        h('button', {
          class: 'switch ' + (t.enabled ? 'on' : 'off'),
          onClick: () => ctx.setCustomEnabled(name, !t.enabled)
        }, t.enabled ? '已上线' : '已下线')
      ]),
      ctx.customExpanded[name] ? h('div', { class: 'tree-detail' }, [
        h('p', t.description),
        h('table', { class: 'params' }, [
          h('thead', h('tr', [h('th', '参数'), h('th', '类型'), h('th', '必填'), h('th', '说明')])),
          h('tbody', (t.parameters || []).map((p) => h('tr', { key: p.name }, [
            h('td', h('code', p.name)),
            h('td', p.type),
            h('td', p.required ? '是' : '否'),
            h('td', p.description)
          ])))
        ]),
        h('p', { class: 'desc' }, '脚本：' + t.script + '　解释器：' + t.interpreter + '　参数风格：' + t.arg_style),
        ctx.customEditing[name]
          ? h('div', { class: 'custom-edit' }, [
            h('textarea', {
              value: ctx.customEdit[name] || '',
              onInput: (e) => { ctx.customEdit[name] = e.target.value; }
            }),
            h('div', { class: 'row' }, [
              h('button', { onClick: () => ctx.saveCustom(name) }, '保存'),
              h('button', { onClick: () => { ctx.customEditing[name] = false; } }, '取消')
            ])
          ])
          : null
      ]) : null
    ]);
  };

  /**
   * 自定义工具安装块：选择 / 扫描 skill 目录并安装其中的工具。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderCustomInstallBlock = function (ctx) {
    return h('div', { class: 'custom-install' }, [
      h('div', { class: 'card-head' }, [h('span', '安装自定义工具（来自标准 skill 的 tool.json）')]),
      h('label', ['skill 目录（选包含 skill 的父目录）', h('div', { class: 'dir-row' }, [
        h('input', {
          type: 'text', value: ctx.skillScanDir,
          onInput: (e) => { ctx.skillScanDir = e.target.value; }
        })
      ])]),
      h('div', [
        h('button', { onClick: () => ctx.scanSkills() }, '扫描可安装'),
        h('button', { onClick: () => ctx.scanDefaults() }, '用默认目录扫描')
      ]),
      ctx.scanResults.length
        ? h('div', { class: 'scan-results' },
          ctx.scanResults.map((skill) => h('div', { class: 'scan-skill' }, [
            h('div', skill.skill_name + (skill.error ? '（解析失败：' + skill.error + '）' : '')),
            ...(skill.tools || []).map((ts) => h('div', { class: 'scan-tool' }, [
              h('span', ts.name + ' — ' + ts.description),
              h('button', {
                disabled: ts.installed,
                onClick: () => ctx.installSkill(skill.skill_dir, ts.name)
              }, ts.installed ? '已安装' : '安装')
            ]))
          ]))
        )
        : null
    ]);
  };

  /**
   * 规则区块：列出规则、设置读取优先级、增删改。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderRulesBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', '规则（' + ctx.rules.length + '）（AI 通过 list_rules / read_rule 按需读取）'),
        h('button', { onClick: () => { ctx.rulesOpen = !ctx.rulesOpen; } }, ctx.rulesOpen ? '▾' : '▸')
      ]),
      ctx.rulesDir ? h('div', { class: 'hint' }, '规则目录：' + ctx.rulesDir) : null,
      ctx.rulesOpen ? h('div', { class: 'rule-list' }, [
        h('div', { class: 'rule-new' }, [
          h('input', {
            type: 'text', value: ctx.newRuleName, placeholder: '新规则名（字母/数字/下划线/连字符）',
            onInput: (e) => { ctx.newRuleName = e.target.value; }
          }),
          h('button', { onClick: () => ctx.createRule() }, '新建')
        ]),
        ctx.rules.length
          ? ctx.rules.map((r) => h('div', { class: 'rule-item', key: r.name }, [
            h('div', { class: 'tree-node', onClick: () => ctx.toggleRule(r.name) }, [
              h('span', { class: 'caret' }, ctx.rulesExpanded[r.name] ? '▾' : '▸'),
              h('b', r.name),
              h('span', { class: 'desc' }, r.summary)
            ]),
            h('div', { class: 'tool-btns' }, [
              h('label', { class: 'rule-priority' }, [
                '读取优先级',
                h('select', {
                  value: r.priority || 'on-demand',
                  onChange: (e) => ctx.setRulePriority(r.name, e.target.value)
                }, ctx.rulePriorities.map((p) => h('option', { value: p.value }, p.label)))
              ]),
              h('button', { onClick: () => ctx.editRule(r.name) }, '编辑'),
              h('button', { class: 'danger', onClick: () => ctx.removeRule(r.name) }, '删除')
            ]),
            ctx.rulesExpanded[r.name] ? h('div', { class: 'tree-detail' }, [
              ctx.rulesEditing[r.name]
                ? h('div', { class: 'custom-edit' }, [
                  h('textarea', {
                    value: ctx.rulesEdit[r.name] || '',
                    onInput: (e) => { ctx.rulesEdit[r.name] = e.target.value; }
                  }),
                  h('div', { class: 'row' }, [
                    h('button', { onClick: () => ctx.saveRule(r.name) }, '保存'),
                    h('button', { onClick: () => { ctx.rulesEditing[r.name] = false; } }, '取消')
                  ])
                ])
                : h('pre', { class: 'rule-view' }, ctx.rulesEdit[r.name] || r.summary)
            ]) : null
          ]))
          : h('div', { class: 'empty' }, '（暂无规则，可新建；首次启动会自动生成 self-healing 规则）')
      ]) : null
    ]);
  };

  /**
   * 通用配置区块：自动回传延迟、连接地址、端口、体积上限。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderGeneralSettings = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [h('span', '通用配置')]),
      // 自动延迟配置 + 全局自动开关（右侧按钮直接切换）
      h('label', ['自动回传延迟(秒)', h('div', { class: 'inline-row' }, [
        h('input', {
          type: 'number', min: '1', step: '1',
          value: ctx.autoSendDelay / 1000,
          onInput: (e) => { const v = parseInt(e.target.value, 10); ctx.autoSendDelay = (v > 0 ? v : 3) * 1000; }
        }),
        h('button', {
          class: 'switch ' + (ctx.autoSendEnabled ? 'on' : 'off'),
          title: '切换全局自动：开启后卡片自动倒计时执行并回传',
          onClick: () => ctx.setAutoSendEnabled(!ctx.autoSendEnabled)
        }, ctx.autoSendEnabled ? '自动：开' : '自动：关')
      ])]),
      h('div', { class: 'hint' }, '开启自动后：卡片会倒计时自动执行，执行完再倒计时自动发送到网页 AI（两者共用此时长）；卡片上可单独跳过。'),
      (!ctx.flaskOk) ? h('div', { class: 'flask-warn' }, '⚠ 无法连接 Flask 服务（' + ctx.flaskError + '），当前使用内置工具目录。') : null,
      h('br'),
      // Flask 连接地址：由后端 config.yaml 下发，仅会话内使用，不持久化到浏览器
      h('label', ['Flask 连接地址（来自后端 config.yaml）',
        h('div', { class: 'ro' }, ctx.config.flaskUrl)]),
      h('div', [
        h('button', { onClick: () => ctx.initBackend() }, '重新连接后端'),
        h('span', { class: 'hint' }, '改了 config.yaml 端口后点此重新发现')
      ]),
      // 端口不一致告警：配置端口已改但服务仍在旧端口运行（尚未重启）
      ctx.portMismatch
        ? h('div', { class: 'flask-warn' },
          '⚠ 配置端口 ' + ctx.config.flaskPort + ' 与服务实际端口不一致：服务仍在旧端口运行。'
          + '请重启 Flask 服务监听新端口，然后点「重新连接后端」。插件当前仍连接旧端口，未使用未生效的新配置。')
        : null,
      // 端口配置：写入后端 config.yaml，重启 Flask 后生效
      h('label', ['Flask 端口（重启服务生效）', h('input', {
        type: 'number', value: ctx.config.flaskPort,
        onInput: (e) => { ctx.config.flaskPort = e.target.value; }
      })]),
      h('div', [
        h('button', { onClick: () => ctx.savePort() }, '保存端口'),
        h('span', { class: 'hint' }, '端口修改需重启 Flask 服务才能监听新端口')
      ]),
      // 工具结果 JSON 体积上限：写入后端 config.yaml，即时生效
      h('label', ['工具结果体积上限(字符)', h('input', {
        type: 'number', min: '1', step: '1',
        value: ctx.maxJsonChars,
        onInput: (e) => { const v = parseInt(e.target.value, 10); ctx.maxJsonChars = v > 0 ? v : 100000; }
      })]),
      h('div', [
        h('button', { onClick: () => ctx.saveMaxJsonChars() }, '保存上限'),
        h('span', { class: 'hint' }, 'search_content / read_file 等结果超过此字符数会报错，提示 AI 缩小范围')
      ])
    ]);
  };

  /**
   * 历史卡片管理区块：按创建时间倒序展示，可单删 / 清空。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderHistoryBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', '历史卡片管理（' + ctx.sortedHistoryCards.length + '）'),
        h('button', { onClick: () => ctx.clearAllCards() }, '清空')
      ]),
      ctx.sortedHistoryCards.length
        ? h('div', { class: 'history-list' },
          ctx.sortedHistoryCards.map((c) => {
            const time = c.createdAt ? new Date(c.createdAt).toLocaleString() : '';
            // 外部卡片与工具/代码卡片字段不同：按 _kind 分别生成可读标签
            const label = c._kind === 'external'
              ? ('外部卡片 · ' + (c.title || c.type || ''))
              : (c.isTool ? ('工具 · ' + (c.tool || '')) : ('代码 · ' + (c.lang || '')));
            return h('div', { class: 'history-item', key: c.id }, [
              h('span', { class: 'h-time' }, time),
              h('span', { class: 'h-label' }, label),
              h('span', { class: 'badge ' + c.status }, ctx.statusText(c.status)),
              h('button', { class: 'h-del', onClick: () => ctx.removeHistoryCard(c) }, '删除')
            ]);
          }))
        : h('div', { class: 'empty' }, '（暂无历史卡片）')
    ]);
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
        h('button', { class: 'close', onClick: () => { ctx.settingsOpen = false; } }, '✕')
      ]),
      h('div', { class: 'settings-body' }, [
        // 1) System Prompt：供复制粘贴到网页 AI 对话框
        D.renderSystemPromptBlock(ctx),
        // 2) 规则：用户自定义约定文件，AI 按需读取
        D.renderRulesBlock(ctx),
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
          ]) : null,
          D.renderCustomInstallBlock(ctx)
        ]),
        // 4) 通用配置：连接地址 / 端口 / 自动回传延迟
        D.renderGeneralSettings(ctx),
        // 5) 历史卡片管理：严格按创建时间倒序展示，可单删 / 清空
        D.renderHistoryBlock(ctx)
      ])
    ]);
  };

  /**
   * 外部卡片：与工具卡片同一套视觉与状态机，仅以徽标区分来源。
   * @param {Object} ctx Vue 实例
   * @param {Object} c 外部卡片
   * @returns {VNode} 卡片节点
   */
  D.renderExternalCard = function (ctx, c) {
    const kids = [
      h('div', { class: 'code-head' }, [
        h('span', { class: 'toolname' }, '外部卡片 · ' + (c.title || '')),
        h('span', { class: 'head-controls' }, [
          h('span', { class: 'badge ' + (c.status || 'pending') }, ctx.statusText(c.status)),
          h('span', { class: 'badge external' }, 'external'),
          D.renderAutoSwitch(ctx),
          c.countdown > 0 ? h('span', { class: 'countdown' }, '发送 ' + c.countdown + 's') : null
        ])
      ]),
      h('pre', { class: 'params-json' }, c.content)
    ];
    kids.push(h('div', { class: 'row' }, [
      h('button', {
        onClick: () => ctx.onExternalSendClick(c),
        disabled: c.status === 'running'
      }, c.executed ? '重新发送' : '发送到网页 AI'),
      (c.status === 'done') ? h('button', { onClick: () => ctx.copy(ctx.fmt(c.result)) }, '复制结果') : null
    ]));
    if (c.status === 'done') kids.push(h('pre', { class: 'result' }, ctx.fmt(c.result)));
    if (c.status === 'error') kids.push(h('pre', { class: 'error' }, c.error || ctx.fmt(c.result)));
    return h('div', { class: 'code-card external-card', key: c.id }, kids);
  };
})();
