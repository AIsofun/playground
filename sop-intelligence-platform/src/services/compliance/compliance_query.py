"""合规 HTTP 查询侧编排：委托 ``PostgresComplianceEventsClient``，不含路由与 SQL 字符串拼装。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg

from src.adapters.storage.postgres_client import PostgresComplianceEventsClient
from src.types.events import ComplianceEvent, EventType


class ComplianceEventsStoreError(Exception):
    """合规事件存储不可用（如表未迁移、连接失败）。"""


@dataclass(frozen=True, slots=True)
class ComplianceSummary:
    """时间窗内事件计数与粗粒度「合规率」指标（非违规事件占比）。"""

    window_start_utc: datetime
    window_end_utc: datetime
    workstation_id: str | None
    total_events: int
    violation_events: int
    compliance_rate: float | None
    """``(total - violations) / total``；``total == 0`` 时为 ``None``。"""


class ComplianceQueryService:
    """只读查询；写入路径在慢路径 / Kafka 消费侧。"""

    def __init__(self, events_pg: PostgresComplianceEventsClient) -> None:
        self._events_pg = events_pg

    async def list_events(
        self,
        *,
        workstation_id: str | None,
        since: datetime | None,
        limit: int,
    ) -> list[ComplianceEvent]:
        try:
            return await self._events_pg.list_recent_events(
                workstation_id=workstation_id,
                since=since,
                limit=limit,
            )
        except asyncpg.UndefinedTableError as exc:
            raise ComplianceEventsStoreError(str(exc)) from exc

    async def summary(
        self,
        *,
        workstation_id: str | None,
        since_hours: int,
        now_utc: datetime | None = None,
    ) -> ComplianceSummary:
        end = now_utc or datetime.now(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)
        start = end - timedelta(hours=max(1, since_hours))
        try:
            total, violations = await self._events_pg.aggregate_violation_counts(
                workstation_id=workstation_id,
                since=start,
                violation_type=EventType.SOP_VIOLATION.value,
            )
        except asyncpg.UndefinedTableError as exc:
            raise ComplianceEventsStoreError(str(exc)) from exc
        rate: float | None
        if total == 0:
            rate = None
        else:
            rate = (total - violations) / total
        return ComplianceSummary(
            window_start_utc=start,
            window_end_utc=end,
            workstation_id=workstation_id,
            total_events=total,
            violation_events=violations,
            compliance_rate=rate,
        )
