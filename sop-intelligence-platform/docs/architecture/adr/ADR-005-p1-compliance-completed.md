# ADR-005: Phase 1 合规监控（`p1-compliance`）完成态与验收边界

## 状态

Accepted · 2026-04-14  

**范围**：`p1-compliance` — 服务端合规**慢路径**（三档置信度、VLM 编排形状、数据湖写入、Kafka 事件、HTTP 查询）；与 `ADR-002-grpc.md` 所述边缘 gRPC 入站衔接。

## 背景

工位侧 Fast Path 已产出分数 \(s\) 与三档分类；服务端需在不破坏分层的前提下，对 **`UNCERTAIN`** 路径做复核与事件外发，对 **`HIGH`/`LOW` 分歧** 自动入湖，并为运营与 Harness 提供可重复的验收命令。

## 决策摘要

1. **分层**：`src/adapters/edge/` 仅做 gRPC I/O；三档与分歧、MinIO/PG/Kafka 编排留在 `src/services/compliance/`；`src/api/routes/compliance.py` 仅编排与 DTO，不直连存储。
2. **领域阈值真源**：`CONF_LOW` / `CONF_HIGH` 定义于 `src/config/vlm.py`，语义见 `docs/domain-logic.md`（不在服务层硬编码魔法数）。
3. **集成测试门**：`tests/integration/test_compliance_pipeline.py` 依赖真实 PostgreSQL、MinIO、Kafka（Redpanda）；通过环境变量 **`COMPLIANCE_E2E=1`**、**`COMPLIANCE_PIPELINE_E2E=1`** 显式开启，未开启时跳过，避免本地误连。
4. **质量 Harness**：`tests/harness/compliance_eval/run_eval.py` 使用冻结字段模拟 VLM 输出，门禁对齐 `docs/eval-standards.md`（Recall、FPR、UNCERTAIN 比例）；修改 Prompt 或阈值后须重跑 Harness 并视情况更新数据集。
5. **迁移**：数据湖样本与合规事件元数据分别见 `data/migrations/003_create_data_lake_samples.sql`、`data/migrations/004_create_compliance_events.sql`（以仓库内 DDL 为真源）。

## 后果

- **边缘节点**：仍须遵守 `edge_node/AGENTS.md` 实时性约束；服务端慢路径扩容不改变 Jetson 主线程无阻塞网络 I/O 的约束。
- **Phase 2**：在线 VLM 评测接入 Harness 时，应保持 `metrics.py` 门禁与事件 schema 兼容，或新增 ADR 说明契约变更。

## 参考实现路径

| 契约层 | 代码 / 文档 |
|--------|-------------|
| 模块规格 | `docs/module-specs/compliance-service.md` |
| gRPC 协议 | `proto/frame_upload.proto`，`src/adapters/edge/grpc_server.py` |
| 合规服务 | `src/services/compliance/` |
| HTTP 路由 | `src/api/routes/compliance.py` |
| 存储与消息适配器 | `src/adapters/storage/data_lake_sample_store.py`，`src/adapters/messaging/kafka_producer.py` |
| 集成说明 | `tests/integration/README.md` |
| Harness | `tests/harness/compliance_eval/README.md` |
