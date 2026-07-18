"""UNCERTAIN 帧慢路径编排：VLM 复核 → 分歧检测 →（可选）入湖与 Kafka。

本模块只做 **services 层编排**；网络 / 存储 / Kafka 的具体 I/O 由注入的
端口（Protocol）委托给 ``src/adapters/`` 实现（见 ``docs/architecture/layering.md``）。

约束：
    - 禁止直接 ``from kafka import ...`` 或实例化 Kafka 客户端；事件发布须经由
      ``ComplianceEventPublisherPort``（由 adapter 内部调用 ``kafka_producer``）。
    - 禁止在本文件内发起裸 HTTP；VLM 调用仅通过 ``VlmComplianceClientPort``。

必读契约：``docs/module-specs/compliance-service.md``、
``src/services/compliance/AGENTS.md``。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from pydantic import BaseModel, Field

from src.services.compliance.divergence_detector import DivergenceResult, detect_divergence
from src.types.events import ComplianceEvent, EventType
from src.types.frames import UncertainFrameUpload
from src.types.models import InferenceResult, VlmComplianceVerdict


class VlmComplianceClientPort(Protocol):
    """由 adapter 实现：加载 anomaly Prompt、调用 vLLM 并解析为 ``VlmComplianceVerdict``。"""

    async def analyze_uncertain_frame(
        self,
        *,
        upload: UncertainFrameUpload,
        sop_step_context: str,
    ) -> VlmComplianceVerdict:
        ...


class DataLakeWriterPort(Protocol):
    """由 adapter 实现：MinIO 字节写入 + PG 元数据（须满足 AGENTS 原子/补偿策略）。"""

    async def save_auto_divergence(
        self,
        *,
        upload: UncertainFrameUpload,
        vlm_verdict: VlmComplianceVerdict,
        reason_code: str,
    ) -> str:
        """返回 ``minio://`` 帧路径。"""
        ...


class ComplianceEventPublisherPort(Protocol):
    """由 adapter 实现：内部应调用 ``src/adapters/messaging/kafka_producer``。"""

    async def publish(self, event: ComplianceEvent) -> None:
        ...


@dataclass(frozen=True, slots=True)
class SlowPathDependencies:
    """编排所需外部能力（单测注入 AsyncMock / 假实现）。"""

    vlm: VlmComplianceClientPort
    lake: DataLakeWriterPort
    events: ComplianceEventPublisherPort


class UncertainFrameSlowPathOutcome(BaseModel):
    """一次慢路径执行的可观测结果（便于单测断言）。"""

    vlm_verdict: VlmComplianceVerdict
    divergence: DivergenceResult
    lake_path: str | None = Field(
        default=None,
        description="分歧入湖后的 minio:// 路径；未分歧或未写湖时为 None",
    )
    event_published: bool = Field(
        default=False,
        description="是否已向 Kafka 发布合规事件",
    )


def _should_publish_kafka(*, vlm: VlmComplianceVerdict, divergence: DivergenceResult) -> bool:
    """MVP：VLM 判异常或存在大小模型分歧时，对外发布 ``SOP_VIOLATION`` 类事件。"""
    return bool(vlm.is_anomaly or divergence.is_divergent)


def _build_compliance_event(
    *,
    upload: UncertainFrameUpload,
    vlm: VlmComplianceVerdict,
    frame_path: str,
    now: datetime,
) -> ComplianceEvent:
    """构造 ``compliance.events`` 载荷；置信度语义固定为 VLM ``confidence``。"""
    return ComplianceEvent(
        timestamp=now,
        workstation_id=upload.workstation_id,
        event_type=EventType.SOP_VIOLATION,
        sop_step=upload.sop_step,
        frame_path=frame_path,
        confidence=float(vlm.confidence),
    )


class UncertainFrameSlowPathOrchestrator:
    """串联：上下文 → VLM → 分歧 →（条件）入湖 + Kafka。"""

    def __init__(self, deps: SlowPathDependencies) -> None:
        self._deps = deps

    async def process(
        self,
        upload: UncertainFrameUpload,
        edge_inference: InferenceResult,
        *,
        sop_step_context: str,
        clock: Callable[[], datetime] | None = None,
    ) -> UncertainFrameSlowPathOutcome:
        """``edge_inference`` 用于分歧检测（可与 ``upload.edge_level`` 的传输语义不同）。

        调用方应传入边缘在慢路径判定时刻的推断快照；若仅传输 UNCERTAIN 档，
        仍可用独立字段表达边缘对合规三档的并行估计。
        """
        _now = clock if clock is not None else (lambda: datetime.now(timezone.utc))

        vlm_verdict = await self._deps.vlm.analyze_uncertain_frame(
            upload=upload,
            sop_step_context=sop_step_context,
        )
        divergence = detect_divergence(edge_inference, vlm_verdict)

        lake_path: str | None = None
        if divergence.is_divergent:
            lake_path = await self._deps.lake.save_auto_divergence(
                upload=upload,
                vlm_verdict=vlm_verdict,
                reason_code=divergence.reason_code or "",
            )

        event_published = False
        if _should_publish_kafka(vlm=vlm_verdict, divergence=divergence):
            path_for_event = lake_path if lake_path is not None else ""
            event = _build_compliance_event(
                upload=upload,
                vlm=vlm_verdict,
                frame_path=path_for_event,
                now=_now(),
            )
            await self._deps.events.publish(event)
            event_published = True

        return UncertainFrameSlowPathOutcome(
            vlm_verdict=vlm_verdict,
            divergence=divergence,
            lake_path=lake_path,
            event_published=event_published,
        )


__all__ = [
    "ComplianceEventPublisherPort",
    "DataLakeWriterPort",
    "SlowPathDependencies",
    "UncertainFrameSlowPathOrchestrator",
    "UncertainFrameSlowPathOutcome",
    "VlmComplianceClientPort",
]
