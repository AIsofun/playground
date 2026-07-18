"""UNCERTAIN 慢路径编排：mock 端口，无真实 I/O。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.services.compliance.divergence_detector import DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY
from src.services.compliance.uncertain_frame_orchestrator import (
    SlowPathDependencies,
    UncertainFrameSlowPathOrchestrator,
)
from src.types.frames import ConfidenceLevel, UncertainFrameUpload
from src.types.models import InferenceResult, VlmComplianceVerdict


def _fixed_now() -> datetime:
    return datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)


def _upload() -> UncertainFrameUpload:
    return UncertainFrameUpload(
        workstation_id="ws-1",
        sop_id="sop-1",
        sop_step=2,
        captured_at=_fixed_now(),
        edge_confidence=0.55,
        edge_level=ConfidenceLevel.UNCERTAIN,
        frame_jpeg=b"\xff\xd8\xff",
        fsm_state="STEP_2",
    )


@pytest.fixture
def deps() -> SlowPathDependencies:
    vlm = AsyncMock()
    lake = AsyncMock()
    events = AsyncMock()
    lake.save_auto_divergence = AsyncMock(
        return_value="minio://hard-cases/ws-1/2026/04/15/u.jpg",
    )
    events.publish = AsyncMock(return_value=None)
    vlm.analyze_uncertain_frame = AsyncMock(
        return_value=VlmComplianceVerdict(
            is_anomaly=False,
            reason="",
            confidence=0.2,
        ),
    )
    return SlowPathDependencies(vlm=vlm, lake=lake, events=events)


def test_no_publish_when_vlm_clear_and_no_divergence(deps: SlowPathDependencies) -> None:
    orch = UncertainFrameSlowPathOrchestrator(deps)
    edge = InferenceResult(level=ConfidenceLevel.COMPLIANT, confidence=0.95)
    out = asyncio.run(
        orch.process(
            _upload(),
            edge,
            sop_step_context="ctx",
            clock=_fixed_now,
        ),
    )
    assert out.divergence.is_divergent is False
    assert out.event_published is False
    assert out.lake_path is None
    deps.lake.save_auto_divergence.assert_not_awaited()
    deps.events.publish.assert_not_awaited()


def test_publish_on_vlm_anomaly_without_divergence(deps: SlowPathDependencies) -> None:
    deps.vlm.analyze_uncertain_frame = AsyncMock(
        return_value=VlmComplianceVerdict(is_anomaly=True, reason="违规", confidence=0.9),
    )
    orch = UncertainFrameSlowPathOrchestrator(deps)
    edge = InferenceResult(level=ConfidenceLevel.VIOLATION, confidence=0.1)
    out = asyncio.run(
        orch.process(_upload(), edge, sop_step_context="ctx", clock=_fixed_now),
    )
    assert out.divergence.is_divergent is False
    assert out.event_published is True
    assert out.lake_path is None
    deps.lake.save_auto_divergence.assert_not_awaited()
    deps.events.publish.assert_awaited_once()
    ev = deps.events.publish.await_args.args[0]
    assert ev.event_type.value == "SOP_VIOLATION"
    assert ev.workstation_id == "ws-1"
    assert ev.frame_path == ""


def test_divergence_edge_compliant_vlm_anomaly_lake_then_kafka(
    deps: SlowPathDependencies,
) -> None:
    deps.vlm.analyze_uncertain_frame = AsyncMock(
        return_value=VlmComplianceVerdict(is_anomaly=True, reason="", confidence=0.88),
    )
    orch = UncertainFrameSlowPathOrchestrator(deps)
    edge = InferenceResult(level=ConfidenceLevel.COMPLIANT, confidence=0.95)
    out = asyncio.run(
        orch.process(_upload(), edge, sop_step_context="ctx", clock=_fixed_now),
    )
    assert out.divergence.is_divergent is True
    assert out.divergence.reason_code == DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY
    assert out.lake_path == "minio://hard-cases/ws-1/2026/04/15/u.jpg"
    assert out.event_published is True
    deps.lake.save_auto_divergence.assert_awaited_once()
    deps.events.publish.assert_awaited_once()
    assert deps.lake.save_auto_divergence.await_args.kwargs["reason_code"] == DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY
    ev = deps.events.publish.await_args.args[0]
    assert ev.frame_path == out.lake_path


def test_divergence_edge_violation_vlm_clear_lake_then_kafka(
    deps: SlowPathDependencies,
) -> None:
    deps.vlm.analyze_uncertain_frame = AsyncMock(
        return_value=VlmComplianceVerdict(is_anomaly=False, reason="", confidence=0.3),
    )
    orch = UncertainFrameSlowPathOrchestrator(deps)
    edge = InferenceResult(level=ConfidenceLevel.VIOLATION, confidence=0.1)
    out = asyncio.run(
        orch.process(_upload(), edge, sop_step_context="ctx", clock=_fixed_now),
    )
    assert out.divergence.is_divergent is True
    assert out.event_published is True
    deps.lake.save_auto_divergence.assert_awaited_once()
    deps.events.publish.assert_awaited_once()
