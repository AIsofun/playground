"""T05 · FSM 编译落库端到端：SOPDocument → PostgreSQL ``fsm_graphs``。

**运行环境**

- 与 ``tests/integration/test_sop_pipeline.py`` 相同：PostgreSQL 已启动并执行
  ``data/migrations/001_create_sop_versions.sql`` 与 ``002_create_fsm_graphs.sql``。
- 本测试在模块启动时会 **幂等执行** ``002`` 的 ``CREATE TABLE IF NOT EXISTS``。

**运行示例**

```bash
export SOP_E2E=1
pytest tests/integration/test_fsm_graph_pipeline.py -v -m e2e
```
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from src.adapters.storage.postgres_client import PostgresFsmGraphsClient, PostgresSopVersionsClient
from src.config.storage import StorageSettings
from src.services.fsm.persist import FsmGraphPersistService
from src.types.fsm import FSM_TERMINAL_NODE_ID, FSM_START_NODE_ID
from src.types.sop import SOPDocument, SOPStep


def _env_dsn() -> str:
    return os.environ.get(
        "SOP_E2E_POSTGRES_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    )


def _e2e_opt_in() -> bool:
    return os.environ.get("SOP_E2E", "").lower() in ("1", "true", "yes", "on")


async def _probe_postgres(dsn: str) -> bool:
    try:
        conn = await asyncpg.connect(dsn, timeout=2.0)
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def e2e_pg() -> dict[str, Any]:
    if not _e2e_opt_in():
        pytest.skip("设置 SOP_E2E=1 以运行 FSM E2E（需 PostgreSQL）")
    dsn = _env_dsn()
    if not asyncio.run(_probe_postgres(dsn)):
        pytest.skip(f"PostgreSQL 不可达：{dsn!r}")
    return {"dsn": dsn, "settings": StorageSettings()}


async def _ensure_fsm_graphs_table(dsn: str) -> None:
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "migrations"
        / "002_create_fsm_graphs.sql"
    )
    sql = sql_path.read_text(encoding="utf-8")
    async with asyncpg.connect(dsn, timeout=10.0) as conn:
        await conn.execute(sql)


def _minimal_sop(product_id: str, version: str) -> SOPDocument:
    return SOPDocument(
        sop_id=str(uuid.uuid4()),
        product_id=product_id,
        version=version,
        steps=[
            SOPStep(
                step_id=1,
                description="步骤一",
                action_object="A",
                keyframe_path="minio://sop-keyframes/e2e/step_1.jpg",
                video_timestamp=10.0,
                action_type="action_alpha",
                warnings=[],
            ),
            SOPStep(
                step_id=2,
                description="步骤二",
                action_object="B",
                keyframe_path="minio://sop-keyframes/e2e/step_2.jpg",
                video_timestamp=25.0,
                action_type="action_beta",
                warnings=[],
            ),
        ],
        total_steps=2,
        created_at=datetime.now(timezone.utc),
        source_video_paths=["minio://sop-videos/e2e/demo.mp4"],
        status="draft",
    )


@pytest.mark.e2e
def test_fsm_compile_persist_and_roundtrip(e2e_pg: dict[str, Any]) -> None:
    """SOP 写入 sop_versions → 编译 FSM → fsm_graphs → 按 fsm_id / sop_id 读回。"""

    async def _run() -> None:
        dsn: str = e2e_pg["dsn"]
        settings: StorageSettings = e2e_pg["settings"]
        await _ensure_fsm_graphs_table(dsn)

        sop_pg = await PostgresSopVersionsClient.connect(
            dsn,
            table_name=settings.POSTGRES_TABLE_SOP_VERSIONS,
            min_size=1,
            max_size=4,
        )
        fsm_pg = await PostgresFsmGraphsClient.connect(
            dsn,
            table_name=settings.POSTGRES_TABLE_FSM_GRAPHS,
            min_size=1,
            max_size=4,
        )
        try:
            pid = f"FSM-E2E-{uuid.uuid4().hex[:8]}"
            ver = f"{pid}-v1.0"
            doc = _minimal_sop(pid, ver)
            await sop_pg.save_sop_version(doc)

            svc = FsmGraphPersistService(sop_pg, fsm_pg)
            fsm_id, graph = await svc.compile_and_store(
                doc.sop_id,
                expert_video_duration_sec=100.0,
            )
            assert FSM_START_NODE_ID in graph.nodes
            assert FSM_TERMINAL_NODE_ID in graph.nodes

            row = await fsm_pg.get_by_fsm_id(fsm_id)
            assert row is not None
            assert row.sop_id == doc.sop_id
            assert row.graph == graph

            latest = await fsm_pg.get_latest_by_sop_id(doc.sop_id)
            assert latest is not None
            assert latest.fsm_id == fsm_id

            async with asyncpg.connect(dsn, timeout=10.0) as conn:
                await conn.execute(
                    f'DELETE FROM "{settings.POSTGRES_TABLE_SOP_VERSIONS}" '
                    "WHERE sop_id = $1::uuid",
                    doc.sop_id,
                )
        finally:
            await fsm_pg.close()
            await sop_pg.close()

    asyncio.run(_run())
