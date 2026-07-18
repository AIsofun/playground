"""Kafka 发布适配器：序列化 ``ComplianceEvent`` 并写入 ``compliance.events``。

本模块不包含合规判定等业务分支；``event_type``、``confidence`` 等语义由
``src/services/compliance/`` 构造 ``ComplianceEvent`` 时确定。

载荷字段与 ``docs/module-specs/compliance-service.md`` §4、
``src/services/compliance/AGENTS.md`` 第四节一致。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.config.kafka import get_kafka_settings
from src.types.events import ComplianceEvent


@runtime_checkable
class _KafkaProducerPort(Protocol):
    """与 ``kafka.KafkaProducer`` 兼容的最小接口，便于单测注入 mock。"""

    def send(
        self,
        topic: str,
        value: bytes | memoryview | None = None,
        key: bytes | memoryview | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def flush(self, timeout: float | None = None) -> None: ...

    def close(self) -> None: ...


def serialize_compliance_event(event: ComplianceEvent) -> bytes:
    """将事件序列化为 UTF-8 JSON 字节串。

    - ``timestamp``：ISO8601（由 Pydantic JSON 模式输出；调用方应使用 UTC）。
    - ``event_type``：枚举对应的字符串字面量。
    - ``confidence``：原样写入 JSON number；标量含义由 services 层固定并在事件中体现。
    """
    text = event.model_dump_json()
    return text.encode("utf-8")


class ComplianceKafkaProducer:
    """封装 ``KafkaProducer.send``；仅负责 topic + 字节载荷。"""

    def __init__(self, producer: _KafkaProducerPort, *, topic: str) -> None:
        if not topic.strip():
            raise ValueError("topic must be non-blank")
        self._producer = producer
        self._topic = topic

    @classmethod
    def from_bootstrap(
        cls,
        bootstrap_servers: str | list[str],
        *,
        topic: str | None = None,
        **producer_kwargs: Any,
    ) -> ComplianceKafkaProducer:
        """使用 ``kafka-python`` 构造真实 Producer（broker 地址由部署注入）。"""
        from kafka import KafkaProducer

        settings = get_kafka_settings()
        resolved = topic if topic is not None else settings.TOPIC_COMPLIANCE_EVENTS
        raw = KafkaProducer(bootstrap_servers=bootstrap_servers, **producer_kwargs)
        return cls(raw, topic=resolved)

    def send(self, event: ComplianceEvent) -> Any:
        """异步发送一条合规事件，返回 ``Future``（与 ``kafka-python`` 一致）。"""
        return self._producer.send(self._topic, value=serialize_compliance_event(event))

    def flush(self, timeout: float | None = None) -> None:
        self._producer.flush(timeout=timeout)

    def close(self) -> None:
        self._producer.close()
