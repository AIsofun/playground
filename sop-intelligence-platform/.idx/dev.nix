# IDX / Nix 沙盒 — SOP Pipeline E2E（T10）
#
# 本文件为 Project IDX 工作区环境定义。集成测试 `tests/integration/test_sop_pipeline.py`
# 需要 **MinIO** 与 **PostgreSQL**（可先 `docker compose up` 或于云端预置服务）。
# 若本机启动较慢，请在 IDX 中使用 **Push to Cloud**，在云端沙盒中运行：
#   pytest tests/integration/test_sop_pipeline.py -v -m e2e
#
# 数据库请先应用迁移：data/migrations/001_create_sop_versions.sql

{ pkgs, ... }: {
  channel = "stable-24.11";

  packages = [
    pkgs.python312
  ];

  # 与测试默认值一致；云端/Compose 中请按实际服务端点修改。
  env = {
    SOP_E2E = "1";
    SOP_E2E_POSTGRES_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/postgres";
    SOP_E2E_MINIO_ENDPOINT = "127.0.0.1:9000";
    SOP_E2E_MINIO_ACCESS_KEY = "minioadmin";
    SOP_E2E_MINIO_SECRET_KEY = "minioadmin";
  };
}
