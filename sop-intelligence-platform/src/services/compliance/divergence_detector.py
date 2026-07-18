"""大小模型分歧检测（服务层，无 I/O）。

规则与 ``src/services/compliance/AGENTS.md`` 第三节伪代码一致；边缘侧使用
``InferenceResult``，VLM 侧使用 ``VlmComplianceVerdict``（含 ``is_anomaly``）。

``edge.level == UNCERTAIN`` 时本模块**不**将上述两种分歧模式之一记为真，
返回未分歧（慢路径仍以 VLM 为准，分歧标签仅用于「边缘与 VLM 结论相反」
的难例入湖）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.types.frames import ConfidenceLevel
from src.types.models import InferenceResult, VlmComplianceVerdict

__all__ = [
    "DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY",
    "DIVERGENCE_EDGE_VIOLATION_VLM_CLEAR",
    "DivergenceResult",
    "detect_divergence",
]

# 与监控/日志对齐的稳定标识符（非阈值魔数）
DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY: str = "EDGE_COMPLIANT_VLM_ANOMALY"
DIVERGENCE_EDGE_VIOLATION_VLM_CLEAR: str = "EDGE_VIOLATION_VLM_CLEAR"


class DivergenceResult(BaseModel):
    """是否分歧及可选结构化说明。"""

    is_divergent: bool = Field(..., description="为 True 时应触发自动入湖（source=auto）")
    reason_code: str | None = Field(
        default=None,
        description="分歧子类型；未分歧时为 None",
    )
    summary: str | None = Field(
        default=None,
        description="供日志/工单的一句话摘要",
    )


def detect_divergence(
    edge_result: InferenceResult,
    vlm_result: VlmComplianceVerdict,
) -> DivergenceResult:
    """若边缘与 VLM 结论处于 AGENTS 规定的两种「相反」模式之一，则视为分歧。"""
    level = edge_result.level

    if level == ConfidenceLevel.COMPLIANT and vlm_result.is_anomaly:
        return DivergenceResult(
            is_divergent=True,
            reason_code=DIVERGENCE_EDGE_COMPLIANT_VLM_ANOMALY,
            summary="边缘合规但 VLM 判异常",
        )

    if level == ConfidenceLevel.VIOLATION and not vlm_result.is_anomaly:
        return DivergenceResult(
            is_divergent=True,
            reason_code=DIVERGENCE_EDGE_VIOLATION_VLM_CLEAR,
            summary="边缘违规但 VLM 未支持异常",
        )

    return DivergenceResult(is_divergent=False, reason_code=None, summary=None)
