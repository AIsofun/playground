# 分层依赖规则 — src/ 架构约束

> **强制性**：本文件定义的规则由 CI `import-linter` 自动检查，违反规则的 PR 将被阻断合并。  
> AI Agent 在修改 `src/` 中任何文件前必须先阅读本文件。

---

## 一、分层架构总览

```
┌─────────────────────────────────────────┐
│  Layer 5: src/api/                      │  ← API 入口层
│  FastAPI Routes + WebSocket             │     可依赖所有层
│  禁止含业务逻辑                          │
├─────────────────────────────────────────┤
│  Layer 4: src/adapters/                 │  ← 外部系统适配层
│  MinIO / Kafka / PostgreSQL / MES 等    │     依赖 types + config
│  禁止含业务逻辑，只做 I/O 封装           │
├─────────────────────────────────────────┤
│  Layer 3: src/services/                 │  ← 核心业务逻辑层
│  sop_engine / compliance / agents /     │     依赖 types + config
│  event_router / data_lake               │     可调用 adapters
├─────────────────────────────────────────┤
│  Layer 2: src/config/                   │  ← 配置层
│  阈值常量 / 连接参数 / Topic 名称        │     仅依赖 types
├─────────────────────────────────────────┤
│  Layer 1: src/types/                    │  ← 类型定义层
│  Pydantic 数据模型                      │     零外部依赖
│  SOPDocument / ComplianceEvent 等       │
└─────────────────────────────────────────┘
```

**依赖方向**：只允许高层 import 低层，**严禁低层 import 高层**。

---

## 二、各层详细规则

### Layer 1：`src/types/` — 类型定义层

**职责**：定义全项目共享的 Pydantic 数据模型，是整个系统的数据契约。

**允许 import**：
- Python 标准库
- `pydantic`
- `enum`、`datetime`、`typing`

**禁止 import**：
- `src/config/`、`src/services/`、`src/adapters/`、`src/api/` 中的任何内容
- 任何需要网络连接、数据库连接的库（`kafka`, `minio`, `psycopg2` 等）

**文件职责**：

| 文件 | 包含的类型 |
|------|-----------|
| `sop.py` | `SOPDocument`, `SOPStep`, `FSMState`, `FSMTransition` |
| `events.py` | `ComplianceEvent`, `AnomalyEvent`, `RouteEvent`, `EventType`（枚举）|
| `frames.py` | `VideoFrame`, `AnnotatedFrame`, `DataLakeSample`, `ConfidenceLevel`（枚举）|
| `models.py` | `ModelVersion`, `EvalMetrics`, `InferenceResult`, `OTAPackage` |

---

### Layer 2：`src/config/` — 配置层

**职责**：集中管理所有配置常量，是全项目"魔法数字"的唯一来源。

**允许 import**：
- Python 标准库
- `src/types/` 中的枚举类型（用于类型注解）
- `pydantic-settings`（从环境变量读取）

**禁止 import**：
- `src/services/`、`src/adapters/`、`src/api/` 中的任何内容

**关键常量（不得在其他文件硬编码）**：

```python
# src/config/vlm.py
CONF_LOW: float = 0.4    # UNCERTAIN 阈值下界
CONF_HIGH: float = 0.7   # COMPLIANT 阈值下界
VLM_TIMEOUT_SEC: int = 2  # gRPC 上传超时

# src/config/kafka.py
TOPIC_COMPLIANCE_EVENTS = "compliance.events"
CONSUMER_GROUP_ROUTER = "event-router-group"

# src/config/storage.py
MINIO_BUCKET_HARD_CASES = "hard-cases"
MINIO_BUCKET_MODELS = "models"
DATA_LAKE_TRIGGER_THRESHOLD = 200  # 触发 QLoRA 的最小新增样本数
```

> ⚠️ **规则**：置信度阈值 `CONF_LOW` / `CONF_HIGH` 修改后，必须同步更新 `docs/domain-logic.md`，并重跑 `tests/harness/compliance_eval/run_eval.py`。

---

### Layer 3：`src/services/` — 核心业务逻辑层

**职责**：实现所有业务规则，是系统的"大脑"。

**允许 import**：
- `src/types/`
- `src/config/`
- `src/adapters/`（调用外部系统，但不依赖其具体实现细节）
- 业务相关第三方库（`transitions`, `langgraph`, `torch` 等）

**禁止 import**：
- `src/api/` 中的任何内容（服务层不知道 HTTP/WebSocket 的存在）
- 直接实例化数据库连接（必须经过 `src/adapters/`）

**子模块规则**：

| 子模块 | 专属约束 | 详见 |
|--------|----------|------|
| `sop_engine/` | VLM Prompt 修改必须同步 `.ai/prompts/` | `sop_engine/AGENTS.md` |
| `compliance/` | 阈值修改必须同步 `docs/domain-logic.md` | `compliance/AGENTS.md` |
| `agents/` | 所有 LangGraph Agent 须含 Human-in-Loop 节点 | `agents/AGENTS.md` |
| `event_router/` | 路由规则修改须更新 `docs/architecture/overview.md` 第四节 | — |
| `data_lake/` | 写入 MinIO 前必须写元数据到 PostgreSQL | — |

---

