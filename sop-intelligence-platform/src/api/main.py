"""FastAPI 应用入口 — 供 ``uvicorn src.api.main:app`` 启动。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapters.storage.minio_client import MinioStorageClient
from src.adapters.storage.postgres_client import (
    PostgresComplianceEventsClient,
    PostgresFsmGraphsClient,
    PostgresSopVersionsClient,
)
from src.api.routes import compliance as compliance_routes
from src.api.routes import feedback as feedback_routes
from src.api.routes import fsm as fsm_routes
from src.api.routes import sop as sop_routes
from src.api.websocket import workstation as ws_workstation
from src.services.compliance.compliance_query import ComplianceQueryService
from src.config.storage import get_storage_settings
from src.services.sop_engine.version_manager import VersionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """按需连接 PostgreSQL / MinIO，挂载 ``VersionManager``；未配置时 ``generate`` 返回 503。"""
    dsn = os.environ.get("SOP_POSTGRES_DSN", "").strip()
    settings = get_storage_settings()
    pg_client: PostgresSopVersionsClient | None = None
    fsm_pg_client: PostgresFsmGraphsClient | None = None
    compliance_pg_client: PostgresComplianceEventsClient | None = None
    if dsn:
        pg_client = await PostgresSopVersionsClient.connect(
            dsn,
            table_name=settings.POSTGRES_TABLE_SOP_VERSIONS,
        )
        fsm_pg_client = await PostgresFsmGraphsClient.connect(
            dsn,
            table_name=settings.POSTGRES_TABLE_FSM_GRAPHS,
        )
        compliance_pg_client = await PostgresComplianceEventsClient.connect(
            dsn,
            table_name=settings.POSTGRES_TABLE_COMPLIANCE_EVENTS,
        )
        endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000").strip()
        access = os.environ.get("MINIO_ACCESS_KEY", "minioadmin").strip()
        secret = os.environ.get("MINIO_SECRET_KEY", "minioadmin").strip()
        secure = os.environ.get("MINIO_SECURE", "").lower() in ("1", "true", "yes")
        minio = MinioStorageClient.from_connection(
            endpoint,
            access,
            secret,
            keyframes_bucket=settings.MINIO_BUCKET_SOP_KEYFRAMES,
            videos_bucket=settings.MINIO_BUCKET_SOP_VIDEOS,
            secure=secure,
        )
        app.state.version_manager = VersionManager(minio=minio, postgres=pg_client)
        app.state.fsm_graphs_client = fsm_pg_client
        app.state.compliance_events_pg = compliance_pg_client
        app.state.compliance_query = ComplianceQueryService(compliance_pg_client)
    else:
        app.state.version_manager = None
        app.state.fsm_graphs_client = None
        app.state.compliance_events_pg = None
        app.state.compliance_query = None
    yield
    if compliance_pg_client is not None:
        await compliance_pg_client.close()
    if fsm_pg_client is not None:
        await fsm_pg_client.close()
    if pg_client is not None:
        await pg_client.close()


app = FastAPI(title="SOP Intelligence Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sop_routes.router, prefix="/api")
app.include_router(fsm_routes.router, prefix="/api")
app.include_router(compliance_routes.router, prefix="/api")
app.include_router(feedback_routes.router, prefix="/api")
app.include_router(ws_workstation.router)
