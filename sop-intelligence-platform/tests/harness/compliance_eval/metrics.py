"""合规监控 Eval 指标（与 ``docs/eval-standards.md`` §1.1 对齐）。

本模块只做 **统计与门禁判定**，不读数据集文件；样本级预测由 ``run_eval.py`` 组装。
"""

from __future__ import annotations

from dataclasses import dataclass


def recall_rate(true_positives: int, false_negatives: int) -> float:
    """Recall = TP / (TP + FN)。无正例时返回 1.0（无可评违规，视为满足）。"""
    denom = int(true_positives) + int(false_negatives)
    if denom <= 0:
        return 1.0
    return float(true_positives) / float(denom)


def false_positive_rate(false_positives: int, true_negatives: int) -> float:
    """FPR = FP / (FP + TN)。无负例时返回 0.0（无可评合规底噪，视为满足）。"""
    denom = int(false_positives) + int(true_negatives)
    if denom <= 0:
        return 0.0
    return float(false_positives) / float(denom)


def uncertain_ratio(uncertain_count: int, total_count: int) -> float:
    """边缘档 ``UNCERTAIN`` 占评估集比例。"""
    if int(total_count) <= 0:
        return 0.0
    return float(uncertain_count) / float(total_count)


@dataclass(frozen=True, slots=True)
class ComplianceEvalThresholds:
    """门禁数值仅在此处与 ``run_eval`` 环境变量默认值对齐；不等式真源见 eval-standards。"""

    recall_min: float
    fpr_max: float
    uncertain_max: float


@dataclass(frozen=True, slots=True)
class ComplianceEvalReport:
    """一次评估的聚合结果与是否通过门禁。"""

    n_total: int
    true_positives: int
    false_negatives: int
    false_positives: int
    true_negatives: int
    uncertain_edge_count: int
    recall: float
    fpr: float
    uncertain_fraction: float
    passed: bool
    failures: tuple[str, ...]


def evaluate_confusion_gate(
    *,
    tp: int,
    fn: int,
    fp: int,
    tn: int,
    uncertain_edge_count: int,
    thresholds: ComplianceEvalThresholds,
) -> ComplianceEvalReport:
    """根据混淆矩阵与 UNCERTAIN 计数判定是否同时满足 Recall / FPR / UNCERTAIN 比例。"""
    r = recall_rate(tp, fn)
    f = false_positive_rate(fp, tn)
    u = uncertain_ratio(uncertain_edge_count, tp + fn + fp + tn)
    fails: list[str] = []
    if r < thresholds.recall_min:
        fails.append(f"Recall {r:.4f} < {thresholds.recall_min}")
    if f > thresholds.fpr_max:
        fails.append(f"FPR {f:.4f} > {thresholds.fpr_max}")
    if u > thresholds.uncertain_max:
        fails.append(f"UNCERTAIN 比例 {u:.4f} > {thresholds.uncertain_max}")
    total = tp + fn + fp + tn
    return ComplianceEvalReport(
        n_total=total,
        true_positives=tp,
        false_negatives=fn,
        false_positives=fp,
        true_negatives=tn,
        uncertain_edge_count=uncertain_edge_count,
        recall=r,
        fpr=f,
        uncertain_fraction=u,
        passed=len(fails) == 0,
        failures=tuple(fails),
    )
