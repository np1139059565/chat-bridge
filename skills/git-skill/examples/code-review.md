## 场景二:代码走查与评论打分

适用于评审人查看变更、发表行内评论(草稿或直接发布),最后给出评分并发布评审意见。

> **命令执行约束(必读)**:本环境每条命令均为独立 shell,且非 `cmd /c` 前缀会触发初始化故障。因此 **所有 curl 命令必须用 `cmd /c "..."` 包裹**;URL 中的 `&` 必须转义为 `^&`。
> **严禁使用 `set` 环境变量方案**:`set` 命令具有延迟性,与后续命令用 `&`/`&&` 连接必然失败;且本环境每条命令都是独立 shell,`set` 的变量在下一条命令中必然丢失。因此一律采用**硬编码方案**——把完整 Cookie 字符串直接写进 `-H "Cookie: ..."`(详见 `auth-cookie.md`)。涉及到 URL 路径编码(如 `/`→`%2F`、空格→`%20`),请**预先手动编码后直接写进 URL**,不要依赖 `set` 在命令行内做字符串替换。

### 获取变更详情

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/detail?O=10004""
```

### 获取变更文件列表

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/revisions/%REVISION_ID%/files""
```
响应中顶层的键即为文件路径。

### 查看某个文件的 Diff

> URL 路径中的 `/` 需替换为 `%2F`,空格替换为 `%20`(应预先手动编码后写进 URL)。`context=ALL&intraline` 中的 `&` 必须写成 `^&`。

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/revisions/%REVISION_ID%/files/zxwinmo-b-net-closedloopoptimization-springboot%2Fsrc%2Fmain%2Fresources%2Fstatic%2Fcovoptsol%2Fsource%2FtaskParaFormNR.svd/diff?context=ALL^&intraline""
```
响应中的 `content` 数组包含了每行代码的差异信息。

### 发表行内评论(保存为草稿)

如果代码没有问题,也应评论一句"已走查"。

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X PUT "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/revisions/%REVISION_ID%/drafts" -H "Content-Type: application/json" -d "{\"path\":\"zxwinmo-b-net-closedloopoptimization-springboot/src/main/resources/static/covoptsol/source/taskParaFormNR.svd\",\"side\":\"REVISION\",\"parent\":0,\"message\":\"这里为什么不显示中文\",\"line\":349,\"range\":{\"start_line\":349,\"start_character\":46,\"end_line\":349,\"end_character\":82}}""
```

**参数说明**:
- `path`:文件路径(必须与 `/files` 返回的键完全一致)
- `side`:`REVISION` 表示当前修订版本,`PARENT` 表示父版本
- `line`:行号(从 1 开始)
- `range`:可选,指定选中字符范围(用于高亮)

### 查看已有的草稿评论

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/revisions/%REVISION_ID%/drafts""
```

### 发布评审(发布所有草稿 + 打分)

如果评论中有疑问则需要打 `-1`,如果没问题需要打 `+2`。

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X POST "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/revisions/%REVISION_ID%/review" -H "Content-Type: application/json" -d "{\"labels\":{\"Code-Review\":-1,\"Workflow\":-1},\"strict_labels\":true,\"drafts\":\"PUBLISH_ALL_REVISIONS\",\"message\":\"待回答完评论中的问题后再找我打分一次\"}""
```

**标签取值说明**(因项目配置可能不同):
- `Code-Review`:-2(拒绝合并)、-1(需修改)、0(无评分)、+1(可合并但需他人批准)、+2(批准)
- `Workflow`:-1(进行中)、0(待评审)、+1(已批准)
- `Verified`:-2(失败)、-1(有问题)、0(未验证)、+1(通过)、+2(已验证成功)

**`drafts` 选项**:
- `PUBLISH_ALL_REVISIONS`:发布所有修订版本的草稿
- `PUBLISH_CURRENT_REVISION`:仅发布当前修订版本的草稿
- `KEEP`:保留草稿不发布
