# 系统全景架构 — SOP 智脑

> **SSOT 声明**：本文件是系统架构的唯一事实来源。AI Agent 修改任何跨模块逻辑前必须先阅读本文件。

---

## 一、核心飞轮模型

系统以四步飞轮为驱动核心，每一步都为下一步积累护城河：

```
① SOP 自动生成  →  ② 合规监控（SOP 编译为 FSM）
       ↑                        ↓
④ 质量根因溯源  ←  ③ 数据飞轮（难例自动收集 → 专属模型微调）
```

**护城河本质**：每个客户的数据只服务于自己的模型，越用越准。竞争对手即使复制技术栈，也无法复制这份数据。

---

## 二、系统全景图

系统由六个子系统组成，数据在其间流动：

```
┌─────────────────────────────────────────────────────────────────┐
│  知识输入层                                                      │
│  专家操作视频（5-10段/工序）+ 工艺 BOM                           │
└──────────────────────┬──────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────┐
│  SOP 智脑核心（src/services/sop_engine/）                        │
│  VideoMAE 动作分段 → Qwen2.5-VL-7B 语义理解 → 结构化 SOP 文档   │
│  ↓ 编译为 FSM                    ↓ 存入 Milvus 向量库            │
└──────────┬───────────────────────────────────────────────────────┘
           ↓ FSM 定义下发
┌─────────────────────────────────────────────────────────────────┐
│  工位边缘节点 — Fast Path（edge_node/ @ Jetson Orin NX 16GB）    │
│  摄像头 → GStreamer → YOLOv10-S TensorRT → ByteTrack 追踪        │
│  ↓ FSM 实时判定（< 5ms）                                         │
│  ┌────────────────────────────────────────┐                     │
│  │ 三档置信度分流                          │                     │
│  │  > 0.7 高置信合规 → 本地日志（丢弃）   │                     │
│  │  0.4~0.6 不确定 → 截帧 gRPC 上传       │                     │
│  │  < 0.4 明确违规 → 直接路由告警          │                     │
│  └────────────────────────────────────────┘                     │
│  PatchCore（Phase 2）← 仅需良品图像建立特征库                    │
└──────────┬──────────────────────┬───────────────────────────────┘
 UNCERTAIN 帧上传（gRPC）         │ VIOLATION 事件
           ↓                      ↓
┌─────────────────────────────────────────────────────────────────┐
│  服务端 Slow Path（src/services/compliance/ + adapters/）        │
│  gRPC Server → Qwen2.5-VL-7B 深度推理                           │
│  ↓ VLM 确诊真异常 → 路由告警                                    │
│  ↓ VLM 否决边缘模型（分歧帧）→ 自动写入数据湖                   │
└──────────┬──────────────────────────────────────────────────────┘
           ↓ Kafka topic: compliance.events
┌─────────────────────────────────────────────────────────────────┐
│  事件语义路由层（src/services/event_router/）Phase 2             │
│  消费 Kafka → 按 event_type 语义分类                             │
│  SOP_VIOLATION  → comply_alert Agent                            │
│  BATCH_DEFECT   → quality_root_cause Agent                      │
│  MODEL_CHANGEOVER → sop_switch Agent                            │
└──────────┬──────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Agent 层（src/services/agents/ — LangGraph）Phase 2             │
│  comply_alert        → 企业微信/钉钉 Webhook + 工位屏推送         │
│  quality_root_cause  → 5W1H 根因报告 + Human-in-Loop + MES 工单  │
│  sop_switch          → 从 Milvus 召回新产品 SOP + 工位屏推送     │
└──────────┬──────────────────────────────────────────────────────┘
           │                    ↑ OTA 热更新（.engine + FSM）
┌─────────────────────────────────────────────────────────────────┐
│  自动数据飞轮（src/services/data_lake/ + model_pipeline/）       │
│  MinIO hard-cases/ ← 分歧帧（自动）+ 误报帧（工位屏一键标记）    │
│  Celery 定时检查：新增 ≥ 200 张 → 触发 QLoRA 微调（RTX 4090）   │
│  TensorRT INT8 量化 → OTA 部署到 Jetson Orin NX                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、模块职责速查

| 模块路径 | 职责 | 部署位置 | 引入阶段 |
|----------|------|----------|----------|
| `src/services/sop_engine/` | SOP 生成、FSM 编译、版本管理 | 服务端 | Phase 1 |
| `src/services/compliance/` | VLM 深度推理、分歧检测、事件发布 | 服务端 | Phase 1 |
| `src/services/event_router/` | Kafka 消费、语义路由分发 | 服务端 | Phase 2 |
| `src/services/agents/` | LangGraph Agent（告警/根因/切换） | 服务端 | Phase 2 |
| `src/services/data_lake/` | 难例收集、伪标签打标、重训触发 | 服务端 | Phase 1（收集侧）|
| `src/adapters/` | 外部系统 I/O 封装（MinIO/Kafka/MES 等） | 服务端 | Phase 1 |
| `src/api/` | FastAPI 入口（REST + WebSocket） | 服务端 | Phase 1 |
| `edge_node/` | 实时视频推理、FSM 判定、PatchCore | Jetson Orin NX | Phase 1 |
| `model_pipeline/` | QLoRA 微调、TensorRT 量化、OTA 包生成 | 训练服务器（RTX 4090） | Phase 2 |
| `frontend/workstation/` | 工位交互屏（SOP 引导 + 误报标记） | 工位显示器 | Phase 1 |
| `frontend/dashboard/` | 管理看板（合规率 + 质检 + 根因报告） | 管理端浏览器 | Phase 1 |

---

## 四、关键数据流路径

### Fast Path（实时，< 25ms 端到端）
```
摄像头帧 → Jetson YOLOv10 推理 → FSM 判定 → [高置信] 本地日志
                                              → [明确违规] Kafka 事件
