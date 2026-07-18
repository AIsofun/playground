"""合规只读 HTTP 路由（MVP）：事件列表、汇总、健康检查。

委托 ``ComplianceQueryService`` + ``PostgresComplianceEventsClient``；
本文件禁止直接 SQL（见 ``docs/module-specs/compliance-service.md`` §8）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.services.compliance.compliance_query import (
    ComplianceEventsStoreError,
    ComplianceQueryService,
    ComplianceSummary,
)
from src.types.events import ComplianceEvent

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _error_detail(
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if extra:
        body["details"] = extra
    return body


def _get_compliance_query(request: Request) -> ComplianceQueryService | None:
    return getattr(request.app.state, "compliance_query", None)


class ComplianceHealthResponse(BaseModel):
    """进程内模块存活；``events_store_configured`` 表示是否已挂 PG 查询客户端。"""

    status: Literal["ok"] = Field(default="ok", description="路由模块可用")
    events_store_configured: bool = Field(
        ...,
        description="已为 ``compliance_events`` 初始化查询服务（需 SOP_POSTGRES_DSN + 迁移）",
    )


class ComplianceSummaryResponse(BaseModel):
    """时间窗聚合，与 ``ComplianceSummary`` 对齐。"""

    window_start_utc: datetime
    window_end_utc: datetime
    workstation_id: str | None
    total_events: int
    violation_events: int
    compliance_rate: float | None = Field(
        default=None,
        description="(total_events - violation_events) / total_events；无事件时为 null",
    )


def _summary_to_response(s: ComplianceSummary) -> ComplianceSummaryResponse:
    return ComplianceSummaryResponse(
        window_start_utc=s.window_start_utc,
        window_end_utc=s.window_end_utc,
        workstation_id=s.workstation_id,
        total_events=s.total_events,
        violation_events=s.violation_events,
        compliance_rate=s.compliance_rate,
    )


@router.get(
    "/health",
    response_model=ComplianceHealthResponse,
    summary="合规 API 模块健康检查",
)
async def compliance_health(request: Request) -> ComplianceHealthResponse:
    q = _get_compliance_query(request)
    return ComplianceHealthResponse(events_store_configured=q is not None)


@router.get(
    "/events",
    response_model=list[ComplianceEvent],
    summary="合规事件列表（倒序）",
)
async def list_compliance_events(
    request: Request,
    workstation_id: str | None = Query(
        default=None,
        description="按工位过滤；缺省为全量（仍受 limit 约束）",
    ),
    limit: int = Query(default=50, ge=1, le=500, description="最大返回条数"),
    since: datetime | None = Query(
        default=None,
        description="仅返回该时间（含）之后的事件；UTC",
    ),
) -> list[ComplianceEvent]:
    svc = _get_compliance_query(request)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "storage_unavailable",
                "未配置 SOP_POSTGRES_DSN 或未初始化合规事件查询客户端",
            ),
        )
    try:
        return await svc.list_events(
            workstation_id=workstation_id,
            since=since,
            limit=limit,
        )
    except ComplianceEventsStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "compliance_store_unavailable",
                "无法读取 compliance_events（表缺失或未迁移）",
                extra={"reason": str(exc)},
            ),
        ) from exc


@router.get(
    "/summary",
    response_model=ComplianceSummaryResponse,
    summary="时间窗内事件计数与合规率（粗粒度）",
)
async def compliance_summary(
    request: Request,
    workstation_id: str | None = Query(default=None, description="按工位过滤"),
    since_hours: int = Query(
        default=24,
        ge=1,
        le=24 * 90,
        description="统计窗口长度（小时），相对当前服务端 UTC 时间",
    ),
) -> ComplianceSummaryResponse:
    svc = _get_compliance_query(request)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "storage_unavailable",
                "未配置 SOP_POSTGRES_DSN 或未初始化合规事件查询客户端",
            ),
        )
    try:
        s = await svc.summary(
            workstation_id=workstation_id,
            since_hours=since_hours,
        )
    except ComplianceEventsStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "compliance_store_unavailable",
                "无法读取 compliance_events（表缺失或未迁移）",
                extra={"reason": str(exc)},
            ),
        ) from exc
    return _summary_to_response(s)
