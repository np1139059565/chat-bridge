---
name: icenter_export
description: iCenter 知识库读写工具。导出方向：把页面导出为完整 Markdown，支持单页、批量、引用宏（Reference Macro）表格还原与图片落盘。写入方向：在指定空间与父页面下新建页面、修改已有页面标题与正文。当用户需要下载 iCenter 页面、保存为 Markdown、导出知识库分支、还原丢失的表格，或向 iCenter 新建/更新文档时使用。
---

# icenter_export

将 iCenter 页面导出为完整 Markdown。

## 何时使用

- 下载 iCenter 单个页面为 Markdown。
- 批量下载多个页面或整个知识库分支。
- 导出的文档表格丢失、内容不全，需要还原。

## 目录结构

技能自包含，所有文件都在本技能目录内，换机器或改目录后仍可直接运行。

```
icenter_export/
├── SKILL.md                      本说明
├── tool.json                     工具声明
├── requirements.txt              Python 依赖
├── references/
│   ├── restore-tables.md         表格还原方法说明
│   └── api-reference.md          iCenter 1.0 API 参考
└── scripts/
    ├── handler.py                下载器主程序
    ├── inline_reference_macros.py 引用宏内联 + 转 Markdown
    ├── config.json               认证配置
    └── config.json.example       配置模板
```

## 前置条件

认证信息在 `scripts/config.json`，字段含 `emp_no` 与 `password`。工具用 1.0 API（工号 + 密码换取 Token），无需 auth_value。

首次使用先安装依赖：

```cmd
cd <本技能目录>\scripts
pip install -r ..\requirements.txt
```

## 执行环境约束

用 cmd 调用 handler.py，但 **`--output` 路径不要加引号**。cmd 会把引号当成路径字符，报 `[WinError 123] 文件名、目录名或卷标语法不正确`。路径含空格时改用短路径或先 `cd` 到目标目录。

## 基本下载

```cmd
cd <本技能目录>\scripts
python handler.py download "<URL>" --output E:\目标目录 --depth 0
```

`--depth 0` 只下当前页；`--depth 2` 尝试递归子页。

## 关键限制：递归抓取依赖子页面宏

handler 的 `crawl_recursive` **只通过 `ChildrenDisplayMacro`（子页面宏）提取子链接**。若页面用正文普通链接列出子页，递归会静默停在第一层——日志只出现 `[Depth 1]`，且只保存一个文件。

绕过方法：把子页 URL 写入列表文件，用 batch 下载。

```cmd
cd <本技能目录>\scripts
python handler.py batch urls.txt --output E:\目标目录 --depth 1
```

## 关键限制：引用宏导致表格丢失

iCenter 页面的表格常以 **`macro-key="Reference"` 引用宏**嵌入，宏体只有空行，真实数据在**被引用页面的某个 block** 里。handler 的转换器只处理 `ChildrenDisplayMacro`，对 `Reference` 宏不处理，导出后正文只剩链接文字，表格全部消失。

还原方法见 [references/restore-tables.md](references/restore-tables.md)，或直接运行：

```cmd
cd <本技能目录>\scripts
python inline_reference_macros.py --url "<URL>" --output <输出文件.md>
```

该脚本递归内联所有 Reference 宏，把被引用页面的内容取回原位，再转 Markdown。脚本默认从自身所在目录加载 `handler.py` 与 `config.json`，无需额外传参。

## 新建与编辑页面

技能除导出外，还能在知识库中写入内容。`handler.py` 的 `create` 与 `edit` 子命令即对应这两件事。

```cmd
cd <本技能目录>\scripts
python handler.py create --title "页面标题" --content "<h1>正文</h1>" --space-id <空间ID> --parent-id <父页面ID> --version 1.0
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--title` | 是 | 页面标题 |
| `--content` | 是 | 正文 HTML 片段 |
| `--space-id` | 是 | URL 中 `/space/` 与 `/wiki/` 之间那段 |
| `--parent-id` | 是 | URL 中 `/page/` 与 `/view` 之间那段 |
| `--version` | 否 | `1.0` 或 `2.0`，省略时按父页面自动探测 |
| `--summary` | 否 | 页面摘要 |

