"""合规链路相关 config 常量可加载且与默认值契约一致。"""

from src.config.edge import GRPC_UNCERTAIN_FRAME_DEADLINE_SEC, GRPC_UNCERTAIN_FRAME_MAX_BYTES
from src.config.kafka import CONSUMER_GROUP_ROUTER, TOPIC_COMPLIANCE_EVENTS
from src.config.storage import (
    MINIO_BUCKET_HARD_CASES,
    MINIO_URI_PREFIX,
    POSTGRES_TABLE_COMPLIANCE_EVENTS,
    POSTGRES_TABLE_DATA_LAKE_SAMPLES,
)
from src.config.vlm import CONF_HIGH, CONF_LOW, VLM_ANOMALY_CHECK_PROMPT_PATH


def test_kafka_compliance_topic_not_empty() -> None:
    assert TOPIC_COMPLIANCE_EVENTS == "compliance.events"
    assert CONSUMER_GROUP_ROUTER == "event-router-group"


def test_storage_compliance_tables_and_minio_prefix() -> None:
    assert MINIO_BUCKET_HARD_CASES == "hard-cases"
    assert MINIO_URI_PREFIX == "minio://"
    assert POSTGRES_TABLE_COMPLIANCE_EVENTS == "compliance_events"
    assert POSTGRES_TABLE_DATA_LAKE_SAMPLES == "data_lake_samples"


def test_edge_grpc_limits_positive() -> None:
    assert GRPC_UNCERTAIN_FRAME_DEADLINE_SEC == 2
    assert GRPC_UNCERTAIN_FRAME_MAX_BYTES == 512_000


def test_vlm_compliance_thresholds_order() -> None:
    assert 0.0 <= CONF_LOW < CONF_HIGH <= 1.0
    assert VLM_ANOMALY_CHECK_PROMPT_PATH.endswith("vlm-anomaly-check.txt")
