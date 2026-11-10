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
      h('div', { class: 'tool-btns' +
         (D.publicFieldClass ? D.publicFieldClass(ctx, 'tools', name, 'enabled', on) : '') }, [
         D.publicRestoreBtn ? D.publicRestoreBtn(ctx, 'tools', name, 'enabled', on) : null,
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
        // 该工具自己的可调配置，跟随工具渲染；无配置声明时不占位
        D.renderToolConfig(ctx, name),
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
    return h('li', { class: 'tool-row custom', key: 'c:' + name, 'data-cfg-block': 'custom_tools' }, [
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
          'data-cfg-skip': '1',
          onInput: (e) => { ctx.skillScanDir = e.target.value; }
        })
      ])]),
      h('div', { class: 'install-actions' }, [
        h('button', { onClick: () => ctx.scanSkills() }, '扫描可安装'),
        h('button', { onClick: () => ctx.scanDefaults() }, '用默认目录扫描')
      ]),
      // 扫描结果：可折叠 + 可清除。
      // 折叠解决「扫完一次就一直占着抽屉高度」，清除解决「结果堆着不走」。
      ctx.scanResults.length
        ? h('div', { class: 'scan-results' }, [
          h('div', { class: 'scan-head' }, [
            h('span', {
              class: 'scan-toggle',
              onClick: () => { ctx.scanOpen = !ctx.scanOpen; }
            }, (ctx.scanOpen ? '▾ ' : '▸ ') + '扫描结果（' + ctx.scanResults.length + ' 个 skill）'),
            h('button', {
              class: 'scan-clear',
              title: '清空扫描结果，不影响已安装的工具',
              onClick: () => { ctx.scanResults = []; ctx.scanOpen = false; }
            }, '清除')
          ]),
          ctx.scanOpen
            ? ctx.scanResults.map((skill) => h('div', { class: 'scan-skill' }, [
              h('div', skill.skill_name + (skill.error ? '（解析失败：' + skill.error + '）' : '')),
              // 只渲染未安装工具：后端已过滤，此处兜住插件先更新、服务未重启的版本错配
              ...(skill.tools || []).filter((ts) => !ts.installed).map((ts) => h('div', { class: 'scan-tool' }, [
                h('span', ts.name + ' — ' + ts.description),
                h('button', {
                  onClick: () => ctx.installSkill(skill.skill_dir, ts.name)
                }, '安装')
              ]))
            ]))
            : null
        ])
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
    return h('div', { class: 'sp-block', 'data-cfg-block': 'general' }, [
      h('div', { class: 'card-head' }, [
        h('span', '通用配置'),
         D.renderConfigBadge ? D.renderConfigBadge(ctx, 'general') : null,
        h('button', { onClick: () => { ctx.generalOpen = !ctx.generalOpen; } },
          ctx.generalOpen ? '▾' : '▸')
      ]),
            ctx.generalOpen ? h('div', [renderGeneralBody(ctx)]) : null
    ]);
  };

  /**
   * 通用配置的内容主体。
   *
   * 抽成独立函数是为了让 renderGeneralSettings 只管折叠判断，
   * 内容再多也不影响折叠逻辑的可读性。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 内容节点
   */
  /**
 * 切换风控自动恢复开关并持久化。
 *
 * 抽成独立函数的原因：写入要走带回调的 chrome.storage 形式（只有回调里才能读到
 * runtime.lastError），内联到渲染函数里会把行数撑破上限。
 *
 * @param {Object} ctx Vue 实例
 */
function toggleRiskRecover(ctx) {
  const next = !ctx.riskRecoverEnabled;
  ctx.riskRecoverEnabled = next;
  // 诊断：写入路径此前完全静默，失败了也看不出
  try {
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
      console.error('[风控恢复] chrome.storage 不可用，开关无法持久化');
      return;
    }
    chrome.storage.local.set({ aiMirrorRiskRecover: next }, function () {
      if (chrome.runtime.lastError) {
        console.error('[风控恢复] 写入失败：' + chrome.runtime.lastError.message);
      } else {
        console.log('[风控恢复] 写入成功：' + next);
      }
    });
  } catch (e) {
    console.error('[风控恢复] 写入异常：' + (e && e.message ? e.message : e));
  }
}

/**
 * 切换风控自动恢复开关并持久化。
 *
 * 抽成独立函数的原因：写入要走带回调的 chrome.storage 形式（只有回调里才能读到
 * runtime.lastError），内联到渲染函数里会把行数撑破上限。
 *
 * @param {Object} ctx Vue 实例
 */
function toggleRiskRecover(ctx) {
  const next = !ctx.riskRecoverEnabled;
  ctx.riskRecoverEnabled = next;
  // 诊断：写入路径此前完全静默，失败了也看不出
  try {
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
      console.error('[风控恢复] chrome.storage 不可用，开关无法持久化');
      return;
    }
    chrome.storage.local.set({ aiMirrorRiskRecover: next }, function () {
      if (chrome.runtime.lastError) {
        console.error('[风控恢复] 写入失败：' + chrome.runtime.lastError.message);
      } else {
        console.log('[风控恢复] 写入成功：' + next);
      }
    });
  } catch (e) {
    console.error('[风控恢复] 写入异常：' + (e && e.message ? e.message : e));
  }
}