创建成功返回 `content_id` 与完整访问地址。省略 `--version` 时，工具以父页面为锚点探测该空间走 1.0 还是 2.0 接口，并打印探测结果；显式传入 `--version` 则以传入值为准。

编辑已有页面：

```cmd
python handler.py edit "<页面URL>" --title "新标题" --content "<div>新内容</div>"
```

1.0 走 `PUT /content/{id}`，需回填完整页面字段（currentVersion、secretLevel、parentPath 等）；2.0 走 `POST /content/{id}/updateContent`，只需 `docType`、`title`、`text`。

### 写入后正文会被编辑器重排

提交的 `<h1>`、`<table>` 会被 iCenter 前端组件改写成 `<div ze-root="zeRoot">` 结构，并加 `tag-start`、`block-id` 等内联属性，字符数显著膨胀。校验写入结果时不要比对字符数，改为检查结构标签（`table`/`tr`/`td`/`th`）与关键正文片段是否仍在。

### 子页面列表接口的权限差异

`GET /content/children?spaceId=&contentId=` 在部分空间返回 `0006 此操作未授权`。此时改用 `GET /content/subtree/?spaceId=&contentId=`，它返回同一批子页的扁平列表（含 `id` 与 `title`），无需额外权限。

## 附件链接

iCenter 正文里的附件以 `<a href="udm-doc-<id>" fileName="x.zip" fileSize="58234">` 形式内联，页面 `attachments` 字段为空。直接转 Markdown 会得到 `[x.zip](udm-doc-<id>)` 这种无法点击的相对链接。

`fix_attachment_links` 会在转换前把所有 `href` 以 `udm-doc-` 开头的链接补成完整地址：

```
https://i.zte.com.cn/index/ispace/udm-doc-<id>
```

该地址是 iCenter 前端的下载路由，用户在已登录的浏览器里点开即可下载，无需额外令牌。导出 Markdown 里的附件因此可直接点击。

### 上传附件：当前不可行

新建或编辑页面时通过 API 内联附件，需要调用 UDM 文档服务的 7 个接口（getLibInfo → createAppFolder → fileStatus → sendData → finish → saveFiles → saveAuth），并按顺序串起 `libraryId`、`folderId`、`fileMd5`、`groupKey`。

网关要求 `X-Access-Key`、`X-Timestamp`、`X-Verify-Code`、`appcode` 四个头，其中 `X-Verify-Code` 是前端私有签名算法，无法由时间戳与密钥直接推出（已用 152 种常见拼接与哈希组合穷举验证，均不命中）。因此脚本不支持自动上传附件；需要附件时请在 iCenter 页面编辑器里手动上传。

## 图片处理（默认开启）

导出时图片会被自动下载到输出文件同级的 `images/` 目录，正文改写为 `![](images/xxx.png)` 相对路径，并在图下附一行 `<!-- 源地址: ... -->` 注释保留原始链接。

图片地址为 `icenterapi.zte.com.cn` 直链，**无需登录态即可访问**，脚本复用已有 session 下载。

| 参数 | 作用 |
| --- | --- |
| `--image-dir <目录>` | 指定图片落盘目录，默认 `<输出目录>/images` |
| `--no-images` | 跳过下载，保留原始在线地址 |

### 三个必须绕开的坑

转换库 markdownify 会在以下位置**静默丢弃图片**，脚本已内置规避，改动时勿删：

1. **表头/标题内的图片**：`<h2>标题<img></h2>` 转换后只剩标题文字。处理方式：转换前把图片移到标题之后。
2. **表格单元格内的图片**：`<td><img></td>` 转换后单元格为空。处理方式：转换前插入 `【见图N】` 占位并把图片移到表格之后。
3. **HTML 注释**：markdownify 不输出注释，源地址注释会全部消失。处理方式：转换时记录 `本地路径 → 源地址` 映射，转换完成后按映射回填注释。

### 验收检查

导出后核对三个数字：正文图片引用数 = 源地址注释数 = 实际图片数（去重前）。出现差额通常意味着上述某个坑被踩中。

## 标题重复说明

handler 的 `get_html_content` 会加一次 `# 标题`，`save_markdown` 又加一次，导致导出文件开头有两行相同标题。用还原脚本重新生成可消除。
