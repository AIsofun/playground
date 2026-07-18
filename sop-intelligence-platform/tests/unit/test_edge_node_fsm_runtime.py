"""edge_node.fsm_runtime 分档逻辑（与 domain-logic 闭开约定一致）。"""

from __future__ import annotations

import pytest

from edge_node.fsm_runtime import ComplianceBand, classify_edge_score


def test_classify_violation_below_low() -> None:
    assert classify_edge_score(0.39) is ComplianceBand.VIOLATION


def test_classify_uncertain_interval_lower_bound() -> None:
    assert classify_edge_score(0.4) is ComplianceBand.UNCERTAIN


def test_classify_uncertain_upper_open() -> None:
    assert classify_edge_score(0.699) is ComplianceBand.UNCERTAIN


def test_classify_compliant_at_high() -> None:
    assert classify_edge_score(0.7) is ComplianceBand.COMPLIANT


def test_critical_rule_forces_violation() -> None:
    assert classify_edge_score(0.99, critical_rule_triggered=True) is ComplianceBand.VIOLATION


def test_score_out_of_range() -> None:
    with pytest.raises(ValueError):
        classify_edge_score(1.01)
