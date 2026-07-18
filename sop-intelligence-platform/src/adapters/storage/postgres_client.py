"""PostgreSQL（asyncpg 连接池）中 ``sop_versions`` / ``fsm_graphs`` 表的 I/O 封装。

仅执行参数化 SQL 与 Pydantic 序列化/反序列化，不包含版本策略等业务逻辑。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import asyncpg

from src.types.events import ComplianceEvent, EventType
from src.types.fsm import FSMGraph
from src.types.sop import SOPDocument

_TABLE_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_table_identifier(table_name: str) -> str:
    """将已通过校验的表名安全地放入双引号标识符中。"""
    return '"' + table_name.replace('"', '""') + '"'


class PostgresSopVersionsClient:
    """在连接池上执行 SOP 版本快照的插入与按主键查询。"""

    def __init__(self, pool: asyncpg.Pool, table_name: str) -> None:
        if _TABLE_IDENT.fullmatch(table_name) is None:
            raise ValueError(f"Invalid PostgreSQL table identifier: {table_name!r}")
        self._pool = pool
        self._table_sql = _quote_table_identifier(table_name)
        self._insert_sql = (
            f"INSERT INTO {self._table_sql} "
            "(sop_id, product_id, version, status, content_json, created_at) "
            "VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6) "
            "RETURNING sop_id::text"
        )
        self._select_sql = (
            f"SELECT content_json FROM {self._table_sql} WHERE sop_id = $1::uuid"
        )

    @classmethod
    async def connect(
        cls,
        dsn: str,
        *,
        table_name: str,
        min_size: int = 1,
        max_size: int = 10,
    ) -> PostgresSopVersionsClient:
        """创建 asyncpg 连接池并绑定表名。禁止在请求路径上每次新建连接，应复用本客户端。"""
        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        return cls(pool, table_name)

    async def close(self) -> None:
        """关闭连接池。"""
        await self._pool.close()

    async def save_sop_version(self, doc: SOPDocument) -> str:
        """写入完整 ``SOPDocument`` 快照，返回 ``sop_id`` 字符串。"""
        payload = doc.model_dump(mode="json")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                self._insert_sql,
                doc.sop_id,
                doc.product_id,
                doc.version,
                doc.status,
                payload,
                doc.created_at,
            )
        return row["sop_id"]

    async def get_sop_by_id(self, sop_id: str) -> SOPDocument | None:
        """按主键读取 ``content_json`` 并还原为 ``SOPDocument``；不存在则返回 ``None``。"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(self._select_sql, sop_id)
        return SOPDocument.model_validate(row["content_json"]) if row is not None else None


@dataclass(frozen=True, slots=True)
class FsmGraphRow:
    """``fsm_graphs`` 表一行映射到领域类型。"""

    fsm_id: str
    sop_id: str
    product_id: str
    version: str
    expert_video_duration_sec: float
    graph: FSMGraph


class PostgresFsmGraphsClient:
    """在连接池上执行 FSM 拓扑 JSON 的插入与按 ``fsm_id`` / ``sop_id`` 查询。"""

    def __init__(self, pool: asyncpg.Pool, table_name: str) -> None:
        if _TABLE_IDENT.fullmatch(table_name) is None:
            raise ValueError(f"Invalid PostgreSQL table identifier: {table_name!r}")
        self._pool = pool
        self._table_sql = _quote_table_identifier(table_name)
        self._insert_sql = (
            f"INSERT INTO {self._table_sql} "
            "(sop_id, product_id, version, expert_video_duration_sec, graph_json) "
            "VALUES ($1::uuid, $2, $3, $4, $5::jsonb) "
            "RETURNING fsm_id::text"
        )
        self._select_by_fsm_sql = (
            f"SELECT fsm_id::text, sop_id::text, product_id, version, "
            f"expert_video_duration_sec, graph_json "
            f"FROM {self._table_sql} WHERE fsm_id = $1::uuid"
        )
        self._select_latest_sop_sql = (
            f"SELECT fsm_id::text, sop_id::text, product_id, version, "
            f"expert_video_duration_sec, graph_json "
            f"FROM {self._table_sql} WHERE sop_id = $1::uuid "
            f"ORDER BY created_at DESC LIMIT 1"
        )

    @classmethod
    async def connect(
        cls,
        dsn: str,
        *,
        table_name: str,
        min_size: int = 1,
        max_size: int = 10,
    ) -> PostgresFsmGraphsClient:
        """创建 asyncpg 连接池并绑定 ``fsm_graphs`` 表名。"""
        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        return cls(pool, table_name)

    async def close(self) -> None:
        """关闭连接池。"""
        await self._pool.close()

    async def insert_graph(
        self,
        *,
        sop_id: str,
        product_id: str,
        version: str,
        expert_video_duration_sec: float,
        graph: FSMGraph,
    ) -> str:
        """插入编译后的 ``FSMGraph``，返回 ``fsm_id`` 字符串。"""
        payload = graph.model_dump(mode="json")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                self._insert_sql,
                sop_id,
                product_id,
                version,
                expert_video_duration_sec,
                payload,
            )
        return row["fsm_id"]

    def _row_to_domain(self, row: asyncpg.Record) -> FsmGraphRow:
        return FsmGraphRow(
            fsm_id=row["fsm_id"],
            sop_id=row["sop_id"],
            product_id=row["product_id"],
            version=row["version"],
            expert_video_duration_sec=float(row["expert_video_duration_sec"]),
            graph=FSMGraph.model_validate(row["graph_json"]),
        )

    async def get_by_fsm_id(self, fsm_id: str) -> FsmGraphRow | None:
        """按 ``fsm_id`` 读取一行；不存在返回 ``None``。"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(self._select_by_fsm_sql, fsm_id)
        return self._row_to_domain(row) if row is not None else None

    async def get_latest_by_sop_id(self, sop_id: str) -> FsmGraphRow | None:
        """按 ``sop_id`` 取最近一次编译的 FSM；不存在返回 ``None``。"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(self._select_latest_sop_sql, sop_id)
        return self._row_to_domain(row) if row is not None else None


