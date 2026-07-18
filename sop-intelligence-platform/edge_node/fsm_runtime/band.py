"""边缘合规三档输出（字符串枚举）；分档语义见 ``docs/domain-logic.md`` §2。

主路径仅调用 ``classify_edge_score``，**禁止**将原始浮点分直接作为对下游契约输出。
"""

from __future__ import annotations

import enum

from edge_node.fsm_runtime.thresholds import CONF_HIGH, CONF_LOW


class ComplianceBand(str, enum.Enum):
    """与 ``docs/domain-logic.md`` 合规三档一致（值与 Kafka / 服务端字符串对齐）。"""

    COMPLIANT = "COMPLIANT"
    UNCERTAIN = "UNCERTAIN"
    VIOLATION = "VIOLATION"


def classify_edge_score(score: float, *, critical_rule_triggered: bool = False) -> ComplianceBand:
    """将 :math:`s \\in [0,1]` 映射为三档；``critical_rule_triggered`` 为真时强制 ``VIOLATION``。"""
    if critical_rule_triggered:
        return ComplianceBand.VIOLATION
    s = float(score)
    if not 0.0 <= s <= 1.0:
        raise ValueError(f"edge score 须在 [0,1]，收到 {s!r}")
    if s < CONF_LOW:
        return ComplianceBand.VIOLATION
    if s < CONF_HIGH:
        return ComplianceBand.UNCERTAIN
    return ComplianceBand.COMPLIANT
