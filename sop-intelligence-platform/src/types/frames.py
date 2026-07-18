"""
合规与媒体帧领域类型 — src/types/frames.py
============================================

与 ``docs/module-specs/compliance-service.md``、``docs/domain-logic.md`` 对齐。

架构约束（``docs/architecture/layering.md``）：
    仅 pydantic / enum / datetime / typing；禁止 import services、adapters、api。
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# ConfidenceLevel — 合规三档（边缘 / 慢路径最终档）
# ---------------------------------------------------------------------------


class ConfidenceLevel(str, enum.Enum):
    """工位合规判定三档，与 ``docs/domain-logic.md`` 一致。

    注意：勿与 ``src/types/sop.ActionDetectionVerdict`` 混淆；后者描述
    「动作观测 vs FSM 期望」的匹配语义，本枚举描述合规分档。
    """

    COMPLIANT = "COMPLIANT"
    UNCERTAIN = "UNCERTAIN"
    VIOLATION = "VIOLATION"


# ---------------------------------------------------------------------------
# VideoFrame / AnnotatedFrame — 通用帧抽象（合规与其它视觉链路复用）
# ---------------------------------------------------------------------------


class VideoFrame(BaseModel):
    """单帧时间与序号元数据（不含大块像素；像素走对象存储或 gRPC 字节流）。"""

    frame_index: int = Field(..., ge=0, description="在当前 clip 或流中的序号")
    captured_at: datetime = Field(..., description="采集时间（UTC 推荐）")
    width_px: int | None = Field(default=None, ge=1, description="像素宽")
    height_px: int | None = Field(default=None, ge=1, description="像素高")


class AnnotatedFrame(BaseModel):
    """已绑定业务上下文的帧引用（URI + 可选标注）。"""

    image_uri: str = Field(
        ...,
        min_length=1,
        description="帧资源定位，如 minio://bucket/key 或临时 upload id",
    )
    sop_step: int | None = Field(
        default=None,
        ge=0,
        description="关联 SOP 步骤索引，可选",
    )
    annotations: dict[str, str] = Field(
        default_factory=dict,
        description="人类可读或下游可消费的轻量标签键值",
    )


# ---------------------------------------------------------------------------
# UncertainFrameUpload — gRPC 边缘上送（与 module-spec §2.1 字段名一致）
# ---------------------------------------------------------------------------


class UncertainFrameUpload(BaseModel):
    """边缘在 ``ConfidenceLevel.UNCERTAIN`` 档上送的一帧及元数据。

    ``frame_jpeg`` 为原始 JPEG 字节；大小约束由 edge 规格与 gRPC 层执行，
    本类型仅做存在性与置信度区间校验。
    """

    workstation_id: str = Field(..., min_length=1)
    sop_id: str = Field(..., min_length=1)
    sop_step: int = Field(..., ge=0)
    captured_at: datetime = Field(..., description="采集时间；序列化 ISO8601")
    edge_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="领域文档中的 s",
    )
    edge_level: ConfidenceLevel = Field(
        ...,
        description="上传时应为 UNCERTAIN；服务端可再校验",
    )
    frame_jpeg: bytes = Field(..., description="JPEG 压缩帧字节")
    fsm_state: str | None = Field(
        default=None,
        description="当前 FSM 状态名，供 VLM 上下文注入",
    )

    @field_validator("edge_level")
    @classmethod
    def _upload_should_be_uncertain(cls, v: ConfidenceLevel) -> ConfidenceLevel:
        """规格默认：仅 UNCERTAIN 档触发上送（实现可放宽时改服务层）。"""
        if v is not ConfidenceLevel.UNCERTAIN:
            raise ValueError(
                "UncertainFrameUpload.edge_level 应为 UNCERTAIN；"
                f"收到 {v!r}"
            )
        return v


# ---------------------------------------------------------------------------
# DataLakeSample — 入湖样本元数据（PG / 索引侧）
# ---------------------------------------------------------------------------


DataLakeSampleSource = Literal["auto", "manual"]


class DataLakeSample(BaseModel):
    """``data_lake_samples`` 表语义字段集（迁移 SQL 为列级真源）。"""

    frame_path: str = Field(
        ...,
        min_length=1,
        description="MinIO 引用，形如 minio://{bucket}/{object_key}",
    )
    label: str = Field(
        ...,
        min_length=1,
        description="训练用标签；分歧帧常为 VLM 结论，误报人工为 COMPLIANT 等",
    )
    sop_step: int = Field(..., ge=0)
    workstation_id: str = Field(..., min_length=1)
    source: DataLakeSampleSource = Field(
        ...,
        description="auto=分歧自动入湖；manual=误报等人工入湖",
    )
    timestamp: datetime = Field(..., description="写入或采集时间")

    @field_validator("frame_path")
    @classmethod
    def _minio_scheme(cls, v: str) -> str:
        if not v.startswith("minio://"):
            raise ValueError("frame_path 应以 minio:// 前缀开头")
        return v
