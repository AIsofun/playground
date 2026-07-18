"""合规相关 ``src/types`` 导入与基础校验。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.types.events import ComplianceEvent, EventType
from src.types.frames import (
    ConfidenceLevel,
    DataLakeSample,
    UncertainFrameUpload,
)
from src.types.models import InferenceResult, VlmComplianceVerdict


def test_imports_modules_resolve() -> None:
    """公开符号可导入（验收：python -c / pytest 不报错）。"""
    assert ConfidenceLevel.VIOLATION.value == "VIOLATION"
    assert EventType.SOP_VIOLATION.value == "SOP_VIOLATION"


def test_uncertain_frame_upload_requires_uncertain_level() -> None:
    with pytest.raises(ValidationError):
        UncertainFrameUpload(
            workstation_id="ws-1",
            sop_id="sop-a",
            sop_step=0,
            captured_at=datetime.now(timezone.utc),
            edge_confidence=0.5,
            edge_level=ConfidenceLevel.VIOLATION,
            frame_jpeg=b"\xff\xd8\xff",
        )


def test_uncertain_frame_upload_ok() -> None:
    u = UncertainFrameUpload(
        workstation_id="ws-1",
        sop_id="sop-a",
        sop_step=3,
        captured_at=datetime.now(timezone.utc),
        edge_confidence=0.55,
        edge_level=ConfidenceLevel.UNCERTAIN,
        frame_jpeg=b"\xff\xd8\xff",
        fsm_state="STEP_3",
    )
    assert u.edge_level is ConfidenceLevel.UNCERTAIN


def test_data_lake_sample_minio_prefix() -> None:
    with pytest.raises(ValidationError):
        DataLakeSample(
            frame_path="s3://x/y",
            label="VIOLATION",
            sop_step=1,
            workstation_id="ws-1",
            source="auto",
            timestamp=datetime.now(timezone.utc),
        )

    s = DataLakeSample(
        frame_path="minio://hard-cases/ws-1/2026/04/14/u.jpg",
        label="COMPLIANT",
        sop_step=1,
        workstation_id="ws-1",
        source="manual",
        timestamp=datetime.now(timezone.utc),
    )
    assert s.source == "manual"


def test_compliance_event_optional_empty_frame_path() -> None:
    e = ComplianceEvent(
        timestamp=datetime.now(timezone.utc),
        workstation_id="ws-1",
        event_type=EventType.SOP_VIOLATION,
        sop_step=2,
        frame_path="",
        confidence=0.2,
    )
    assert e.frame_path == ""


def test_inference_and_vlm_verdict() -> None:
    edge = InferenceResult(level=ConfidenceLevel.COMPLIANT, confidence=0.95)
    vlm = VlmComplianceVerdict(is_anomaly=True, reason="手套缺失", confidence=0.88)
    assert edge.level is ConfidenceLevel.COMPLIANT
    assert vlm.is_anomaly is True
