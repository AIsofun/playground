# 集成测试说明（`tests/integration/`）

与根目录 `AGENTS.md` 一致：本目录用例依赖 **真实外部服务**（PostgreSQL、MinIO、Kafka 等），须通过 **环境变量显式开启**，避免在未启动 Docker 时拖慢或误连局域网。

## 1. 启动依赖（Docker Compose）

在项目根目录执行：

```bash
docker compose -f deploy/docker-compose.integration.yml up -d
```

默认暴露端口：

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | `5432` | 用户/库/密码均为 `postgres` |
| MinIO | `9000`（控制台 `9001`） | `minioadmin` / `minioadmin` |
| Redpanda（Kafka API） | `19092` | 与 `kafka-python` 兼容 |

停止并删除卷：

```bash
docker compose -f deploy/docker-compose.integration.yml down -v
```

**Windows PowerShell** 示例（路径含 `&` 时请给路径加引号）：

```powershell
Set-Location "f:\code\myCode\Agent&MCP&Skills\sop-intelligence-platform"
docker compose -f deploy/docker-compose.integration.yml up -d
```

## 2. 测试套件与开关

### 2.1 数据湖写入（MinIO + PostgreSQL）

- 文件：`test_compliance_pipeline.py` → `test_auto_divergence_minio_and_postgres`
- 开启：`COMPLIANCE_E2E=1`
- 可选环境变量：见 `test_compliance_pipeline.py` 顶部注释（`COMPLIANCE_E2E_POSTGRES_DSN`、`COMPLIANCE_E2E_MINIO_*`）
- 运行前请在库中执行迁移 `data/migrations/003_create_data_lake_samples.sql`（或依赖测试内联 DDL）

### 2.2 边缘帧 → gRPC → Mock VLM → Kafka

- 文件：`test_compliance_pipeline.py` → `test_grpc_uncertain_frame_triggers_kafka_compliance_event`
- 开启：`COMPLIANCE_PIPELINE_E2E=1`
- Kafka 地址：`COMPLIANCE_PIPELINE_KAFKA_BOOTSTRAP`（默认 `127.0.0.1:19092`，与 Compose 中 Redpanda 映射一致）
- Topic 名：与 `src/config/kafka.py` 中 `TOPIC_COMPLIANCE_EVENTS` 一致（默认 `compliance.events`），由 Redpanda 在首次生产时自动建 topic 即可

## 3. pytest 命令

**统一标记**：集成用例均带 `@pytest.mark.integration`。

```bash
# 仅跑 integration 标记（未设环境变量时会 skip）
pytest tests/integration/ -m integration -v

# 数据湖 E2E
export COMPLIANCE_E2E=1
pytest tests/integration/test_compliance_pipeline.py -m integration -v -k auto_divergence

# gRPC + Kafka 流水线 E2E
export COMPLIANCE_PIPELINE_E2E=1
pytest tests/integration/test_compliance_pipeline.py -m integration -k grpc_uncertain
```

**CI 建议**：在 job 中 `docker compose -f deploy/docker-compose.integration.yml up -d`，轮询 `pg_isready` / `kafka` 端口就绪后再执行上述 `pytest`，并导出所需 `COMPLIANCE_*` 变量。
