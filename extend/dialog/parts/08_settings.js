// 模块：extend/dialog/parts/08_settings.js
// 用途：设置面板渲染（一）：System Prompt 块、内置 / 自定义工具行、自定义工具安装块。
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
      h('div', { class: 'install-actions' }, [
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
                // '读取优先级',
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
          : h('div', { class: 'empty' }, '（暂无规则，可新建）')
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
      h('div', { class: 'hint' }, '开启自动后：只对最新一张待执行卡片倒计时自动执行，执行完再倒计时自动发送到网页 AI（两者共用此时长）；积压的旧卡片需手动执行，卡片上可单独跳过。'),
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
})();
