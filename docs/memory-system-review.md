# 记忆系统代码走查报告

走查范围：记忆系统相关代码、注释与文档。
覆盖文件：

- 核心层：`flask_server/core/memory_db.py`、`memory_distill.py`、`memory_keywords.py`、`memory_search.py`、`memory_nodes.py`、`memory_events.py`、`memory_edges.py`、`memory_decay.py`、`memory_conversations.py`、`memory_cards.py`、`memory_solidify.py`、`memory_notes.py`、`memory_loader.py`、`memory_scheduler.py`
- 路由层：`flask_server/routes/memory_graph.py`
- 工具层：`flask_server/tools/memory_quality_impl.py`、`memory_search_impl.py`
- 测试：`flask_server/tests/test_memory_db_conn.py`
- 前端：`extend/dialog/parts/05h_memory_bridge.js`、`05d_memory.js`
- 文档：`docs/记忆机制改进方案.md`

走查方法：静态阅读 + 注释与实现逐条对照 + 运行时记忆抽检验证。

---

## 一、结论摘要

模块边界清晰，注释普遍解释「为什么这么做」（WAL 只设一次、慢 SQL 用 progress_handler、蒸馏串行队列、逐节点短事务），质量在上游。

问题集中在两类：

1. **规格未落地**：设计文档规定的行为在代码中缺失或走样，导致功能事实与文档不符。
2. **注释与实现脱节**：注释描述的是设计意图，实现却停在别处，读者会被误导。

按严重程度分四级列出。

---

## 二、严重：功能事实错误或测试失真

### S1 工具节点精华提取与规格不符（已修复）

位置：`memory_distill._essence_for`。

设计文档 4.2 规定 tool 来源产出「工具名 + 结果摘要」。实现只把 blocks 纯文本截前 200 字，工具节点的 blocks 是 `bridge-chat-res` 的 JSON 原文，于是精华成为被腰斩的 JSON。

这是记忆抽检反复出现失真的根因，稳定复现。

修复：新增 `_tool_essence`，解析 JSON 取 `tool` 与 `result` 摘要，解析失败回退文本截断。

### S2 测试复位未重置建表标志（已修复）

位置：`memory_db.reset_for_tests`。

它重置连接与库路径，但模块级 `_schema_ready`、`_wal_ready` 未复位。真实库已在进程内建过表时，切到临时库后 `_ensure_schema_once` 直接返回，临时库没有表。

修复：把两个标志一并复位。

### S3 初始分级未按来源落地（已修复）

位置：`memory_nodes.upsert_node`。

设计文档 4.4 规定初始分级：用户发言 perm、AI 回复 temp、工具结果 mid。实现所有节点一律 `temp`。

修复：按 `source` 映射初始 tier 写入 INSERT。

### S4 dormant 未实现，图遍历不排除零权边（已修复）

位置：`memory_edges.get_neighbors`。

设计文档 5.2 规定权重衰减到阈值以下标记 dormant 且图遍历不展开。实现只把权重置 0，且 `get_neighbors` 查询无权重条件，零权边照常参与遍历。

修复：两分支 SQL 各加 `AND weight > 0`，衰减到零的边不参与图遍历。

---

## 三、中：注释与实现不一致

### M1 关于 FTS5 的描述自相矛盾（已修复）

`memory_db` docstring 与 `_ensure_schema` 称「建 FTS5 全文索引（关键词检索）」，`memory_search._fts_search` docstring 明确说中文分词失效、已改用 LIKE。FTS5 虚表建了却无人查询。

修复：`memory_db` 与检索层注释统一为「FTS5 虚表仅保留兼容，关键词检索实际走 LIKE 子串匹配」。

### M2 表数量注释错误（已修复）

`memory_db` docstring 与 `_SCHEMA` 注释写「五张表」，实际 7 张（另有 notes、conversations）。附带 `search_vectors` 归属写错文件。

修复：改为七张表并更正归属。

### M3 「三路并行」名不副实（已修复）

`memory_search` 称三路并行，实际图遍历的种子只取关键词路前三条，向量路不参与，且关键词路已非 FTS5。

修复：注释改为「关键词路 + 向量路 + 以关键词路结果为种子的图遍历」。

### M4 `cluster_events` 声称写 revision_log 实际未写（已修复）

docstring 写「改用 revision_log 记录聚类事件」，函数体全程未写。

修复：删去不实描述，注明聚类结果仅内存返回。

### M5 `close_conn` 实现了却无调用点

位置：`memory_db.close_conn`。docstring 强调请求线程处理完毕后释放连接，路由层无任何调用。

处置：保留能力与测试；路由层是否接入按需决定，注释保持与实现一致即可。

### M6 `upsert_node` 的 ON CONFLICT 字段与注释不符（已修复）

注释写「更新内容字段」，SQL 只更新 `blocks` 与 `parent_id`。

修复：注释明确只更新 blocks 与 parent_id。

### M7 `_next_tier` 无降级路径（已修复）

docstring 暗示存在降级评估，函数只有升级分支，`recompute_all` 的 `downgraded` 恒为 0。

修复：注释注明「当前仅升级，不降级」。

### M8 `_all_stop` 判定近乎失效（已修复）

`memory_keywords._all_stop` 用单字去匹配以多字词为主的停用词表，基本不生效。

修复：注释注明该判定对中文单字近似失效，短语切分由 boundaries 承担。

---

## 四、轻：死代码与文档滞后

### L1 死代码与冗余参数（已清理）

- `memory_conversations._save_conversation_inner` 的 `_t0` 参数未使用——已删。
- `memory_conversations._find_key_by_child` 无调用——已删。

### L2 设计文档未随实现更新

- 文档 3.3 称向量检索用 sqlite-vec，实现用 numpy 暴力余弦。
- 文档 4.3 把 LLM 精筛列为必备，实现默认关闭且无 provider。

处置：在文档相应处标注实现现状。

### L3 日期隔离的两个缺口

- `paths.MEMORY_DIR` 仍定义，全工程无引用。
- `memory_notes` 称「原 Markdown 迁移入此」，但无迁移代码。

处置：迁移代码缺失项单列待办；死路径清理按需。

---

## 五、日期隔离机制说明

旧机制：`memory/` 目录按天一个 Markdown 文件，另加 `error-notebook.md`。

新机制：`notes` 表，`kind` + `day` 两字段区分。

| 类型 | kind | day | 语义 |
|---|---|---|---|
| 每日记忆 | journal | YYYY-MM-DD | 按天隔离 |
| 错题本 | notebook | NULL | 永久累积 |

接口：`add_note` 仅对 journal 写 day；`list_notes(kind, day)` 按日期过滤；`list_days` 列出有内容的日期；QQ 指令取最新一天发送。

结论：日期隔离保留在每日记忆一类；错题本按设计不分日期。

---

## 六、注释质量评价

好的方面：模块 docstring 普遍交代职责、依赖、并发模型与取舍原因，属高质量「原因型注释」。

风险方面：部分注释描述的是设计意图，意图与落地之间存在缺口（S3、S4、M1、M4、M7）。意图型注释在实现未跟上时会误导维护者，需与实现保持同步。
