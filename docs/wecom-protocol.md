# 企业微信智能机器人长连接协议

本文记录本工程与企业微信智能机器人通道交互时**实际确认**的协议细节，
以及尚未确认、需要真机验证的部分。

## 证据等级

| 标记 | 含义 |
|---|---|
| 已验证 | 真机日志或平台返回值直接确认 |
| 推断 | 依据报错信息或命名惯例推测，未经确认 |
| 已否证 | 实测失败，不可再采用 |

新增字段前先查本文；实测确认后把「推断」改为「已验证」。

---

## 一、连接与订阅

| 项 | 内容 | 等级 |
|---|---|---|
| 连接地址 | `wss://openws.work.weixin.qq.com` | 已验证 |
| 订阅命令 | `aibot_subscribe`，body 带 `bot_id` 与 `secret` | 已验证 |
| 订阅成功应答 | `{"headers":{"req_id":...},"errcode":0,"errmsg":"ok"}`，顶层无 `cmd` | 已验证 |
| 心跳 | `ping`，间隔 30 秒 | 已验证 |
| 连接约束 | 同一机器人同一时刻只允许一条长连接，新连接踢旧连接 | 已验证 |
| 重连间隔 | 5 秒 | 已验证 |

订阅成功与否必须靠 `headers.req_id` 比对判断：成功应答顶层没有 `cmd` 字段，
按 `cmd` 判断会恒为假，表现为「订阅成功却显示未连接」。

---

## 二、接收消息

| 项 | 内容 | 等级 |
|---|---|---|
| 消息回调 | `aibot_msg_callback` | 已验证 |
| 发送者位置 | `body.from.userid`，不在顶层 | 已验证 |
| 单聊会话 id | 无 `chatid` 字段，用 `from.userid` 作会话标识 | 已验证 |
| 群聊会话 id | `body.chatid` | 推断 |
| 文本正文 | `body.text.content` | 已验证 |
| 图片字段 | `body.image = {url, aeskey}` | 已验证 |
| 文件字段 | `body.file = {url, aeskey, ...}` | 推断（与图片同构） |
| 语音字段 | `body.voice` | 推断 |

### 媒体解密

| 项 | 内容 | 等级 |
|---|---|---|
| 密钥编码 | URL-safe base64，**省略末尾 padding** | 已验证 |
| 密钥长度 | 32 字节对应 43 字符（标准编码为 44 字符含 `=`） | 已验证 |
| 加密算法 | AES-256-CBC | 已验证 |
| IV | 密钥前 16 字节 | 已验证 |
| 填充 | PKCS7 | 已验证 |

密钥解码必须先用 `-`→`+`、`_`→`/` 还原字符集，再补齐 `=` 至 4 的倍数，
否则 `b64decode` 抛异常、解密被静默跳过，密文原样落盘成 `.bin`。

---

## 三、发送消息

| 项 | 内容 | 等级 |
|---|---|---|
| 被动回复 | `aibot_respond_msg`，`headers.req_id` 必须透传回调带来的值 | 已验证 |
| 主动推送 | `aibot_send_msg` | 已验证 |
| 文本消息体 | `body.msgtype=markdown`，正文在 `body.markdown.content` | 已验证 |
| 流式回复体 | `body.msgtype=stream`，`body.stream.finish=True` | 已验证 |
| 媒体消息项 | `body.stream.msg_item` 数组 | 已验证 |
| 图片项 | `{msgtype:"image", image:{base64, md5}}`，base64 与 md5 均针对**原始字节** | 已验证 |
| 语音项 | `{msgtype:"voice", voice:{base64, md5}}` | 推断（与图片同构） |
| 文件项 | `{msgtype:"file", file:{media_id, file_name}}` | 推断 |

**回复凭证特性**：一个 `req_id` 只能回复一条消息，用后即失效。
多条媒体需要多个凭证，或改走主动推送。

---

## 四、媒体上传（当前失败中）

大文件走三步上传：`aibot_upload_media_init` → `aibot_upload_media_chunk` →
`aibot_upload_media_finish`，完成后拿 `media_id` 发文件消息项。

### 已否证

| 字段写法 | 结果 |
|---|---|
| init body 用 `media_type` | 平台报错：`missing field 'body.type'. invalid Request Parameter, errcode 40058` |

平台错误原文：

```
missing field `body.type`. invalid Request Parameter,
hint: [1793626002286443577948970], from ip: 27.38.239.145,
more info at https://open.work.weixin.qq.com/devtool/query?e=40058
```

### 待验证

| 项 | 当前代码写法 | 状态 |
|---|---|---|
| 媒体类型字段名 | `media_type` | 已否证，平台要求 `type` |
| 文件名 | `file_name` | 待确认 |
| 文件大小 | `file_size` | 待确认 |
| 总分片数 | 未发送 | 待确认是否需要 |
| 文件 md5 | 未发送 | 待确认是否需要 |
| 分片内容字段 | `chunk_data` | 待确认 |
| init 应答中 `upload_id` 位置 | `body.upload_id` | 待确认 |
| finish 应答中 `media_id` 位置 | `body.media_id` | 待确认 |

修正方式：按平台报错逐个补齐缺失字段。平台会在 `hint` 里指明下一个缺失字段，
照此迭代即可，不必猜。

---

## 五、排查入口

平台报错里的 `e=40058` 这类错误码，可查：

```
https://open.work.weixin.qq.com/devtool/query?e=<errcode>
```

日志位置：

- 桥接日志：`flask_server/data/logs/bridge-YYYY-MM-DD.log`
- 应用日志：`flask_server/data/logs/app-YYYY-MM-DD.log`（媒体模块走这条）

媒体模块（`wecom_media.py`）用 `app_log`，网关与路由用 `bridge_log`，
两者写不同文件，排查时两边都要看。
