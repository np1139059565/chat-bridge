# 多通道重构进度（3c）

## 目标

把 QQ / 微信 / 企业微信三条通道的重复实现收敛到公共层，
每个通道只保留「连接与协议差异」的少量适配代码。

## 现状盘点

`remote_bridge/` 共 41 个文件、约 1 万行。三通道各有一套实现：

| 职责 | QQ | 微信 | 企业微信 |
|---|---|---|---|
| 客户端 | qq_client.py | weixin_client.py | wecom_client.py |
| 网关 | qq_gateway.py | weixin_gateway.py | wecom_gateway.py |
| 推送分发 | message_router.py | weixin_router.py | wecom_router.py |
| 协议 | qq_event_parse.py | weixin_proto.py | wecom_proto.py |
| 媒体 | qq_media.py | （复用 weixin_client） | wecom_media.py |
| 文件 | qq_files.py | — | wecom_media_collect.py |

已经存在的公共模块：

- `message_parse.py` —— 消息分类与块转文本
- `outbound.py` —— 出站正文组装（QQ 与网页共用）
- `message_flow.py` —— 消息流
- `voice_*` —— 语音合成与识别

## 重复点清单

1. **最近用户兜底**：`note_incoming` / `_last_user` / `_last_openid`，各通道各写一份，都要持久化。
2. **已推集合去重**：各通道用不同命名空间，但「读集合 → 差集 → 写回」的流程完全一样。
3. **推送串行锁**：QQ 按会话分锁，微信用全局 RLock，企微无锁。
4. **配额窗口**：QQ 是 60 分钟被动回复窗口，微信是 24 小时 10 条，企微无限制。
5. **媒体上传**：各通道自己的上传格式与重试。

## 目标架构

```
remote_bridge/
├── channel/                 # 公共层（阶段一已完成）
│   ├── adapter.py           # 通道适配器协议
│   ├── push_pipeline.py     # 推送管线：去重 → 组装 → 发送 → 记账
│   ├── dedupe.py            # 已推集合（按通道命名空间）
│   ├── quota.py             # 配额窗口（可配置策略）
│   └── target.py            # 最近用户兜底与持久化
├── adapters/                # 各通道适配器（阶段二起逐步落地）
│   ├── qq.py                # 连接 + 发送 + 协议
│   ├── weixin.py
│   └── wecom.py
└── （其余既有模块保持不动，逐步改为调用公共层）
```

媒体公共流程（上传、转码、重试）在阶段五抽出，作为公共层的独立模块。

适配器协议（草案）：

```python
class ChannelAdapter:
    name = "qq"                        # 通道标识，用于去重命名空间
    def send_text(self, target, text, markdown=False): ...
    def send_image(self, target, path_or_bytes): ...
    def send_file(self, target, path): ...
    def quota_policy(self): ...        # 返回配额策略对象
```

## 阶段任务

### 阶段一：公共层骨架

- [ ] 新建 `channel/` 包
- [ ] `target.py`：最近用户兜底 + 持久化（QQ / 微信各一份状态，接口统一）
- [ ] `dedupe.py`：已推集合，按通道命名空间隔离
- [ ] `quota.py`：配额策略（窗口时长、条数上限、是否可主动推送）
- [ ] `adapter.py`：适配器协议定义
- [ ] `push_pipeline.py`：统一推送管线

### 阶段二：QQ 接入公共层

- [ ] `message_router.py` 改为调用 `push_pipeline`
- [ ] 被动回复窗口保留为 QQ 专属（`window_store`）
- [ ] 回归：单条推送、批量推送、窗口续期、去重

### 阶段三：微信接入公共层

- [x] 新建微信通道适配器：合并推送、剔除工具调用、标识格式校验
- [x] 配额语义修正为「用户发消息时重置池子」，并加 `reset()`
- [x] 端到端验证：合并推送、工具调用剔除、去重、配额重置
- [ ] `weixin_router.py` 切换为调用 `push_pipeline`（旧实现仍在用）
- [ ] 回归：配额提示、来源过滤、真实账号收消息

### 阶段四：企业微信接入公共层

- [x] 新建企业微信适配器：合并文本、媒体单独发送、回复凭证消费
- [x] 适配器协议补 `push_media` 钩子，管线在文本送达后调用
- [x] 端到端验证：合并推送、去重
- [x] 已记录代价：管线是「文本先发」，媒体首条常降级为主动推送
- [ ] `wecom_router.py` 切换为调用 `push_pipeline`（旧实现仍在用）
- [ ] 回归：真实账号收图片 / 文件 / 语音

### 阶段五：媒体与文件

- [ ] 抽公共媒体流程（上传、转码、重试）为公共层的独立模块
- [ ] 三个通道的媒体实现改为薄适配

### 阶段六：清理

- [ ] 删除已被替代的重复实现
- [ ] 更新架构文档
- [ ] 删除本进度文档

## 验收标准

- 三条通道的推送行为与改造前一致（逐项回归）
- `remote_bridge/` 文件数下降
- 新增一个通道只需实现适配器协议，不改公共层

## 风险

- 推送链路涉及真实账号，回归须谨慎，优先在测试环境验证
- 配额与窗口语义各通道不同，抽象时不能抹平差异，只能把差异收敛到策略对象
