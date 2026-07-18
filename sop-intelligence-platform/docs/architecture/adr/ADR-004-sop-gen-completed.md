# ADR-004: SOP 自动生成 Pipeline 完成态与接口契约

## 状态

Accepted · 2026-04-09  

**范围**：`p1-sop-gen`（`docs/module-specs/sop-engine.md` T01–T10）交付冻结的**对外与跨层协议**，供 `p1-sop-fsm` 与工位侧消费。

## 背景

SOP 生成链路涉及视频分段、VLM 语义标注、结构化编译、对象存储与关系型快照。Phase 1 在无 Celery 的前提下采用**同步 HTTP** 完成一次生成，并要求 API 层不嵌入模型推理实现，仅做编排。

## 决策摘要

1. **唯一 REST 入口（Phase 1）**：`POST /api/sop/generate` 同步执行完整流水线；`GET /api/sop/{sop_id}` 返回已持久化的 `SOPDocument` JSON。
2. **持久化职责**：`VersionManager.save` 负责并发上传关键帧、回写 `minio://` 路径、写入 `sop_versions`；查询经 `VersionManager.get` 委托 PostgreSQL 适配器。
3. **segment_id → step_id 映射**：编排层在 `SOPCompiler.compile` 之后，将 `VideoParser` 产出的 `keyframes[segment_id]` 按 **segment_id 升序**与 `doc.steps` 逐项对齐，构造 `VersionManager.save(..., keyframe_bytes={step_id: bytes})`。
4. **发布与弃用**：`POST /api/sop/{sop_id}/publish` 与 `VersionManager.publish` 的实现推迟到 Phase 2；当前 `publish` 为占位（`NotImplementedError`）。

## HTTP API 契约

**基路径**：应用挂载 `src/api/routes/sop.py` 中 `router` 于 **`/api`**，路由器前缀 **`/sop`**。

### `POST /api/sop/generate`

**请求体**（`SOPGenerateRequest`）：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `product_id` | `string` | `min_length=1` | 产品型号 |
| `video_paths` | `string[]` | `min_length=1` | 源视频在对象存储中的路径；**Phase 1 仅使用 `video_paths[0]`** |
| `version` | `string` | 默认 `"v1.0"`，`min_length=1` | 版本后缀，与 `product_id` 组合为 `SOPDocument.version` |

**成功响应**（`200`，`SOPGenerateResponse`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `string` | 与 `sop_id` 相同（无任务队列） |
| `status` | `"accepted" \| "completed"` | 同步成功时为 `"completed"` |
| `sop_id` | `string \| null` | 新建文档主键（UUID 字符串） |

**典型错误**（`detail` 为 JSON 对象）：

| HTTP | `detail.code` | 含义 |
|------|----------------|------|
| `503` | `storage_unavailable` | 未配置 `SOP_POSTGRES_DSN` 或存储未初始化 |
| `400` | `invalid_video_path` | `video_paths[0]` 为空 |
| `422` | `parse_empty` | 视频解析无片段 |
| `422` | `annotate_empty` | VLM 无返回 |
| `422` | `compilation_failed` | `SOPCompilationError`（可含 `details`） |
| `504` | `vlm_timeout` | 标注阶段整体超时 |
| `503` | `persist_failed` | MinIO/PostgreSQL 写入失败 |
| `500` | `internal_segment_mismatch` | 编译步骤数与分段数不一致（不应出现于正常数据） |

### `GET /api/sop/{sop_id}`

**成功**（`200`）：响应体为 **`SOPDocument`** 的 JSON 序列化（与 `src/types/sop.py` 模型一致）。

**错误**：

| HTTP | `detail.code` | 含义 |
|------|----------------|------|
| `503` | `storage_unavailable` | 存储未初始化 |
| `404` | `not_found` | 无对应 `sop_id` |

## 编排与内部契约（非 HTTP）

执行顺序（`src/api/routes/sop.py`）：

1. **`VideoParser.parse(video_paths[0])`** → `list[ActionSegment]`（按 `start_time_sec` 升序）。
2. **关键帧**：对每个 `segment`，`extract_keyframe(path, segment.keyframe_index)` → `bytes`，填入 `dict[segment_id, bytes]`（**键为 `segment_id`**，与 T03→T04 规格一致）。
3. **`VLMAnnotator.annotate(segments, keyframes, product_context=product_id)`** → `list[AnnotatedStep]`（并发上限 5；非法 JSON 降级不中断）。
4. **`SOPCompiler.compile(...)`**：占位 `keyframe_paths` 仅用于通过校验；真实路径由 `VersionManager.save` 写入。
5. **`VersionManager.save(doc, keyframe_bytes={step_id: jpeg_bytes})`**：键必须为 **`SOPStep.step_id`**，与编译器按 `segment_id` 升序生成的步骤一一对应。

**应用启动**（`src/api/main.py`）：若设置 `SOP_POSTGRES_DSN`，则创建 `PostgresSopVersionsClient` 与 `MinioStorageClient`，并挂载 `VersionManager(minio=..., postgres=...)` 至 `app.state.version_manager`。

## 存储与路径约定

- **关键帧对象键**（实现于 `MinioStorageClient.upload_keyframe`）：`{keyframes_bucket}/{sop_id}/step_{step_id}.jpg`；写入 `SOPStep.keyframe_path` 时为 **`minio://{bucket}/{key}`** 形式。
- **源视频路径**：保留在 `SOPDocument.source_video_paths`（来自请求 `video_paths`）。
- **版本快照表**：`sop_versions.content_json` 存完整 `SOPDocument`（JSONB）。

## `VersionManager` 补充契约

- **`save(doc, *, keyframe_bytes)`**：按 `step_id` 上传 JPEG，更新 `keyframe_path`，`save_sop_version`。
- **`get(sop_id)`**：`SOPDocument | None`。
- **`diff_update(..., keyframe_bytes_by_segment_id)`**：换型增量；键为 **`segment_id`**。
- **`publish(sop_id)`**：Phase 2；当前未实现。

## 后果

- **下游 `p1-sop-fsm`** 仅需依赖 **`SOPDocument`** 与 **`ActionSegment.action_class` / `SOPStep.action_type`** 语义一致即可编排 FSM。
- **替换 VideoMAE / VLM**：保持 `VideoParser` / `VLMAnnotator` 接口与上述编排不变即可；API 形状不变。
- **发布能力**：新增路由时必须与 `VersionManager.publish` 及 `sop_versions.status` 迁移策略一同设计，并更新本 ADR 或新增 ADR。

## 参考实现路径

| 契约层 | 代码位置 |
|--------|----------|
| HTTP 模型与路由 | `src/api/routes/sop.py` |
| 应用生命周期与依赖注入 | `src/api/main.py` |
| 领域类型 | `src/types/sop.py` |
| 编译与规范化 | `src/services/sop_engine/sop_compiler.py` |
| 版本与持久化编排 | `src/services/sop_engine/version_manager.py` |
| 存储 I/O | `src/adapters/storage/minio_client.py`, `postgres_client.py` |
| 质量门禁 | `tests/harness/sop_gen_eval/run_eval.py` |
