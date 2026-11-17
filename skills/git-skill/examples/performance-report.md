## 场景三:周期述职报告生成

基于 Gerrit 提交记录与本地 Git 真实改动,生成个人述职报告。

### 数据获取原则(优先级)

1. **Gerrit API 为主**:用 `auth-cookie.md` 的方式拉取本人当月的全部变更(见 `notes.md` 的"Gerrit 为主、本地 Git 为辅"分层规则)。Gerrit 覆盖已推送到服务器的所有变更,比本地 `git log` 更全更准。
2. **本地 Git 为辅(用于充实内容)**:当某条提交的 commit message 描述过简、无法体现业务价值时,**必须切换到本地代码库用 `git show` / `git log -p` 查看真实 diff**,把具体的业务逻辑、参数、配置、修复点写进报告,而不是只抄 commit message。

### 格式规范(强制)

**1. 严禁出现偏代码/统计类信息**
- **严禁**出现"插入 X 行 / 删除 X 行""新增 X 行""改动 X 文件"等代码行数、文件数统计。
- **严禁**出现与业务无关的纯代码细节(如某函数签名、变量定义、diff 片段)。
- 只描述**业务功能、业务价值、解决了什么业务问题**。
- 允许出现的适度技术信息:需求/故障单号(如 RNIA-xxxxxxx)、接口路径调整、配置参数名、字段名(这些用于说明业务语义,不算偏代码统计)。

**2. 描述过简必须用命令查真实改动补充**
- 若 commit message 只写"修复 bug""优化""调整"等笼统描述,**必须**执行本地 Git 命令(`git show <commit>` 或 `git log -p <commit>`)查看实际改动,提炼出具体的业务点(改了哪个流程、新增了什么能力、修复了什么场景)。
- 报告每条应写成"做了什么业务 + 带来什么业务效果",而非一句话带过。

### 报告结构(沿用既有模板)

- 按模块/分支分组(如:无线网络孪生 master 分支、优化方案孪生 ngi-master 分支、跨项目协作)。
- **当月无本人提交的库/分支,不单列章节**;若需说明,仅在协作段落用一句话说明"本月未在本项目提交代码,按需配合维护"。
- 跨项目协作段落用业务语言总结投入重点与价值,不堆砌行数或清单。

### 命令示例

**查看某条提交的真实改动(用于充实报告内容)**:
```cmd
cmd /c "cd /d e:\projects\zxwinmo\zxwinmo-b-net-closedloopoptimization-ngi && git show <commit> --stat"
cmd /c "cd /d e:\projects\zxwinmo\zxwinmo-b-net-closedloopoptimization-ngi && git show <commit>"
```

> 注意:本地 Git 命令是独立的 shell 调用,`cd /d` 与 `git` 写在同一 `cmd /c` 内即可;`git show` 用于看具体 diff 内容,`--stat` 仅看改动文件概况。这些不涉及 Cookie,无需走 Gerrit 的 `cmd /c` + 约束,但仍需 `cmd /c` 前缀以避免 shell 初始化故障。
