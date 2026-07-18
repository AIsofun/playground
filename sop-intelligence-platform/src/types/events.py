"""
事件与路由载荷类型 — src/types/events.py
=========================================

Kafka ``compliance.events`` 等契约见 ``docs/module-specs/compliance-service.md`` §4。

架构约束：仅标准库 + pydantic；禁止 import services、adapters、api。
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# EventType — Kafka event_type 枚举
# ---------------------------------------------------------------------------


class EventType(str, enum.Enum):
    """合规及相关事件类型（字符串值与 Kafka JSON 一致）。"""

    SOP_VIOLATION = "SOP_VIOLATION"
    BATCH_DEFECT = "BATCH_DEFECT"
    MODEL_CHANGEOVER = "MODEL_CHANGEOVER"


# ---------------------------------------------------------------------------
# ComplianceEvent — compliance.events 消息体
# ---------------------------------------------------------------------------


class ComplianceEvent(BaseModel):
    """发布至 Kafka ``compliance.events`` 的 JSON 对象（字段名与 module-spec 一致）。"""

    timestamp: datetime = Field(..., description="ISO8601 UTC 序列化")
    workstation_id: str = Field(..., min_length=1)
    event_type: EventType
    sop_step: int = Field(..., ge=0)
    frame_path: str = Field(
        default="",
        description="minio://bucket/key；无帧时为空字符串",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="事件语义绑定的标量置信度（实现层固定含义）",
    )


# ---------------------------------------------------------------------------
# AnomalyEvent / RouteEvent — Phase 2+ 占位模型
# ---------------------------------------------------------------------------


class AnomalyEvent(BaseModel):
    """质检 / PatchCore 等异常事件（与合规 Kafka  topic 分离前的载荷草图）。"""

    timestamp: datetime
    workstation_id: str = Field(..., min_length=1)
    defect_class: str = Field(default="unknown", min_length=1)
    severity: float = Field(default=1.0, ge=0.0, le=1.0)


class RouteEvent(BaseModel):
    """事件路由器输出侧最小字段（供 ``event_router`` 实现填充）。"""

    timestamp: datetime
    inbound_topic: str = Field(..., min_length=1)
    routed_to: str = Field(..., min_length=1, description="目标 Agent 或 sink 标识")
