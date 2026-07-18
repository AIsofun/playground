# 模块规格：`src/services/compliance/` 与合规慢路径

**对应 Todo**：`p1-compliance`（Phase 1）  
**领域规则（三档、阈值语义）**：`docs/domain-logic.md`（阈值数值真源：`src/config/vlm.py`）  
**子目录约束**：`src/services/compliance/AGENTS.md`  
**分层**：`docs/architecture/layering.md`

本文件描述 **服务端合规慢路径** 的对外契约：gRPC 入参、VLM 调用形状、Kafka、MinIO、PostgreSQL 元数据，以及与 **误报反馈 API**（`src/api/routes/feedback.py`：`POST /feedback/false-positive`；路由前缀见 `docs/architecture/layering.md`）的边界。

---

## 1. 职责边界

| 区域 | 职责 |
|------|------|
| **边缘 `edge_node`** | Fast Path：FSM + 检测 → 产出 \(s\) 与三档 → **仅 `UNCERTAIN` 档**按约定上送帧（见 `docs/module-specs/edge-node.md`、`plan/sop-intelligence-platform.md` edge 小节）。 |
| **`src/adapters/edge/`** | gRPC 服务端：接收帧字节流与元数据，**无业务分支**（不写三档逻辑）。 |
| **`src/services/compliance/`** | 三档分类（引用 `CONF_LOW`/`CONF_HIGH`）、VLM 编排（经上层或专用 handler 调用适配器）、分歧检测、协调写 MinIO + PG、发 Kafka。 |
| **`src/api/`** | HTTP/WS 入口；**不写业务**；合规查询路由见 `docs/architecture/layering.md`（`routes/compliance.py`）。 |

**禁止**（摘自 `compliance/AGENTS.md`）：在 `fsm_runtime.py` 内直接调用 VLM；在 `confidence_classifier.py` 内硬编码阈值数字。

---

## 2. gRPC（边缘 → 服务端）

**协议**：`frame_upload.proto`（二进制帧 + 元数据）；架构说明见 `docs/architecture/adr/ADR-002-grpc.md`。  
**触发条件**：边缘对当前帧/clip 判定为 **`UNCERTAIN`**（见 `docs/domain-logic.md`）。

### 2.1 建议消息字段（实现以 proto 为最终真源）

以下为 **规格层** 最小集，便于前后端对齐；字段名以仓库内 `.proto` 落地为准。

| 字段 | 类型 | 说明 |
|------|------|------|
| `workstation_id` | string | 工位唯一标识。 |
| `sop_id` | string | 当前执行的 SOP 版本标识。 |
| `sop_step` | int32 | 当前 FSM 步骤索引或规范步骤 ID（与事件 `sop_step` 一致）。 |
| `captured_at` | string (ISO8601) / int64 | 采集时间。 |
| `edge_confidence` | float | \([0,1]\)，即领域文档中的 \(s\)。 |
| `edge_level` | enum/string | `COMPLIANT` / `UNCERTAIN` / `VIOLATION`（上传帧时应为 `UNCERTAIN`）。 |
| `frame_jpeg` | bytes | JPEG；规划约束参考 `plan/...` edge 小节（如 ≤500KB 等，以 edge 规格为准）。 |
| `fsm_state` | string | 可选；当前 FSM 状态名，便于 VLM 上下文。 |

**超时**：帧上传链路的超时与重试策略见 `plan/sop-intelligence-platform.md` edge 小节；与 **VLM HTTP** 的 `VLM_TIMEOUT_SEC`（`src/config/vlm.py`）是**不同层**的配置，勿混为一谈。

---

## 3. VLM 调用（服务端 → vLLM）

**通道**：HTTP(S)，**OpenAI 兼容** Chat Completions（与 `src/services/sop_engine/vlm_annotator.py` 同类集成方式）。  
**配置**：`src/config/vlm.py`（`VLM_BASE_URL`、`VLM_MODEL_NAME`、`VLM_TIMEOUT_SEC`、`VLM_MAX_TOKENS` 等）。  
**Prompt 模板**：`.ai/prompts/vlm-anomaly-check.txt`（异常/合规复核；须与 Harness 数据集一致迭代）。

### 3.1 请求（逻辑形状）

- **角色**：`system` + `user`（`user` 含 **当前 SOP 步骤文字上下文** + **一帧图像** `image_url`/`image_base64`，以实际客户端为准）。  
- **模型**：来自 `VLM_MODEL_NAME`。

### 3.2 响应 JSON（应用层解析目标）

服务从模型文本中解析出结构化对象（示例字段名，实现可包一层 `response_format` 或 JSON mode，以代码为准）：

```json
{
  "is_anomaly": false,
  "reason": "string",
  "confidence": 0.0
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_anomaly` | bool | **true** 表示与 SOP 期望严重偏离 / 违规；**false** 表示可视为合规或噪声可接受。 |
| `reason` | string | 短理由，供工单与审计。 |
| `confidence` | float | VLM 自身置信度 \([0,1]\)，用于日志与二次阈值（若有）；**不得替代**边缘 \(s\) 作为 `CONF_LOW`/`CONF_HIGH` 的定义来源。 |

