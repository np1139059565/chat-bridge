# iCenter API 参考手册

## 目录

1. [认证方式](#认证方式)
2. [API基础信息](#api基础信息)
3. [1.0版本API](#10版本api)
4. [2.0版本API](#20版本api)
5. [响应格式](#响应格式)
6. [错误码](#错误码)

---

## 认证方式

### 方式一：Token认证（适用于1.0 API）

通过用户名密码获取访问令牌。

**认证接口：**
```
POST http://uac.zte.com.cn/uaccommauth/auth/comm/verify.serv
```

**请求头：**
```json
{
    "Content-Type": "application/json"
}
```

**请求体：**
```json
{
    "account": "工号",
    "passWord": "密码",
    "loginClientIp": "本机IP",
    "loginSystemCode": "Portal",
    "originSystemCode": "",
    "other": {
        "networkArea": "1",
        "networkAccessType": "1"
    },
    "verifyCode": "MD5(工号+密码+IP+loginsyscode+originsyscode)"
}
```

**响应：**
```json
{
    "other": {
        "token": "访问令牌"
    }
}
```

### 方式二：AuthValue认证（适用于2.0 API）

使用预先分配的认证密钥。

**请求头：**
```json
{
    "X-Emp-No": "工号",
    "X-Auth-Value": "认证密钥",
    "X-Lang-Id": "zh_CN"
}
```

---

## API基础信息

### Base URLs

| 版本 | Base URL |
|------|----------|
| 1.0 | `https://icenterapi.zte.com.cn/zte-rd-icenter-contents` |
| 2.0 | `https://icenterapi.zte.com.cn/zte-rdcloud-space-content` |

### 通用请求头

```json
{
    "Accept": "application/json, text/plain",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://i.zte.com.cn",
    "Referer": "https://i.zte.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Tenant-Id": "ZTE"
}
```

### 通用查询参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `t` | 时间戳(毫秒) | `t=1719900000000` |
| `spaceId` | 空间ID | `spaceId=xxx` |
| `environmentType` | 环境类型 | `environmentType=browser` |
| `system` | 系统标识 | `system=space-1921407097` |

---

## 1.0版本API

### 获取页面内容

```
GET /content/{contentId}?spaceId={spaceId}
```

**认证：** Token

**响应示例：**
```json
{
    "bo": {
        "id": "页面ID",
        "title": "页面标题",
        "contentBody": "<html>HTML内容</html>",
        "summary": "摘要",
        "currentVersion": "版本号",
        "spaceName": "空间名称",
        "secretLevel": 0,
        "tags": ["标签1"],
        "attachments": [
            {
                "fileName": "文件名",
                "fileType": "image/png",
                "fileUrl": "https://..."
            }
        ]
    },
    "code": {
        "code": "0000",
        "message": "成功"
    }
}
```

### 创建页面

```
POST /content/?spaceId={spaceId}&parentId={parentId}&noRedirect=true
```

**认证：** Token

**请求体：**
```json
{
    "title": "页面标题",
    "contentBody": "<html>HTML内容</html>",
    "summary": "摘要",
    "spaceId": "空间ID",
    "parentId": "父页面ID",
    "tags": ["标签"],
    "secretLevel": 0,
    "isLatestVersion": true
}
```

### 编辑页面

```
PUT /content/{contentId}?spaceId={spaceId}&noRedirect=true
```

**认证：** Token

**请求体：** 与创建相同，需要包含完整的页面数据

### 获取子页面列表

```
GET /content/children?spaceId={spaceId}&contentId={contentId}
```

**认证：** Token

**响应：**
```json
{
    "bo": [
        {
            "id": "子页面ID",
            "title": "子页面标题"
        }
    ]
}
```

### 获取页面子树

```
GET /content/subtree/?spaceId={spaceId}&contentId={contentId}
```

**认证：** Token

**响应：**
```json
{
    "bo": [
        {
            "id": "页面ID",
            "title": "页面标题",
            "children": []
        }
    ]
}
```

---

## 2.0版本API

### 获取页面内容

```
GET /content/{contentId}?spaceId={spaceId}
```

**认证：** AuthValue

**响应格式：** 与1.0相同

### 创建页面

```
POST /content/?spaceId={spaceId}&parentId={parentId}&noRedirect=true
```

**认证：** AuthValue

**请求体：** 与1.0相同

### 编辑页面

```
POST /content/{contentId}/updateContent?spaceId={spaceId}&noRedirect=true
```

**认证：** AuthValue

**请求体：**
```json
{
    "docType": "HTML",
    "title": "新标题",
    "text": "<html>新内容</html>"
}
```

### 获取子页面

```
GET /content/children?spaceId={spaceId}&contentId={contentId}
```

**认证：** AuthValue

**响应格式：** 与1.0相同

---

## 响应格式

### 成功响应

```json
{
    "bo": { ... },
    "code": {
        "code": "0000",
        "message": "成功"
    }
}
```

### 错误响应

```json
{
    "code": {
        "code": "错误码",
        "message": "错误信息"
    }
}
```

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| `0000` | 成功 |
| `0006` | 文档不存在 |
| `0010` | 权限不足 |
| `0100` | 参数错误 |
| `0200` | 服务器内部错误 |

---

## URL格式解析

iCenter页面URL格式：
```
https://i.zte.com.cn/index/ispace/#/space/{spaceId}/wiki/page/{contentId}/view
```

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `spaceId` | 空间ID | `7fa2aa4a98a04128923584592fedfcaa` |
| `contentId` | 页面/文档ID | `46cee6eebdef46a68a30c5bdc5633612` |

### 共享文档URL
```
https://i.zte.com.cn/index/ispace/#/shared/{spaceId}/wiki/page/{contentId}/view
```
