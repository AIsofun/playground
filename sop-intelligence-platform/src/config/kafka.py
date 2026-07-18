"""Kafka topic 与消费者组常量 — src/config/kafka.py

Layer 2 (config/) — 仅依赖 stdlib、pydantic-settings；禁止 import services/adapters/api。

合规事件 Topic 与 ``docs/module-specs/compliance-service.md``、
``docs/architecture/layering.md`` 对齐；默认值可通过环境变量覆盖。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Kafka 连接无关的「逻辑名」常量（broker URL 由部署/适配器侧配置）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    TOPIC_COMPLIANCE_EVENTS: str = Field(
        default="compliance.events",
        min_length=1,
        description="合规与 SOP 偏差类事件发布 Topic",
    )

    CONSUMER_GROUP_ROUTER: str = Field(
        default="event-router-group",
        min_length=1,
        description="Phase 2 事件路由器消费组 ID（layering.md）",
    )

    @field_validator("TOPIC_COMPLIANCE_EVENTS", "CONSUMER_GROUP_ROUTER")
    @classmethod
    def _kafka_names_non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Kafka topic / consumer group must be non-blank")
        return v


@lru_cache(maxsize=1)
def get_kafka_settings() -> KafkaSettings:
    """返回缓存的 KafkaSettings；测试中可 ``get_kafka_settings.cache_clear()``。"""
    return KafkaSettings()


_s = get_kafka_settings()

TOPIC_COMPLIANCE_EVENTS: str = _s.TOPIC_COMPLIANCE_EVENTS
CONSUMER_GROUP_ROUTER: str = _s.CONSUMER_GROUP_ROUTER
