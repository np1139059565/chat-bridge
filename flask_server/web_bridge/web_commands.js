/* ============================================================
 * 网页版机器人 —— 指令展开面板
 * 职责：点击指令按钮向上展开快捷键列表；点某条指令填入输入框等待发送。
 *
 * 指令数据从后端 /api/web/commands 取，新增内置指令时面板自动出现。
 * 首次展开时才懒加载，避免页面初始化多一次请求。
 *
 * 依赖：window.WebRender.renderCommandPanel（渲染分区网格）。
 * ============================================================ */
(function () {
  'use strict';

  var renderCommandPanel = window.WebRender.renderCommandPanel;

  // 面板相关 DOM 与状态
  var btnCmd = null;      // 展开/收起按钮
  var cmdPanel = null;    // 面板容器
  var cmdGrid = null;     // 指令网格
  var inputEl = null;     // 消息输入框（选中指令后填入）
  var loaded = false;     // 指令列表是否已拉取

  /** 拉取指令快捷键列表并渲染成分区内网格（内置/自定义，各按首字母排序）。 */
  function loadCommands() {
    fetch('/api/web/commands', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) return;
        var groups = data.groups || { builtin: data.commands || [], custom: [] };
        // 点选即填入输入框并留尾随空格：需要参数的指令便于补参数，其余发送时会被 trim。
        renderCommandPanel(cmdGrid, groups, function (c) {
          inputEl.value = c + ' ';
          inputEl.focus();
          cmdPanel.classList.remove('on');
        });
      })
      .catch(function () { /* 取不到指令时面板为空，不阻断聊天 */ });
  }

  /**
   * 初始化指令面板：注入 DOM 引用并挂上展开/收起交互。
   * @param {Object} opts { btnCmd, cmdPanel, cmdGrid, inputEl }
   */
  function init(opts) {
    opts = opts || {};
    btnCmd = opts.btnCmd;
    cmdPanel = opts.cmdPanel;
    cmdGrid = opts.cmdGrid;
    inputEl = opts.inputEl;
    if (!btnCmd || !cmdPanel || !cmdGrid || !inputEl) return;
    btnCmd.addEventListener('click', function (e) {
      e.preventDefault();
      // 首次展开时懒加载指令列表
      if (!loaded) { loadCommands(); loaded = true; }
      cmdPanel.classList.toggle('on');
    });
  }

  window.WebCommands = { init: init, loadCommands: loadCommands };
})();
