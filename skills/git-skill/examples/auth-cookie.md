## 认证与 Cookie 管理

所有 Gerrit API 调用均需使用 Cookie 认证。为安全与便捷,我们将 Cookie 存储在本地配置文件中,并由技能自动管理。

### 配置文件位置

```
git-skill/assets/config.json
```

> 注意:若目录不存在,请自行创建 `git-skill/assets/`。

### 配置文件格式

```json
{
  "cookie": "UCSSSOLanguage=zh_CN; iAuthLanguage_prod=zh_CN; ...; GerritAccount=xxx; XSRF_TOKEN=yyy; itHelpTip=true"
}
```

> 注意:Cookie 应为**完整 SSO Cookie 字符串**,其中需包含 `GerritAccount` 字段。仅写 `GerritAccount=xxx; GerritSession=yyy` 往往不足,需整串 SSO Cookie 才能通过 Gerrit 认证。

### 初始化与自动检查流程

在执行任何 Gerrit API 请求前,应执行以下步骤。

> **【运行环境约束 - 必读】**
> 命令行在"每条命令都是独立 shell"的自动化环境中执行,且**非 `cmd /c` 前缀的命令会触发 shell 初始化故障**(`无法启动此 shell。初始化过程中出现故障`)。
> **`set` 命令具有延迟性,与任何后续命令用 `&`/`&&` 连接必然失败**:在 `cmd /c "set X=... & curl ... %X%"` 中,`%X%` 是在整条命令"解析期"展开的,而 `set` 赋值发生在"执行期",因此 curl 拿到的是展开时的旧值(空值),必然 401。**严禁**用 `&`/`&&` 把 `set` 与任何其他命令连写。
> 更关键的是:本环境每条命令都是**全新独立 shell**,前一条 `cmd /c` 里 `set` 的变量在下一条 `cmd /c` 中**必定丢失**。因此:
> - **环境变量方案(`set` + `%COOKIE%` 引用)在本环境根本不可行,一律不要使用。**
> - **唯一可靠做法:硬编码方案**——把完整 Cookie 字符串直接写进每条 curl 的 `-H "Cookie: ..."`。
> - 命令内 URL 的 `&` 必须转义为 `^&`,否则会被当作命令分隔符截断。

#### 1. 检查配置文件是否存在

#### 2. 读取 Cookie(仅读取,不设置环境变量)

该步骤与命令行无关,直接使用 read_file 工具读取 `git-skill/assets/config.json` 即可。
> **重要**:本环境每条命令都是独立 shell,`set` 的环境变量跨命令必然丢失;且 `set` 与后续命令用 `&` 连接会因延迟性必然失败。因此**不要尝试 `set COOKIE` 再用 `%COOKIE%` 引用**。Cookie 直接用于下方第 3/4 节的硬编码 curl 中。


#### 3. 验证 Cookie 有效性(最小可用验证,硬编码方式)

用最小查询验证即可,避免复杂 URL 拼接出错。**直接把 Cookie 写进 `-H`**:

```cmd
cmd /c "curl -s -o nul -w "%{http_code}" --noproxy "*" -H "Cookie: 完整的Cookie字符串" "https://gerrit.zte.com.cn/changes/?q=is:open+owner:self^&limit=1""
```

- 若返回 `200`,说明有效。
- 若返回 `401`,表示 Cookie 已失效,走第 5 节重新获取。
- 若返回 `000`/`Unauthorized`,先在 curl 中确认已加 `--noproxy "*"`,再判断是否为 Cookie 失效。

#### 4. Cookie 失效处理流程

当 Cookie 失效(401)时,**通过弹框方式获取用户输入**。具体步骤:

1. **调用弹框工具**:
   - 标题:`"Gerrit Cookie 更新"`
   - 提示文本:`"当前 Gerrit Cookie 已失效,请从浏览器开发者工具(F12 → Network → 任意请求 → Request Headers → Cookie)中复制完整的 Cookie 字符串,粘贴到下方输入框中:"`
   - 等待用户输入。

2. **获取用户输入**:
   - 若用户确认输入(`status == "success"`),将 `value` 中的内容写入 `git-skill/assets/config.json`(覆盖原有内容),后续 curl 直接引用此新 Cookie 。
   - 若用户取消输入(`status == "cancelled"`),则终止流程并提示用户"无法继续执行 Gerrit 操作,请准备好 Cookie 后重试"。

3. **重新验证**:
   - 写入配置文件后,再次执行步骤 3/4 验证 Cookie 有效性,直到验证通过。

### 在 curl 命令中使用 Cookie

**本环境唯一可靠方式:硬编码**。把完整 Cookie 字符串直接写进每条 curl 的 `-H "Cookie: ..."`,**不要**使用 `set COOKIE` + `%COOKIE%` 引用(独立 shell 下变量丢失,且 `set` 与 `curl` 用 `&` 连接会因延迟性必然失败)。

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" "https://gerrit.zte.com.cn/changes/?q=is:open+owner:self^&limit=1""
```

> URL 中的 `&` 必须写成 `^&`(在 `cmd /c "..."` 内);不得使用未转义的 `&`,否则命令会被截断。
> **严禁**出现 `set X=... & curl ... %X%` 这种写法。
