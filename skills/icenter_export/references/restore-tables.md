## 引用宏（Reference Macro）还原方法

### 问题表现

iCenter 页面在浏览器里能看到表格，但导出为 Markdown 后表格消失，正文只剩一行链接文字。

### 根因

页面表格常以引用宏形式嵌入，特征如下：

```html
<div macro-key="Reference" m-doc-id="144f531e..." m-block-id="bKZxOIrq"
     m-type="table&simpletable" m-text="【表/Table】">
  <div class="ze-macro-body"><p><br /></p></div>
</div>
```

- `macro-key="Reference"` 表明这是引用宏。
- 宏体 `<p><br /></p>` 是空的——真实数据不在本页。
- `m-doc-id` 指向被引用的文档，`m-block-id` 指向该文档内的块。

handler 的转换器只处理 `ChildrenDisplayMacro`，遇到 Reference 宏不处理，于是正文只剩链接文字。

### 还原步骤

1. 读主页 `contentBody`，找所有 `macro-key="Reference"` 的 div。
2. 对每个宏，用 `m-doc-id` 拉取被引用页面的 `contentBody`。
3. 在被引用页面里按 `m-block-id` 定位目标块。
4. 把目标块内容内联回原位（引用目标若是标题，连标题带其下内容一并取）。
5. 递归处理内联内容里可能嵌套的引用宏。
6. 用 markdownify 转 Markdown。

直接用 `scripts/inline_reference_macros.py` 完成上述全部步骤。

### 两个易错点

**属性名大小写**：BeautifulSoup 会把 HTML 属性名转成小写，`anchor-yWdz8FSF` 变成 `anchor-ywdz8fsf`。匹配时必须小写比较，否则精确匹配永远失败。

**锚点不是 block-id**：目标块有时不是以 `block-id` 标注，而是把锚点挂在标题元素上，形如 `anchor-yWdz8FSF="true"` 或 `reference-yWdz8FSF="true"`。匹配规则要同时覆盖 `block-id`、`anchor-*`、`reference-*` 三种。

### 已知局限

Markdown 表格语法不支持合并单元格（rowspan/colspan）。原表有合并格时，转换后这些位置会留空，表格骨架与其余数据正确，但跨行合并处会缺列。这是 Markdown 的固有局限，原始 HTML 里数据完整。需要完整保留合并信息时，应同时保留原始 HTML 存档。
