"""``kafka_producer`` 适配器：序列化契约与 send 委托（mock broker）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.adapters.messaging.kafka_producer import ComplianceKafkaProducer, serialize_compliance_event
from src.types.events import ComplianceEvent, EventType


def test_serialize_compliance_event_roundtrip_shape() -> None:
    ts = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
    event = ComplianceEvent(
        timestamp=ts,
        workstation_id="ws-01",
        event_type=EventType.SOP_VIOLATION,
        sop_step=3,
        frame_path="minio://hard-cases/ws-01/2026/04/14/uuid.jpg",
        confidence=0.82,
    )
    raw = serialize_compliance_event(event)
    assert isinstance(raw, bytes)
    data = json.loads(raw.decode("utf-8"))
    assert data["timestamp"] == "2026-04-14T12:00:00Z"
    assert data["workstation_id"] == "ws-01"
    assert data["event_type"] == "SOP_VIOLATION"
    assert data["sop_step"] == 3
    assert data["frame_path"] == "minio://hard-cases/ws-01/2026/04/14/uuid.jpg"
    assert data["confidence"] == 0.82
    assert set(data.keys()) == {
        "timestamp",
        "workstation_id",
        "event_type",
        "sop_step",
        "frame_path",
        "confidence",
    }


def test_serialize_empty_frame_path_emitted() -> None:
    event = ComplianceEvent(
        timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        workstation_id="ws-99",
        event_type=EventType.MODEL_CHANGEOVER,
        sop_step=0,
        frame_path="",
        confidence=1.0,
    )
    data = json.loads(serialize_compliance_event(event).decode("utf-8"))
    assert data["frame_path"] == ""


def test_compliance_kafka_producer_send_delegates() -> None:
    mock_producer = MagicMock()
    mock_producer.send.return_value = "future-handle"
    adapter = ComplianceKafkaProducer(mock_producer, topic="compliance.events")
    ts = datetime(2026, 4, 14, 0, 0, 0, tzinfo=timezone.utc)
    event = ComplianceEvent(
        timestamp=ts,
        workstation_id="ws-02",
        event_type=EventType.BATCH_DEFECT,
        sop_step=1,
        confidence=0.5,
    )
    fut = adapter.send(event)
    assert fut == "future-handle"
    mock_producer.send.assert_called_once()
    call_kw = mock_producer.send.call_args
    assert call_kw[0][0] == "compliance.events"
    payload = call_kw[1]["value"]
    assert isinstance(payload, bytes)
    body = json.loads(payload.decode("utf-8"))
    assert body["event_type"] == "BATCH_DEFECT"


def test_compliance_kafka_producer_blank_topic_rejected() -> None:
    with pytest.raises(ValueError, match="topic"):
        ComplianceKafkaProducer(MagicMock(), topic="   ")


def test_flush_and_close_forwarded() -> None:
    mock_producer = MagicMock()
    adapter = ComplianceKafkaProducer(mock_producer, topic="compliance.events")
    adapter.flush(timeout=1.0)
    adapter.close()
    mock_producer.flush.assert_called_once_with(timeout=1.0)
    mock_producer.close.assert_called_once()
