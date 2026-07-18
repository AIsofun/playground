"""compliance_eval metrics 纯函数契约。"""

from __future__ import annotations

import pytest

from tests.harness.compliance_eval.metrics import (
    ComplianceEvalThresholds,
    evaluate_confusion_gate,
    false_positive_rate,
    recall_rate,
    uncertain_ratio,
)


def test_recall_rate_basic() -> None:
    assert recall_rate(9, 1) == pytest.approx(0.9)
    assert recall_rate(0, 0) == 1.0


def test_false_positive_rate_basic() -> None:
    assert false_positive_rate(1, 19) == pytest.approx(0.05)
    assert false_positive_rate(0, 0) == 0.0


def test_uncertain_ratio() -> None:
    assert uncertain_ratio(3, 20) == pytest.approx(0.15)
    assert uncertain_ratio(0, 0) == 0.0


def test_evaluate_confusion_gate_pass() -> None:
    t = ComplianceEvalThresholds(recall_min=0.95, fpr_max=0.05, uncertain_max=0.15)
    r = evaluate_confusion_gate(
        tp=10, fn=0, fp=0, tn=40, uncertain_edge_count=5, thresholds=t
    )
    assert r.passed is True
    assert r.failures == ()


def test_evaluate_confusion_gate_fail_recall() -> None:
    t = ComplianceEvalThresholds(recall_min=0.95, fpr_max=0.05, uncertain_max=0.15)
    r = evaluate_confusion_gate(
        tp=9, fn=1, fp=0, tn=40, uncertain_edge_count=0, thresholds=t
    )
    assert r.passed is False
    assert any("Recall" in x for x in r.failures)
