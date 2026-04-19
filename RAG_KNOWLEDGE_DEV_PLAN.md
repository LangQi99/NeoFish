# NeoFish 知识库（文件夹粒度）RAG 开发方案

## 1. 目标与范围

本方案用于 NeoFish 的“知识库”能力建设，目标是：

- 以**文件夹**为最小管理粒度（不做文件级勾选）；
- 支持文件夹创建、文件上传、文件浏览、文件删除；
- 支持勾选文件夹进入检索范围（selected folders）；
- 保证“向量索引中的有效内容”始终与用户勾选状态一致；
- 前端采用“进入文件夹工作区”的交互（类似文件管理器）。

非目标：

- 暂不做文件级权限系统；
- 暂不做复杂增量索引（首版采用文件夹全量重建）；
- 暂不接入多租户。

---

## 2. 核心设计原则

### 2.1 单一真相源

`selected_folders` 是唯一真相（source of truth）。  
向量库只是副本，必须被“同步器/对账器”收敛到该真相。

### 2.2 声明式同步

用户操作只改变“期望状态”，后台任务负责把实际状态对齐。

- `to_add = selected - indexed`
- `to_remove = indexed - selected`
- `to_rebuild = selected ∩ dirty`

执行顺序建议：

1. 先 `rebuild/add`；
2. 再 `remove`；
3. 更新 `index_manifest` 与 `dirty` 标记。

### 2.3 文件夹粒度索引

- 选中文件夹：对该文件夹全量扫描、切块、嵌入、写索引；
- 取消勾选：按 `folder_id` 清空索引分区；
- 文件增删：若文件夹已选中，则标记 `dirty` 并触发该文件夹全量重建。

---

## 3. 代码结构建议

## 3.1 后端新增模块

- `knowledge_service.py`  
  负责文件夹/文件 CRUD、元数据统计、路径安全校验。

- `knowledge_state.py`  
  负责状态持久化（selected/indexed/dirty/index_status）。

- `knowledge_indexer.py`  
  负责切块、embedding、索引构建、按 folder 检索与清理。

- `embedder.py`  
  抽象 embedding 提供方（首版可固定 MiniMax，后续可替换）。

## 3.2 现有文件改造点

- `main.py`  
  增加知识库 REST API 路由。

- `agent.py`（第二阶段）  
  增加 `knowledge_*` 工具（列表、勾选、取消、检索）。

---

## 4. 存储与目录规范

建议落盘结构：

- `WORKDIR/knowledge/<folder_id>/`：原始知识文件
- `WORKDIR/.knowledge/state.json`：selected / indexed / dirty / status
- `WORKDIR/.knowledge/file_index.json`：文件元数据（hash、mtime、size）
- `WORKDIR/.knowledge/vector_snapshot/`：本地索引快照（可选）

关键字段建议：

- `folder_id`：安全 slug（显示名和 id 分离）
- `file_id`：建议 `sha1(folder_id + relative_path)`
- `index_status`：`ready | indexing | failed`
- `generation`：索引代次（可选，用于原子切换）

---

## 5. API 设计（首版）

### 5.1 文件夹管理

- `GET /knowledge/folders`  
  返回：
  - `id`
  - `name`
  - `path`
  - `file_count`
  - `size_label`
  - `updated_at`

- `POST /knowledge/folders`  
  请求：`{ "name": "xxx" }`  
  行为：创建文件夹，返回新对象。

### 5.2 勾选状态管理

- `GET /knowledge/selected`  
  返回：`{ "selected_folder_ids": ["..."] }`

- `POST /knowledge/select`  
  请求：`{ "folder_id": "xxx" }`  
  行为：加入 selected，触发该 folder 重建任务（幂等）。

- `POST /knowledge/deselect`  
  请求：`{ "folder_id": "xxx" }`  
  行为：从 selected 移除，删除该 folder 索引（幂等）。

### 5.3 文件管理

- `POST /knowledge/upload`（multipart）
  - 字段：`folder_id` + `files[]`
  - 行为：保存文件；若 folder 已选中，标记 dirty 并触发重建。

- `GET /knowledge/folders/{folder_id}/files`  
  返回：
  - `id`
  - `name`
  - `mime_type`
  - `size_label`
  - `updated_at`
  - `preview_url`（可选）

- `DELETE /knowledge/files/{file_id}`  
  行为：删除文件；若所属 folder 已选中，标记 dirty 并触发重建。

### 5.4 可选状态接口

- `GET /knowledge/status`  
  返回每个 folder 的索引状态，用于前端提示 `indexing/failed/ready`。

---

## 6. 并发、幂等与容错