class PostgresDataLakeSamplesClient:
    """``data_lake_samples`` 表：难例 / 分歧帧元数据索引（参数化 SQL，无业务分支）。"""

    def __init__(self, pool: asyncpg.Pool, table_name: str) -> None:
        if _TABLE_IDENT.fullmatch(table_name) is None:
            raise ValueError(f"Invalid PostgreSQL table identifier: {table_name!r}")
        self._pool = pool
        self._table_sql = _quote_table_identifier(table_name)
        self._insert_sql = (
            f"INSERT INTO {self._table_sql} "
            "(sample_id, frame_path, label, sop_step, workstation_id, source, "
            "recorded_at, sop_id, reason_code) "
            "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)"
        )

    @classmethod
    async def connect(
        cls,
        dsn: str,
        *,
        table_name: str,
        min_size: int = 1,
        max_size: int = 10,
    ) -> PostgresDataLakeSamplesClient:
        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        return cls(pool, table_name)

    async def close(self) -> None:
        await self._pool.close()

    async def insert_auto_sample(
        self,
        *,
        sample_id: uuid.UUID,
        frame_path: str,
        label: str,
        sop_step: int,
        workstation_id: str,
        source: Literal["auto", "manual"],
        recorded_at: datetime,
        sop_id: str,
        reason_code: str | None,
    ) -> None:
        """插入一行；违反唯一约束等数据库错误将原样抛出。"""
        async with self._pool.acquire() as conn:
            await conn.execute(
                self._insert_sql,
                sample_id,
                frame_path,
                label,
                sop_step,
                workstation_id,
                source,
                recorded_at,
                sop_id,
                reason_code,
            )


class PostgresComplianceEventsClient:
    """``compliance_events`` 表只读查询；参数化 SQL，无合规业务分支。"""

    def __init__(self, pool: asyncpg.Pool, table_name: str) -> None:
        if _TABLE_IDENT.fullmatch(table_name) is None:
            raise ValueError(f"Invalid PostgreSQL table identifier: {table_name!r}")
        self._pool = pool
        self._table_sql = _quote_table_identifier(table_name)
        self._list_sql = (
            f'SELECT "timestamp", workstation_id, event_type, sop_step, frame_path, confidence '
            f"FROM {self._table_sql} "
            f"WHERE ($1::text IS NULL OR workstation_id = $1) "
            f'AND ($2::timestamptz IS NULL OR "timestamp" >= $2) '
            f'ORDER BY "timestamp" DESC '
            f"LIMIT $3"
        )
        self._aggregate_sql = (
            f"SELECT COUNT(*)::bigint AS total, "
            f"SUM(CASE WHEN event_type = $3 THEN 1 ELSE 0 END)::bigint AS violations "
            f"FROM {self._table_sql} "
            f"WHERE ($1::text IS NULL OR workstation_id = $1) "
            f'AND "timestamp" >= $2'
        )

    @classmethod
    async def connect(
        cls,
        dsn: str,
        *,
        table_name: str,
        min_size: int = 1,
        max_size: int = 10,
    ) -> PostgresComplianceEventsClient:
        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        return cls(pool, table_name)

    async def close(self) -> None:
        await self._pool.close()

    async def list_recent_events(
        self,
        *,
        workstation_id: str | None,
        since: datetime | None,
        limit: int,
    ) -> list[ComplianceEvent]:
        """按时间倒序返回最近 ``limit`` 条；列语义与 ``ComplianceEvent`` 一致。"""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                self._list_sql,
                workstation_id,
                since,
                limit,
            )
        out: list[ComplianceEvent] = []
        for row in rows:
            out.append(
                ComplianceEvent(
                    timestamp=row["timestamp"],
                    workstation_id=row["workstation_id"],
                    event_type=EventType(row["event_type"]),
                    sop_step=int(row["sop_step"]),
                    frame_path=row["frame_path"] or "",
                    confidence=float(row["confidence"]),
                )
            )
        return out

    async def aggregate_violation_counts(
        self,
        *,
        workstation_id: str | None,
        since: datetime,
        violation_type: str = EventType.SOP_VIOLATION.value,
    ) -> tuple[int, int]:
        """返回 ``(total_events, violation_events)``；``violation_type`` 与 ``event_type`` 列匹配。"""
        viol = str(violation_type)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                self._aggregate_sql,
                workstation_id,
                since,
                viol,
            )
        assert row is not None
        total = int(row["total"] or 0)
        violations = int(row["violations"] or 0)
        return total, violations
