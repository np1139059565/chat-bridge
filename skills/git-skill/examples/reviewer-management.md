## 场景一:评审人管理

以下操作使用 `curl` 直接调用 Gerrit REST API。  
**前置条件**:已按 `auth-cookie.md` 完成 Cookie 配置与验证。

> **命令执行约束(必读)**:本环境每条命令均为独立 shell,且非 `cmd /c` 前缀会触发初始化故障。因此 **所有 curl 命令必须用 `cmd /c "..."` 包裹**;URL 中的 `&` 必须转义为 `^&`。
> **严禁使用 `set` 环境变量方案**:`set` 命令具有延迟性,与后续命令用 `&`/`&&` 连接必然失败;且本环境每条命令都是独立 shell,`set` 的变量在下一条命令中必然丢失。因此一律采用**硬编码方案**——把完整 Cookie 字符串直接写进 `-H "Cookie: ..."`(详见 `auth-cookie.md`)。

> **关于响应格式**:Gerrit API 的所有响应均以 `)]}'\n` 这 5 个字符作为前缀,实际 JSON 内容从第 6 个字符开始。建议把响应写入文件后用 read_file 读取,并**忽略开头 `)]}'` 那一行**,从下一行起的 JSON 才是有效内容;切勿把带前缀的内容直接当 JSON 解析。

### 获取我的变更列表

**当用户要求添加评审人、走查代码或对某个变更进行操作时,必须先调用此接口获取所有已推送到 Gerrit 的变更(以 Gerrit API 为准,严禁用本地 Git 替代以获取变更列表)。**

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/?q=is:open+owner:self^&q=is:open+reviewer:self+-owner:self+-star:ignore^&q=is:closed+(owner:self+OR+reviewer:self)+-age:4w+limit:10^&O=881""
```

**参数说明**:
- `q=is:open+owner:self`:查询当前用户拥有的未合并变更
- `q=is:open+reviewer:self+-owner:self+-star:ignore`:查询当前用户作为评审人的未合并变更
- `q=is:closed+(owner:self+OR+reviewer:self)+-age:4w+limit:10`:查询最近4周内当前用户拥有或评审的已合并变更
- `O=881`:返回额外的变更信息

**响应示例**(去除前缀后):
```json
[
  [
    {
      "_number": 25832328,
      "subject": "RDC:RNIA-1518084 解决优化方案孪生...",
      "status": "NEW",
      "owner": {
        "name": "林常怡 6396000838",
        "username": "6396000838"
      }
    }
  ]
]
```

### 搜索评审人(Suggest Reviewers)

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/suggest_reviewers?q=%KEYWORD%^&n=20""
```

**参数说明**:
- `CHANGE_NUMBER`:变更号纯数字(如 `25832328`)
- `q`:搜索关键词(支持中文拼音、用户名、姓名),必须是完整姓名,不能只搜姓"林"
- `n`:返回最大结果数

**响应示例**(去除前缀后):
```json
[
  {
    "account": {
      "_account_id": 5160462,
      "name": "林常怡 6396000838",
      "email": "lin.changyi@zte.com.cn",
      "username": "6396000838"
    },
    "count": 1
  }
]
```
> 注:若未找到匹配用户,返回空数组 `[]`,说明该用户没有权限,可以换其他用户试试。

### 添加评审人

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X POST "https://gerrit.zte.com.cn/a/changes/%CHANGE_NUMBER%/reviewers" -H "Content-Type: application/json" -d "{\"reviewer\": \"%REVIEWER%\"}""
```

**参数说明**:
- `CHANGE_NUMBER`:变更号纯数字
- `REVIEWER`:评审人,可使用用户名、邮箱或账号ID(如 `林常怡`)
- Cookie 直接硬编码在 `-H "Cookie: ..."` 中,**不要**使用 `set` 环境变量 + `%COOKIE%` 引用。

**响应示例**:
```json
{
  "input": "林常怡",
  "reviewers": [
    {
      "approvals": {
        "Code-Review": " 0",
        "Workflow": " 0"
      },
      "_account_id": 5160462,
      "name": "林常怡 6396000838",
      "email": "lin.changyi@zte.com.cn",
      "username": "6396000838"
    }
  ]
}
```

> **认证要求**:添加评审人时, REST API 端点 URL 必须以 `/a/` 前缀进行身份验证,否则将返回 `Invalid authentication method` 错误。例如:`https://gerrit.zte.com.cn/a/changes/...` 而非 `https://gerrit.zte.com.cn/changes/...`。

### 智能补充评审人

在提交代码后,应确保变更的评审人列表满足要求:**至少包含一位主评审人 + 至少一位对应领域的评审人**(总人数 ≥ 2)。

> **何时执行**:建议在 `git push` 成功后立即执行智能补充逻辑,确保评审人及时到位。

#### 评审人列表定义

| 类型 | 人员 | 备注 |
|------|------|------|
| **主评审人** | 祝晶、朱世军 | 至少添加其中一位 |
| **后端领域评审人** | 牛赫、马鸣、张晓亮、刘占鹏 | 根据代码变更领域选择 |
| **测试领域评审人** | 黄靖邦 | 若变更涉及测试用例或配置 |
| **前端领域评审人** | 温达喜、叶维发 | 若变更涉及前端代码 |

#### 补充逻辑流程

1. **获取当前变更的评审人列表**

```cmd
cmd /c "curl --noproxy "*" -H "Cookie: 完整的Cookie字符串" -X GET "https://gerrit.zte.com.cn/changes/%CHANGE_NUMBER%/detail""
```
响应中的 `reviewers.REVIEWER` 数组包含了当前所有评审人信息,每个成员有 `username` 和 `name` 字段。

2. **确定本次变更的领域**  
   从返回的评审人列表中提取 `username` 或 `name`,判断是否包含"祝晶"或"朱世军"。若缺失,则自动添加其中一位(建议默认添加"祝晶")。

3. **检查领域评审人是否缺失**  
   根据领域判断对应人员是否已在评审人列表中。若缺失,则从该领域列表中任选一位添加。

4. **执行补充添加**
   对每一位缺失的评审人调用添加评审人 API(参见"添加评审人"章节)。

5. 必须在"评审人列表"中添加评审人,严禁添加其他无关人员。
