"""误报反馈接口 — 接收工位人员对合规告警的误报标记。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FalsePositiveRequest(BaseModel):
    event_id: str = Field(..., description="合规事件 ID")
    workstation_id: str = Field(..., description="工位 ID")
    operator_comment: str = Field("", description="操作员备注")


class FalsePositiveResponse(BaseModel):
    accepted: bool = True
    event_id: str
    received_at: str


@router.post(
    "/false-positive",
    response_model=FalsePositiveResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="标记合规告警为误报",
)
async def report_false_positive(body: FalsePositiveRequest) -> FalsePositiveResponse:
    """MVP 阶段仅记录日志，后续接入 Data Lake 的 feedback_events 表。"""
    logger.info(
        "误报反馈: event_id=%s workstation=%s comment=%r",
        body.event_id,
        body.workstation_id,
        body.operator_comment,
    )
    return FalsePositiveResponse(
        event_id=body.event_id,
        received_at=datetime.now(timezone.utc).isoformat(),
    )

