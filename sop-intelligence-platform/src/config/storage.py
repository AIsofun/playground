"""Configuration constants for all external storage systems.

Layer 2 (config/) — only imports from stdlib, pydantic-settings, and src/types/.
Forbidden: src/services/, src/adapters/, src/api/.

All constants are readable directly:
    from src.config.storage import MINIO_BUCKET_SOP_KEYFRAMES

All constants can be overridden via environment variables or a .env file at
the project root. Example:
    MINIO_BUCKET_SOP_KEYFRAMES=prod-keyframes python -m pytest
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Pydantic-settings model for MinIO, PostgreSQL, and data-lake storage constants.

    Fields are populated in priority order:
    1. Direct constructor arguments (e.g. in tests)
    2. Environment variables (same name, case-insensitive)
    3. `.env` file at the project root
    4. Default values defined below
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # MinIO buckets — SOP pipeline (T02 spec)
    # ------------------------------------------------------------------

    MINIO_BUCKET_SOP_KEYFRAMES: str = Field(
        default="sop-keyframes",
        min_length=1,
    )
    """MinIO bucket that stores per-step keyframe images extracted from expert videos.
    Path convention: sop-keyframes/{sop_id}/step_{step_id}.jpg"""

    MINIO_BUCKET_SOP_VIDEOS: str = Field(
        default="sop-videos",
        min_length=1,
    )
    """MinIO bucket that stores the original expert-operation source videos.
    Path convention: sop-videos/{product_id}/{filename}"""

    # ------------------------------------------------------------------
    # PostgreSQL table names — SOP pipeline (T02 spec)
    # ------------------------------------------------------------------

    POSTGRES_TABLE_SOP_VERSIONS: str = Field(
        default="sop_versions",
        min_length=1,
    )
    """PostgreSQL table that stores SOP document snapshots and version metadata.
    Schema defined in: data/migrations/001_create_sop_versions.sql"""

    POSTGRES_TABLE_FSM_GRAPHS: str = Field(
        default="fsm_graphs",
        min_length=1,
    )
    """PostgreSQL table for compiled FSMGraph JSON bound to a sop_id.
    Schema defined in: data/migrations/002_create_fsm_graphs.sql"""

    # ------------------------------------------------------------------
    # PostgreSQL — compliance & data-lake（表名以迁移 SQL 为列级真源）
    # ------------------------------------------------------------------

    POSTGRES_TABLE_COMPLIANCE_EVENTS: str = Field(
        default="compliance_events",
        min_length=1,
    )
    """TimescaleDB / PG 超表：合规事件时序（见 docs/module-specs/compliance-service.md）。"""

    POSTGRES_TABLE_DATA_LAKE_SAMPLES: str = Field(
        default="data_lake_samples",
        min_length=1,
    )
    """数据湖样本元数据索引表（分歧帧 / 误报等）。"""

    # ------------------------------------------------------------------
    # MinIO buckets — compliance & data-lake (layering.md)
    # ------------------------------------------------------------------

    MINIO_BUCKET_HARD_CASES: str = Field(
        default="hard-cases",
        min_length=1,
    )
    """MinIO bucket for frames where edge and VLM classifications diverge.
    These frames are ingested into the data lake for human labelling and
    subsequent QLoRA fine-tuning (see docs/module-specs/data-lake.md)."""

    MINIO_URI_PREFIX: str = Field(
        default="minio://",
        min_length=1,
    )
    """写入 Kafka / PG / types 的帧引用 URI 前缀；与 ``src/types/frames.DataLakeSample`` 校验一致。"""

    MINIO_BUCKET_MODELS: str = Field(
        default="models",
        min_length=1,
    )
    """MinIO bucket for versioned TensorRT .engine model files pushed to Jetson
    edge nodes via OTA updates (src/adapters/edge/ota_client.py)."""

    # ------------------------------------------------------------------
    # Data-lake thresholds (layering.md)
    # ------------------------------------------------------------------

    DATA_LAKE_TRIGGER_THRESHOLD: int = Field(
        default=200,
        gt=0,
    )
    """Minimum number of new labelled samples required before the data-lake
    trigger fires an automatic QLoRA fine-tuning job.
    See src/services/data_lake/trigger.py."""

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator(
        "MINIO_BUCKET_SOP_KEYFRAMES",
        "MINIO_BUCKET_SOP_VIDEOS",
        "MINIO_BUCKET_HARD_CASES",
        "MINIO_BUCKET_MODELS",
        "MINIO_URI_PREFIX",
        "POSTGRES_TABLE_SOP_VERSIONS",
        "POSTGRES_TABLE_FSM_GRAPHS",
        "POSTGRES_TABLE_COMPLIANCE_EVENTS",
        "POSTGRES_TABLE_DATA_LAKE_SAMPLES",
    )
    @classmethod
    def _name_must_not_be_blank(cls, v: str) -> str:
        """Bucket and table names must contain at least one non-whitespace character."""
        if not v.strip():
            raise ValueError(
                f"Storage name must not be blank or whitespace-only, got {v!r}."
            )
        return v


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    """Return a cached StorageSettings instance (loaded once at first call).

    The cache can be cleared in tests with:
        get_storage_settings.cache_clear()
    """
    return StorageSettings()


# ---------------------------------------------------------------------------
# Module-level constants — direct import API
# ---------------------------------------------------------------------------

_s = get_storage_settings()

MINIO_BUCKET_SOP_KEYFRAMES: str = _s.MINIO_BUCKET_SOP_KEYFRAMES
MINIO_BUCKET_SOP_VIDEOS: str = _s.MINIO_BUCKET_SOP_VIDEOS

POSTGRES_TABLE_SOP_VERSIONS: str = _s.POSTGRES_TABLE_SOP_VERSIONS
POSTGRES_TABLE_FSM_GRAPHS: str = _s.POSTGRES_TABLE_FSM_GRAPHS
POSTGRES_TABLE_COMPLIANCE_EVENTS: str = _s.POSTGRES_TABLE_COMPLIANCE_EVENTS
POSTGRES_TABLE_DATA_LAKE_SAMPLES: str = _s.POSTGRES_TABLE_DATA_LAKE_SAMPLES

MINIO_BUCKET_HARD_CASES: str = _s.MINIO_BUCKET_HARD_CASES
MINIO_BUCKET_MODELS: str = _s.MINIO_BUCKET_MODELS
MINIO_URI_PREFIX: str = _s.MINIO_URI_PREFIX

DATA_LAKE_TRIGGER_THRESHOLD: int = _s.DATA_LAKE_TRIGGER_THRESHOLD
