"""divergence_detector：边合/VLM异、边违/VLM否及对齐组合。"""

from __future__ import annotations

from src.services.compliance.divergence_detector import (
    DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY,
    DIVERGENCE_EDGE_VIOLATION_VLM_CLEAR,
    DivergenceResult,
    detect_divergence,
)
from src.types.frames import ConfidenceLevel
from src.types.models import InferenceResult, VlmComplianceVerdict


def _edge(level: ConfidenceLevel, confidence: float = 0.5) -> InferenceResult:
    return InferenceResult(level=level, confidence=confidence)


def _vlm(is_anomaly: bool, reason: str = "") -> VlmComplianceVerdict:
    return VlmComplianceVerdict(is_anomaly=is_anomaly, reason=reason, confidence=0.9)


def test_edge_compliant_vlm_anomaly_is_divergent() -> None:
    """边合 / VLM 异 → 分歧。"""
    r = detect_divergence(_edge(ConfidenceLevel.COMPLIANT, 0.95), _vlm(True, "手套"))
    assert r == DivergenceResult(
        is_divergent=True,
        reason_code=DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY,
        summary="边缘合规但 VLM 判异常",
    )


def test_edge_violation_vlm_clear_is_divergent() -> None:
    """边违 / VLM 否（未判异常）→ 分歧。"""
    r = detect_divergence(_edge(ConfidenceLevel.VIOLATION, 0.1), _vlm(False))
    assert r == DivergenceResult(
        is_divergent=True,
        reason_code=DIVERGENCE_EDGE_VIOLATION_VLM_CLEAR,
        summary="边缘违规但 VLM 未支持异常",
    )


def test_edge_compliant_vlm_clear_not_divergent() -> None:
    """边合 / VLM 同（未判异常）→ 未分歧。"""
    r = detect_divergence(_edge(ConfidenceLevel.COMPLIANT), _vlm(False))
    assert r.is_divergent is False
    assert r.reason_code is None
    assert r.summary is None


def test_edge_violation_vlm_anomaly_not_divergent() -> None:
    """边违 / VLM 异（亦判异常）→ 未分歧（一致）。"""
    r = detect_divergence(_edge(ConfidenceLevel.VIOLATION), _vlm(True, "明显违规"))
    assert r.is_divergent is False
    assert r.reason_code is None


def test_edge_uncertain_neither_branch_not_divergent() -> None:
    """UNCERTAIN 档不触发两种分歧模式（伪代码未覆盖）。"""
    r1 = detect_divergence(_edge(ConfidenceLevel.UNCERTAIN, 0.55), _vlm(True))
    r2 = detect_divergence(_edge(ConfidenceLevel.UNCERTAIN, 0.55), _vlm(False))
    assert r1.is_divergent is False and r2.is_divergent is False
