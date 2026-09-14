// 设置视图渲染
(function () {
  const D = window.AIDrawer;
  const { h } = D;

  // ctx 需包含：cfg, view, saveCfg, loadCfgFromBackend, cfgStatus, cfgStatusClass,
  //            pageUrls, setMappingPath, refreshUrls, copyPatch
  D.createSettingsRenderer = function (ctx) {
    function renderSettings() {
      const c = ctx.cfg.value;
      const urls = ctx.pageUrls.value || [];
      return h('div', { class: ['drawer', { open: true }] }, [
        h('div', { class: 'header' }, [
          h('span', '设置'),
          h('div', { class: 'status-bar' }, [
            h('button', { class: 'icon-btn', onClick: () => { ctx.view.value = 'chat'; } }, '返回'),
          ]),
        ]),

        h('div', { class: 'settings' }, [
          h('div', { class: 'section' }, [
            h('h3', '连接配置'),
            D.field('工具服务地址', D.textInput(c.backend_url, (v) => { c.backend_url = v; }, 'http://127.0.0.1:5000')),
            h('p', { class: 'hint-text' }, '工具服务由 chat-bridge 提供；调试能力以工具形式挂靠在其上。'),
          ]),

          h('div', { class: 'section' }, [
            h('h3', '采集配置'),
            D.checkBox(c.screenshot_enabled === true, (v) => { c.screenshot_enabled = v; }, '开启页面截图（默认关闭）'),
            h('p', { class: 'hint-text' }, '开启后，选中的元素卡片会附带当前可视区整屏截图（不做元素裁剪）。关闭时仍可主动请求截图。'),
            D.checkBox(c.style_list_enabled === true, (v) => { c.style_list_enabled = v; }, '采集样式列表（默认关闭）'),
            h('p', { class: 'hint-text' }, '开启后，元素卡片会附带 getComputedStyle 全量样式列表；关闭时仅采集选择器、DOM 源码等必要信息。'),
          ]),

          // URL 映射：自动列出当前页面所有 URL（含 iframe），用户只需为每个 URL 填本地路径。
          h('div', { class: 'section' }, [
            h('h3', 'URL 与本地工程映射'),
            h('p', { class: 'hint-text' }, '已自动列出当前页面所有 URL（去参数，含 iframe）。请为需要调试的 URL 填写本地工程路径；未填写映射的 URL 无法选择元素。'),
            h('div', { class: 'row' }, [
              h('button', { class: 'secondary', onClick: ctx.refreshUrls }, '刷新 URL 列表'),
            ]),
            urls.length
              ? urls.map((u) =>
                h('div', { class: 'list-item', key: 'u-' + u }, [
                  h('span', { class: 'map-url', title: u }, u),
                  h('input', {
                    value: (ctx.mappingFor(u) || {}).local_path || '',
                    placeholder: '本地工程路径，如 E:/projects/demo/src',
                    onInput: (e) => ctx.setMappingPath(u, e.target.value),
                  }),
                ])
              )
              : h('p', { class: 'hint-text' }, '（尚未获取到页面 URL，请打开抽屉后点击「刷新 URL 列表」）'),
          ]),

          // 补丁：解决 iframe 内页面无法被点选的问题
          h('div', { class: 'section' }, [
            h('h3', 'iframe 点选补丁'),
            h('p', { class: 'hint-text' }, '若页面元素位于 iframe 内，插件无法直接点选。点击下方按钮复制补丁代码，在对应 iframe 的控制台粘贴执行，即可打通点选。'),
            h('button', { class: 'secondary', onClick: ctx.copyPatch }, '补丁（复制代码）'),
          ]),

          h('div', { class: 'actions' }, [
            h('button', { onClick: ctx.saveCfg }, '保存'),
            h('button', { class: 'secondary', onClick: ctx.loadCfgFromBackend }, '重新载入'),
          ]),
          h('p', { class: ['status', ctx.cfgStatusClass.value] }, String(ctx.cfgStatus.value || '')),
        ]),
      ]);
    }

    return { renderSettings };
  };
})();