**分歧检测**：逻辑条件见 `src/services/compliance/AGENTS.md` 第三节（`COMPLIANT` vs `is_anomaly`、`VIOLATION` vs `is_anomaly` 的组合）。

---

## 4. Kafka：`compliance.events`

**发布**：须通过 `src/adapters/messaging/kafka_producer.py`（禁止在 compliance 内直接 new Producer）。  
**Topic 名**：以 `src/config/kafka.py` 落地为准；架构预期见 `docs/architecture/layering.md`（示例名 `compliance.events`）。

### 4.1 消息 JSON Schema（字段级）

与 `src/services/compliance/AGENTS.md` 第四节一致，细化类型如下：

| 字段 | JSON 类型 | 必填 | 说明 |
|------|-----------|------|------|
| `timestamp` | string | 是 | ISO8601 UTC。 |
| `workstation_id` | string | 是 | 工位 ID。 |
| `event_type` | string | 是 | 如 `SOP_VIOLATION`、`BATCH_DEFECT`、`MODEL_CHANGEOVER`（MVP 以 `SOP_VIOLATION` 为主）。 |
| `sop_step` | integer | 是 | 步骤编号。 |
| `frame_path` | string | 条件 | MinIO 引用，格式 `minio://{bucket}/{object_key}`；无帧时可约定空字符串或省略策略（实现须文档化）。 |
| `confidence` | number | 是 | 与事件语义一致的标量（如最终判定置信度或边缘 \(s\)，**实现须在代码注释中固定一种含义**）。 |

---

## 5. MinIO 与对象路径

**分歧 / 难例桶**：`src/config/storage.py` → `MINIO_BUCKET_HARD_CASES`（默认 `hard-cases`）。  
**路径约定（建议，实现可调整但须同步本文档）**：

```text
{MINIO_BUCKET_HARD_CASES}/{workstation_id}/{yyyy}/{mm}/{dd}/{uuid}.jpg
```

**URI 写法**：写入 Kafka / PG 时使用 `minio://{bucket}/{object_key}` 前缀，与 SOP 关键帧 `minio://...` 风格一致（见 `docs/architecture/adr/ADR-004-sop-gen-completed.md`）。

---

## 6. PostgreSQL 元数据（与 MinIO 配对）

**原则**（`compliance/AGENTS.md`）：对象写入 MinIO 后，**必须**有 PG 元数据；需事务或补偿。

### 6.1 规划表（名称以迁移 SQL 为最终真源）

| 表 / 超表 | 用途 |
|-----------|------|
| `compliance_events`（TimescaleDB 超表，规划） | 合规事件时序：支撑看板与合规率查询。 |
| `data_lake_samples`（规划） | 数据湖样本索引：`frame_path`、`label`、`sop_step`、`workstation_id`、`source`（`auto` \| `manual`）、`timestamp`。 |

**`source` 枚举**：

- **`auto`**：分歧帧自动入湖（VLM 结论作伪标签，见 `compliance/AGENTS.md`）。  
- **`manual`**：人工误报等，经反馈 API 写入。

具体列类型与索引见后续迁移脚本；本文件锁定**语义字段集**。

---

## 7. 与误报 API（`POST /feedback/false-positive`）的关系

| 维度 | 合规服务（本模块） | 反馈 API |
|------|-------------------|----------|
| 触发 | 系统自动（分歧、违规链路） | 工位 UI「误报」操作 |
| `source` | `auto` | `manual`（或规范等价枚举） |
| 标签策略 | VLM 结论或规则引擎输出 | 产品规约：误报 → 标签 **`COMPLIANT`**（见 `plan/sop-intelligence-platform.md` data_lake `labeler` 小节） |
| 存储 | 同一 `hard-cases` 桶 + `data_lake_samples` 扩展行 | 复用数据湖写入路径（`src/services/data_lake/collector.py`，实现后） |

路由文件：`src/api/routes/feedback.py`（当前占位时，实现须遵守本边界）。

---

## 8. HTTP API（查询侧，MVP）

| 路由前缀 | 说明 |
|----------|------|
| `/api/compliance` | 合规率、事件列表等只读查询（委托 service + adapter），无业务逻辑在路由内。 |

细节请求/响应模型在 OpenAPI/代码稳定后补全；本阶段以 **`layering.md` 职责表** 为准。

---

## 9. 测试与 Harness

- **单元测试**：`tests/unit/` — 纯逻辑，无 I/O。  
- **Harness**：`tests/harness/compliance_eval/` — 门禁见 `docs/eval-standards.md`。  
- **集成测试**：`tests/integration/test_compliance_pipeline.py` — 含真实 Kafka/MinIO 的流水线（见根 `AGENTS.md`）。**依赖启动、环境变量与 CI 示例**：`tests/integration/README.md`；Compose：`deploy/docker-compose.integration.yml`。

---

## 10. 相关文档

- `docs/domain-logic.md`  
- `docs/eval-standards.md`  
- `docs/module-specs/edge-node.md`  
- `docs/module-specs/data-lake.md`（数据湖总览；与本模块写入交叉）  
- `plan/sop-intelligence-platform.md` — 第五章 `services/compliance_service/`
