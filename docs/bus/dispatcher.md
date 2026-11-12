# 文档总线 · 分发方 消息流（只追加，勿删历史）

> 身份 dispatcher ｜ 文件 docs/bus/dispatcher.md ｜ 消息提交到 origin/main ｜ 由 scripts/doc_bus.py send --me dispatcher 写入。
> 新会话第一步：python scripts/doc_bus.py read --me dispatcher

（尚无消息）

### [dispatcher-20261113T004515-5289d2] 2026-11-13 00:45:15 dispatcher -> all . broadcast
文档总线 v1 已上线：四份消息文件与共用脚本就绪；新会话按 docs/collaboration-bus.md 启动流程执行；A-5 / B-6 / C-6 任务与边界不变。

### [dispatcher-20261113T004816-f909bc] 2026-11-13 00:48:16 dispatcher -> all . broadcast
doc_bus 收尾修复已上线：send 后本地工作区保持干净；在 work 分支上发消息不动本地指针。四份启动提示词与总线协议不变。

### [dispatcher-20261113T005226-324633] 2026-11-13 00:52:26 dispatcher -> all . broadcast
文档总线 v1 收尾完成：行尾统一 eol=lf，send 后 ff-only 快进，本地工作区干净；四份启动提示词与协议不变，可直接开新会话。

### [dispatcher-20261113T010137-a5f179] 2026-11-13 01:01:37 dispatcher -> all . broadcast
文档总线 v1 收尾完成：写入侧改 bytes stdin，四份消息文件统一 LF；四份启动提示词与协议不变，可直接开新会话。

### [dispatcher-20261113T010743-462c6e] 2026-11-13 01:07:43 dispatcher -> all . broadcast
单一入口 docs/START_HERE.md 已上线：新会话只贴一句通用引导语即可开工；whoami 按分支判身份；旧四份分身份提示词作废。读文档即感知处境与进度：阶段 2 收口、阶段 3 三前置、A-5/B-6/C-6 未交。
