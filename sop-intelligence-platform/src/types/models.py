"""
模型版本、评估指标与推断结果 — src/types/models.py
==================================================

合规 VLM 响应形状见 ``docs/module-specs/compliance-service.md`` §3.2；
``InferenceResult`` 在分层文档中表示边缘侧合规推断快照（level + s）。

架构约束：可依赖 ``src/types/frames`` 中的枚举；禁止 import services、adapters、api。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.types.frames import ConfidenceLevel


# ---------------------------------------------------------------------------
# InferenceResult — 边缘（或统一为三档前的）合规推断
# ---------------------------------------------------------------------------


class InferenceResult(BaseModel):
    """边缘侧对当前观测的合规相关推断：三档 + 标量置信度。

    与 ``src/services/compliance/AGENTS.md`` 分歧检测伪代码中的
    ``edge_result.level``、``edge_result`` 置信度语义对齐。
    """

    level: ConfidenceLevel
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="与 domain-logic 中 s 一致，[0,1]",
    )


# ---------------------------------------------------------------------------
# VlmComplianceVerdict — VLM 解析后的结构化输出
# ---------------------------------------------------------------------------


class VlmComplianceVerdict(BaseModel):
    """VLM 异常/合规复核 JSON（module-spec §3.2）。"""

    is_anomaly: bool = Field(
        ...,
        description="true=与 SOP 期望严重偏离；false=可视为合规或可接受噪声",
    )
    reason: str = Field(default="", description="短理由，供审计与工单")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="VLM 自报告置信度；不替代 CONF_LOW/HIGH 分档",
    )


# ---------------------------------------------------------------------------
# ModelVersion / OTAPackage — 边缘模型与 OTA（与 storage 规划对齐）
# ---------------------------------------------------------------------------


class ModelVersion(BaseModel):
    """客户专属检测或合规辅助模型的版本描述。"""

    model_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    created_at: datetime | None = None
    minio_uri: str | None = Field(
        default=None,
        description="可选：模型包在 MinIO 的 URI",
    )


class OTAPackage(BaseModel):
    """下发至 Jetson 的 OTA 更新单元元数据。"""

    package_id: str = Field(..., min_length=1)
    target_runtime: str = Field(
        default="jetson-orin-nx",
        description="目标硬件/运行时标识",
    )
    artifact_uri: str = Field(..., min_length=1, description="MinIO 或 CDN 下载地址")


# ---------------------------------------------------------------------------
# EvalMetrics — Harness / 训练评估通用指标容器
# ---------------------------------------------------------------------------


class EvalMetrics(BaseModel):
    """各模块 Harness 指标；合规门禁见 ``docs/eval-standards.md``。"""

    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    fpr: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertain_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="UNCERTAIN 档占比",
    )
    notes: str = ""