### 6.1 并发控制

- 每个 `folder_id` 一把 `asyncio.Lock`；
- 防止上传与重建并发导致元数据不一致。

### 6.2 幂等语义

- 已选再选：返回成功（不重复入库）；
- 未选取消：返回成功（不报错）；
- 重复删除文件：返回“已不存在”可视为成功。

### 6.3 失败恢复

- 重建失败：`index_status=failed`，保留 dirty 标志；
- 定时对账任务再次尝试；
- API 层不因后台失败阻塞用户主流程。

---

## 7. 索引与检索策略（首版）

### 7.1 构建

1. 扫描 `folder_id` 下所有可索引文件；
2. 文本提取与切块；
3. embedding；
4. 写入索引分区（按 `folder_id` 标记）；
5. 更新 `index_manifest` 和状态。

### 7.1.1 切片（Chunking）策略

首版采用“**段落优先 + 长度兜底 + 重叠补边界**”策略，不做整文件向量化。

- 入库单位：`chunk`（不是整个文件）
- 推荐 chunk 大小：`500 ~ 900 tokens`
- 推荐 overlap：`10% ~ 20%`（建议 `80 ~ 150 tokens`）
- 分片优先级：
  1. 先按标题/段落边界切（保证语义完整）；
  2. 超长段落再按长度强制切分；
  3. 切分后在相邻 chunk 之间加入 overlap。

建议的 chunk 元数据字段：

- `folder_id`
- `file_id`
- `chunk_id`
- `source_path`
- `chunk_index`
- `start_offset` / `end_offset`（可选）

为什么不用“整文件直接入库”：

- 语义粒度过粗，召回精度低；
- 长文容易超 embedding 上下文限制或被截断；
- 召回后单条上下文过大，导致成本升高且噪音增加。

---

### 7.1.2 切片参数调优方法（上线前）

建议用离线评测集做 A/B：

- 方案 A：`chunk=512, overlap=64`
- 方案 B：`chunk=768, overlap=96`
- 方案 C：`chunk=900, overlap=128`

评测指标建议：

- `Recall@k`（是否召回正确片段）
- `MRR`（正确片段排序）
- 单次查询上下文 token 成本
- 最终回答正确率（人工抽样）

首版默认推荐：

- `chunk=768 tokens`
- `overlap=96 tokens`

若文档短小且结构化明显，可适当减小 chunk。  
若文档偏长且跨段依赖强，可适当增大 overlap。

### 7.2 查询

- 查询时只在 `selected_folders` 对应分区检索；
- 返回 top-k 片段给 Agent；
- 返回项附带 `folder_id/file_id/chunk_id` 便于追踪。

### 7.3 清理

- 取消勾选时按 `folder_id` 批量清理索引；
- 定时“垃圾回收”删除非 selected 的残留分区。

---

## 8. 前后端联调约定

前端目前已具备以下交互路径：

- 左侧“知识库”入口；
- 文件夹列表；
- 点击文件夹进入工作区（文件网格）；
- 工作区内上传、删除；
- 勾选文件夹是否参与检索。

后端接口实现时需保证字段名与前端一致：

- `selected_folder_ids`
- `file_count`
- `size_label`
- `updated_at`
- `mime_type`
- `preview_url`（可空）

---

## 9. 落地顺序（建议）

### 阶段 1：接口与文件管理打通

1. 实现 `folders/selected/upload/files/delete` API；
2. 本地状态落盘（state + file_index）；
3. 前端从 demo 切真实接口。

### 阶段 2：索引与同步器

1. 实现文件夹全量重建；
2. 接入 select/deselect 流程；
3. 增加 dirty 对账任务。

### 阶段 3：Agent 集成

1. 在 `agent.py` 增加 `knowledge_search` 工具；
2. 仅查询 selected folders；
3. 在回答中引用来源片段（可选）。

---

## 10. 纠错清单（上线前必查）

- [ ] `folder_id` 是否安全规范化（防路径穿越）
- [ ] 文件上传是否限制类型/大小
- [ ] 幂等行为是否一致（select/deselect/delete）
- [ ] dirty 标志是否在成功重建后清理
- [ ] 重建失败是否可重试
- [ ] 查询是否严格限定 selected folders
- [ ] 前端是否正确处理 `loading/indexing/error` 状态

---

## 11. 首版验收标准

- 新建文件夹后可见；
- 上传文件后进入文件夹可见；
- 删除文件后列表即时更新；
- 勾选文件夹后可检索命中；
- 取消勾选后不可命中；
- 重启服务后 selected 与索引状态不丢失；
- 异常中断后可通过对账任务恢复一致性。
