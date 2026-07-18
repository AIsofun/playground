# SPEC.md — SOP 智脑 任务追踪器

> **使用规则**：AI Agent 每次开始工作前读本文件，确认当前 Sprint 目标和进行中的 Todo ID，完成后在此标记。  
> **前端/JS 约束**：项目中所有涉及 JavaScript/TypeScript 的部分，**统一使用 pnpm** 进行依赖管理与验证（安装/构建/测试），禁止混用 npm/yarn。

---

## 当前 Sprint：Phase 1 — 建立核心产品

**目标**：完成 SOP 自动生成 Pipeline + 工位合规监控 MVP，找到首个 PoC 客户并交付。  
**截止节点**：Month 4（参考甘特图）

---

## Todo 列表

### 🟢 Phase 1（当前阶段）

| ID | 内容摘要 | 状态 | 对应模块 |
|----|----------|------|----------|
| `p1-sop-gen` | SOP 自动生成 Pipeline：专家视频 → VideoMAE 分段 → Qwen2.5-VL 语义理解 → 结构化 SOP 文档输出 | ✅ **Completed** | `src/services/sop_engine/` + `src/api/routes/sop.py` |
| `p1-sop-fsm` | SOP 状态机：`SOPToFSMCompiler` 将 `SOPDocument` 编译为 `FSMGraph`；`ActionDetector` + `FSMRunner` 运行态；`POST/GET /api/fsm/*` 持久化与查询；边缘 `edge_node/fsm_runtime/` 与 Eval Harness 见 Phase 2 backlog | ✅ **Completed** | `docs/module-specs/sop-fsm.md` · `src/types/fsm.py` · `src/services/fsm/*` · `src/api/routes/fsm.py` · `data/migrations/002_create_fsm_graphs.sql` |
| `p1-compliance` | 实时合规监控（三档置信度级联）：高置信丢弃 / 不确定截帧送 VLM / 明确违规直接告警；分歧自动入湖 | ✅ **Completed** | `docs/module-specs/compliance-service.md` · `src/services/compliance/` · `src/adapters/edge/` · `src/api/routes/compliance.py` · `data/migrations/003_create_data_lake_samples.sql` · `data/migrations/004_create_compliance_events.sql` · `tests/harness/compliance_eval/` |
| `p1-workstation-ui` | 工位交互屏：分步 SOP 视频引导 + 实时合规状态高亮 + "标记为误报"一键按钮 + 误报入湖闭环 | ✅ **Completed** | `frontend/workstation/` + `src/api/routes/feedback.py` |

### 🔵 Phase 2（数据飞轮，Month 5-9）

| ID | 内容摘要 | 状态 | 对应模块 |
|----|----------|------|----------|
| `p2-finetune` | 自动数据飞轮：数据湖收集分歧帧 + 误报帧 → 达到阈值自动触发 QLoRA 微调 → OTA 部署到 Jetson | `pending` | `src/services/data_lake/` + `model_pipeline/` |
| `p2-anomaly` | 装配质检增强：PatchCore 无监督异常检测（仅需良品图像），换型时零标注成本 | `pending` | `edge_node/anomaly/` |
| `p2-event-router` | 事件语义路由层：Kafka 消费 → 按语义分类 → 分发到对应 Agent | `pending` | `src/services/event_router/` |
| `p2-root-cause` | 质量根因 Agent（LangGraph 多节点）：批量缺陷 → 自动溯源 → 5W1H 报告 + Human-in-Loop → MES 工单 | `pending` | `src/services/agents/quality_root_cause.py` |

### ⚪ Phase 3（规模复制，Month 10-18）

| ID | 内容摘要 | 状态 | 对应模块 |
|----|----------|------|----------|
| `p3-knowledge-base` | SOP 知识库产品化：多产品版本管理、跨工位知识共享、新员工入职培训，独立 SaaS 定价 | `pending` | `src/services/sop_engine/version_manager.py` + `frontend/dashboard/` |
| `p3-saas` | SaaS 化：多租户隔离、边缘节点 OTA 热更新管理、用量计费，从单工厂复制到供应链工厂群 | `pending` | `deployment/helm-charts/` |

---

## 已完成里程碑

