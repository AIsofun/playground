"""边缘 ↔ 服务端帧通道相关常量 — src/config/edge.py

Layer 2 (config/) — 仅 stdlib + pydantic-settings。

与 ``plan/sop-intelligence-platform.md`` edge 小节（gRPC UNCERTAIN 上送、
帧大小/超时）及 ``docs/module-specs/compliance-service.md`` 一致；
业务逻辑仍在 adapters/services。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EdgeSettings(BaseSettings):
    """工位边缘经 gRPC 上送 UNCERTAIN 帧时的非功能性约束。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    GRPC_UNCERTAIN_FRAME_DEADLINE_SEC: int = Field(
        default=2,
        gt=0,
        description="单帧 gRPC 调用 deadline（秒），与规划文档 edge 小节一致",
    )

    GRPC_UNCERTAIN_FRAME_MAX_BYTES: int = Field(
        default=512_000,
        gt=0,
        description="单帧 JPEG 上限（字节）；默认 500KiB 量级",
    )


@lru_cache(maxsize=1)
def get_edge_settings() -> EdgeSettings:
    return EdgeSettings()


_s = get_edge_settings()

GRPC_UNCERTAIN_FRAME_DEADLINE_SEC: int = _s.GRPC_UNCERTAIN_FRAME_DEADLINE_SEC
GRPC_UNCERTAIN_FRAME_MAX_BYTES: int = _s.GRPC_UNCERTAIN_FRAME_MAX_BYTES