function renderGeneralBody(ctx) {
    return h('div', [
      // 自动延迟配置 + 全局自动开关（右侧按钮直接切换）
      h('label', ['自动回传延迟(秒)', h('div', { class: 'inline-row' }, [
        h('input', {
          type: 'number', min: '1', step: '1',
          value: ctx.autoSendDelay / 1000,
          'data-cfg-skip': '1',
          onInput: (e) => { const v = parseInt(e.target.value, 10); ctx.autoSendDelay = (v > 0 ? v : 3) * 1000; }
        }),
        h('button', {
          class: 'switch ' + (ctx.autoSendEnabled ? 'on' : 'off'),
          title: '切换全局自动：开启后卡片自动倒计时执行并回传',
          onClick: () => ctx.setAutoSendEnabled(!ctx.autoSendEnabled)
        }, ctx.autoSendEnabled ? '自动：开' : '自动：关')
      ])]),
      h('div', { class: 'hint' }, '开启自动后：只对最新一张待执行卡片倒计时自动执行，执行完再倒计时自动发送到网页 AI（两者共用此时长）；积压的旧卡片需手动执行，卡片上可单独跳过。'),
      // 风控自动恢复：默认关闭。开启后检测到「已停止」或输出为空，
      // 等 20 秒自动点一次重新生成。属侵入性动作，故默认不启用。
      h('label', ['风控自动恢复', h('div', { class: 'inline-row' }, [
        h('button', {
          class: 'switch ' + (ctx.riskRecoverEnabled ? 'on' : 'off'),
          title: '开启后：检测到网页 AI 因风控停止生成，等待 20 秒自动点一次「重新生成」',
          onClick: () => toggleRiskRecover(ctx)
        }, ctx.riskRecoverEnabled ? '已开启' : '已关闭')
      ])]),
      h('div', { class: 'hint' }, '开启后：检测到 AI 因风控停止（页面显示「已停止」或输出为空），等 20 秒自动点一次重新生成。仅在你停留在对话底部时生效——往上翻看历史时不打扰，避免替你重跑主动停止的回复。'),
      (!ctx.flaskOk) ? h('div', { class: 'flask-warn' }, '⚠ 无法连接 Flask 服务（' + ctx.flaskError + '），当前使用内置工具目录。') : null,
      h('br'),
      // 工具服务地址：唯一输入框，形如 http://127.0.0.1:5000。
      // 保存时从中解析端口，以滚动重启切到新端口。
      // 输入框绑草稿变量而非连接地址——输入过程中不改实际连接，
      // 只有点「保存并重启」才把草稿里的端口拿去滚动重启；
      // 草稿为空时回显当前实际地址，保证首次打开能看到现状。
      h('label', ['工具服务地址', h('input', {
        type: 'text', class: 'bridge-sel-input',
        value: ctx.flaskUrlDraft || ctx.config.flaskUrl,
        placeholder: 'http://127.0.0.1:端口',
        // 切换端口期间禁用输入，禁止中途再改
        disabled: ctx.portSwitching,
        onInput: (e) => { ctx.flaskUrlDraft = e.target.value; }
      })]),
      h('div', [
        h('button', {
          disabled: ctx.portSwitching,
          onClick: () => ctx.savePort()
        }, ctx.portSwitching ? '切换中…' : '保存并重启'),
        h('span', { class: 'hint' }, '端口不一致才重启：先起新服务、探通后才切换并退出旧服务；超时自动还原')
      ]),
      // 工具结果 JSON 体积上限：写入后端 runtime.yaml，即时生效
      h('label', ['工具结果体积上限(字符)', h('input', {
        type: 'number', min: '1', step: '1',
        value: ctx.maxJsonChars,
        'data-cfg-skip': '1',
           class: 'tc-num' + (D.publicFieldClass
             ? D.publicFieldClass(ctx, 'limits', '', 'max_json_chars', ctx.maxJsonChars) : ''),
        onInput: (e) => { const v = parseInt(e.target.value, 10); ctx.maxJsonChars = v > 0 ? v : 100000; }
      })]),
      h('div', [
        D.publicRestoreBtn
           ? D.publicRestoreBtn(ctx, 'limits', '', 'max_json_chars', ctx.maxJsonChars) : null,
         h('button', { onClick: () => ctx.saveMaxJsonChars() }, '保存上限'),
        h('span', { class: 'hint' }, 'search_content / read_file 等结果超过此字符数会报错，提示 AI 缩小范围')
      ]),
      h('br'),
      // 文件访问权限：控制文件类工具可访问的路径范围
      h('br'),
      // 系统资源上限：各目录与队列保留数，独立于工具
      h('div', { class: 'hint' }, '资源保留上限'),
      D.renderSystemConfig(ctx)
    ]);
  }
})();