```

### Slow Path（深度推理，< 2s）
```
[不确定帧] gRPC 上传 → 服务端 VLM → 确诊/否决 → Kafka 事件 / 数据湖
```

### 飞轮路径（异步，每日触发）
```
数据湖 ≥ 200 新样本 → Celery 触发 QLoRA 微调（30-60min）
→ TensorRT INT8 量化 → MinIO models/ → Jetson OTA 热更新
```

### Human-in-Loop 路径（quality_root_cause Agent）
```
BATCH_DEFECT 事件 → LangGraph 多节点分析 → 根因报告挂起
→ 质量工程师看板确认 → Agent 恢复 → MES 工单创建
```

---

## 五、外部依赖清单

| 系统 | 类型 | 用途 |
|------|------|------|
| Qwen2.5-VL-7B（vLLM） | 本地部署 VLM | SOP 生成语义理解 + 合规深度推理 |
| DeepSeek-V3 / Qwen3-32B | API / 本地部署 LLM | Agent 推理（与 VLM 分开部署） |
| Milvus | 向量数据库 | SOP 知识库向量存储与召回 |
| TimescaleDB | 时序数据库 | 合规事件 90 天存储 + 趋势查询 |
| PostgreSQL | 关系数据库 | SOP 版本、数据湖元数据、零件批次 |
| MinIO | 对象存储 | 视频文件、难例帧、TensorRT 模型 |
| Kafka | 消息队列 | 合规事件异步传递（compliance.events topic）|
| Redis + Celery | 任务队列 | QLoRA 微调定时触发 |
| MES（客户系统） | 外部 REST API | 质量工单创建（Human-in-Loop 后触发）|

---

## 六、架构演进路线

| 阶段 | 部署形态 | 规模 |
|------|----------|------|
| Phase 1 PoC | Docker Compose 单机（`deployment/docker-compose/`） | 1 工厂，1-4 工位 |
| Phase 2 验证 | Docker Compose + Jetson 边缘 | 1 工厂，多工位 |
| Phase 3 SaaS | Kubernetes + Helm Charts（`deployment/helm-charts/`） | 多工厂，多租户隔离 |