| 日期 | 里程碑 |
|------|--------|
| 2026-04-02 | ✅ 项目目录结构初始化（AI 原生 2026 标准） |
| 2026-04-02 | ✅ 全局 `AGENTS.md`（AI 宪法）生成完毕 |
| 2026-04-02 | ✅ `docs/architecture/overview.md` + `layering.md` 填充完毕 |
| 2026-04-02 | 🔄 `p1-sop-gen` 拆解为 T01–T10 共 10 个原子任务，写入 `docs/module-specs/sop-engine.md` |
| 2026-04-08 | ✅ **T03**（`video_parser.py`）：`MockVideoParser` + `tests/unit/test_sop_parser.py`，输出按 `start_time_sec` 升序；`docs/module-specs/sop-engine.md` 已勾选 |
| 2026-04-09 | ✅ **`p1-sop-gen` 完成**：E2E（`SOP_E2E=1`）+ `tests/harness/sop_gen_eval/run_eval.py` 质量门禁通过；`docs/module-specs/sop-engine.md` T01–T10 全 Done；契约见 `docs/architecture/adr/ADR-004-sop-gen-completed.md` |
| 2026-04-10 | 🔄 **`p1-sop-fsm` 拆解**：`docs/module-specs/sop-fsm.md` 写入 T01–T05（Types / `to_fsm` / 边缘运行时 / 单测 / Harness）；SPEC 本表与「子任务进度」已同步 |
| 2026-04-13 | ✅ **`p1-sop-fsm` 结案（Milestone 1-2）**：`sop-fsm.md` T01–T05 已勾选；类型/编译/运行态/API+PG 交付；`scripts/fsm_chain_smoke.py` 冒烟链；Eval Harness 与 `edge_node/fsm_runtime/` 列为 Phase 2 跟踪项 |
| 2026-04-13 | ✅ **`p1-workstation-ui` 结案（Phase 1）**：`workstation-ui.md` T01–T06 已勾选；`frontend/workstation/` 交付 `/demo`（T06 MockInterval + Mock/Real）、REST/WS Hooks、SOPPlayer/HUD/InstructionList；事件契约导出见 `docs/reports/workstation-ui-events-export.md` |
| 2026-04-14 | ✅ **`p1-compliance` 结案（Phase 1）**：三档级联与分歧入湖（MinIO + PostgreSQL）、边缘 `UNCERTAIN` 帧经 gRPC 入站、合规事件经 Kafka（`compliance.events`）；`compliance-service.md` 与 `tests/integration/README.md` 对齐；Harness `compliance_eval` 门禁通过；完成态与验收边界见 `docs/architecture/adr/ADR-005-p1-compliance-completed.md` |
| 2026-04-15 | ✅ **Phase 1 硬化（Demo-Ready）**：前端视觉微调（横向动画/骨架屏/WS 重连/AI 扫描线）+ 后端 Demo 种子路由（`/api/sop/demo` `/api/fsm/demo`）+ WS 工位推送 + 误报反馈 API + CORS + VLM 重试（3 次指数退避）+ FFmpeg 关键帧提取 + DemoVideoParser（4 步骤规则分段）+ 合规去抖动 + FSM 回退 + `.env` VLM 配置 + DevOps 一键启动脚本；单元测试 192 项通过，两项 Eval Harness 通过 |

## p1-sop-gen 子任务进度（摘录）

与 `docs/module-specs/sop-engine.md` 同步：**T01–T10** 均已标记 **`done`**。

## p1-workstation-ui 子任务进度（摘录）

与 `docs/module-specs/workstation-ui.md` 同步：**T01–T06** 均已 **`[x]` / 结案**（2026-04-13）；完整交互见 `frontend/workstation` 路由 **`/demo`**；误报按钮与 `feedback` API 联调列为后续迭代（SPEC 本行模块列已标注路径）。

| 任务 | 说明 |
|------|------|
| T01 | Vite + React + TS + Tailwind + shadcn 基建与 1080p 布局骨架 |
| T02 | `useSop` / `useFsmGraph` / `useWorkstationWs` + `.env` + 消息分发 |
| T03 | `SOPPlayer`：seek / 全屏 / 倍速 + 多候选视频源 |
| T04 | `InstructionList` + `InstructionCard` + `fsmStateToView` 联动 |
| T05 | `HudOverlay`（TIMEOUT / VIOLATION）+ WS 映射 |
| T06 | `MockIntervalRunner` + `DemoPage` Mock/Real 切换 |

## p1-sop-fsm 子任务进度（摘录）

与 `docs/module-specs/sop-fsm.md` 同步：**T01–T05** 均已 **`done` / 结案**（2026-04-13）；边缘与 Harness backlog 以该文档「合并标准」脚注为准。

| 任务 | 说明 |
|------|------|
| T01 | `src/types/fsm.py` — `FSMGraph` / `FSMNode` / `RuntimeContext` 等 |
| T02 | `src/services/fsm/compiler.py` — `SOPToFSMCompiler` |
| T03 | `src/services/fsm/detector.py` · `runtime.py` — `ActionDetector` + `FSMRunner`（边缘 `edge_node/fsm_runtime/` Phase 2） |
| T04 | `tests/unit/test_fsm_runner.py` 等 — 状态转换与并发 |
| T05 | `src/api/routes/fsm.py` + `PostgresFsmGraphsClient` + `tests/integration/test_fsm_graph_pipeline.py`（`sop_fsm_eval` Phase 2） |

---

## 开发优先级说明

```
当前聚焦：Phase 2 数据飞轮准备（`p2-finetune` 收集侧可在 Phase 1 启动，不等 Phase 2）
Phase 1 核心交付（`p1-sop-gen` / `p1-sop-fsm` / `p1-workstation-ui` / `p1-compliance`）均已 Completed（2026-04-14）
```

---

## 关键技术决策速查

| 决策点 | 选型 | ADR |
|--------|------|-----|
| VLM 引擎 | Qwen2.5-VL-7B via vLLM | `docs/architecture/adr/ADR-001-vlm-qwen.md` |
| 边缘传帧协议 | gRPC（frame_upload.proto） | `docs/architecture/adr/ADR-002-grpc.md` |
| 数据湖存储 | MinIO（S3 兼容，自托管） | `docs/architecture/adr/ADR-003-minio.md` |
| 置信度阈值 | LOW=0.4 / HIGH=0.7 | `src/config/vlm.py` + `docs/domain-logic.md` |
| Agent 框架 | LangGraph | `src/services/agents/AGENTS.md` |
| 边缘推理硬件 | Jetson Orin NX 16GB + TensorRT INT8 | `edge_node/AGENTS.md` |
| SOP 生成 Pipeline 契约（HTTP + 编排） | FastAPI `/api/sop/*` + Mock→正式模型可切换 | `docs/architecture/adr/ADR-004-sop-gen-completed.md` |
| Phase 1 合规监控结案（慢路径、集成门、Harness） | 分层 gRPC→服务编排→MinIO/PG/Kafka；集成用例环境变量门控 | `docs/architecture/adr/ADR-005-p1-compliance-completed.md` |