### Layer 4：`src/adapters/` — 外部系统适配层

**职责**：封装所有外部系统的 I/O 操作，为 `services/` 提供干净接口。

**允许 import**：
- `src/types/`
- `src/config/`
- 对应外部系统的 SDK（`minio`, `kafka-python`, `psycopg2`, `pymilvus` 等）

**禁止 import**：
- `src/services/`、`src/api/`
- **禁止在适配器中写 if/else 业务判断**（违反单一职责）

**子模块职责**：

| 子模块 | 文件 | 封装的外部系统 |
|--------|------|--------------|
| `edge/` | `grpc_server.py` | 接收 Jetson gRPC 帧上传 |
| `edge/` | `ota_client.py` | 向 Jetson 推送 TensorRT 模型 |
| `storage/` | `minio_client.py` | MinIO 对象存储读写 |
| `storage/` | `postgres_client.py` | PostgreSQL + TimescaleDB 读写 |
| `storage/` | `milvus_client.py` | Milvus 向量读写 |
| `messaging/` | `kafka_producer.py` | 发布 compliance.events |
| `messaging/` | `kafka_consumer.py` | 消费事件（供 event_router 使用）|
| `external/` | `mes_client.py` | MES REST API（工单创建）|
| `external/` | `webhook_client.py` | 企业微信 / 钉钉推送 |

---

### Layer 5：`src/api/` — API 入口层

**职责**：HTTP / WebSocket 接口定义，是外部流量的唯一入口。

**允许 import**：所有层

**禁止 import**：无（但有行为约束）

**行为约束**：
- **禁止在路由函数中写业务逻辑**，所有逻辑必须委托给 `services/`
- **禁止在路由函数中直接操作数据库**，必须经过 `adapters/` 或 `services/`
- 路由函数只做：参数解析 → 调用 service → 格式化响应

**接口文件职责**：

| 文件 | 路由前缀 | 说明 |
|------|---------|------|
| `routes/sop.py` | `/api/sop` | SOP 生成触发、版本查询、导出 |
| `routes/compliance.py` | `/api/compliance` | 合规率查询、事件列表 |
| `routes/feedback.py` | `/api/feedback` | `POST /feedback/false-positive`（误报标记入湖）|
| `routes/reports.py` | `/api/reports` | 根因报告列表、审批确认 |
| `websocket/workstation.py` | `/ws/workstation/{id}` | 工位屏实时推送（FSM 状态 + 告警）|

---

## 三、边缘节点的特殊位置

`edge_node/` **不在 `src/` 分层体系内**，独立部署于 Jetson Orin NX：

```
edge_node/          ← 独立部署，不参与 src/ 分层检查
├── AGENTS.md
├── pipeline/       ← GStreamer + OpenCV CUDA
├── inference/      ← TensorRT .engine 加载
├── tracking/       ← ByteTrack
├── fsm_runtime/    ← 唯一共享：可只读引用 src/types/sop.py 的类型
└── anomaly/        ← PatchCore（Phase 2）
```

**唯一桥接**：`edge_node/fsm_runtime/` 通过**复制**（非 import）`src/types/sop.py` 中的 `FSMState` 枚举定义，保持类型一致性，避免部署时的 Python 包依赖问题。

---

## 四、违规检测配置（import-linter）

`.importlinter` 配置示例（待创建）：

```ini
[importlinter]
root_package = src

[importlinter:contract:types-independence]
name = types layer must not import higher layers
type = forbidden
source_modules = src.types
forbidden_modules = src.config, src.services, src.adapters, src.api

[importlinter:contract:config-independence]
name = config layer must not import services or above
type = forbidden
source_modules = src.config
forbidden_modules = src.services, src.adapters, src.api

[importlinter:contract:adapters-no-services]
name = adapters must not import services
type = forbidden
source_modules = src.adapters
forbidden_modules = src.services, src.api

[importlinter:contract:services-no-api]
name = services must not import api
type = forbidden
source_modules = src.services
forbidden_modules = src.api
```

---

## 五、常见违规示例

### ❌ 违规：types 层 import services

```python
# src/types/sop.py — 错误！
from src.services.sop_engine.sop_compiler import compile_fsm  # 禁止
```

### ❌ 违规：adapters 层含业务判断

```python
# src/adapters/storage/minio_client.py — 错误！
def save_frame(frame, confidence):
    if confidence < 0.4:  # 业务判断不应在 adapter 中
        bucket = "violations"
    else:
        bucket = "normal"
```

### ✅ 正确：services 调用 adapters

```python
# src/services/compliance/divergence_detector.py — 正确
from src.adapters.storage.minio_client import MinioClient
from src.config.vlm import CONF_LOW

def detect_divergence(edge_result, vlm_result, frame):
    if edge_result.is_compliant != vlm_result.is_anomaly:
        MinioClient().save(frame, bucket=MINIO_BUCKET_HARD_CASES)
```

### ✅ 正确：api 层委托给 services

```python
# src/api/routes/feedback.py — 正确
from src.services.data_lake.collector import DataLakeCollector

@router.post("/feedback/false-positive")
async def mark_false_positive(payload: FeedbackPayload):
    await DataLakeCollector().ingest_manual(payload.frame_id)
    return {"status": "ok"}
```
