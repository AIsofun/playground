"""合规监控 Eval Harness 入口（``p1-compliance``）。

从项目根执行::

    python tests/harness/compliance_eval/run_eval.py

门禁与 ``docs/eval-standards.md`` §1.1 一致；阈值数字默认引用 eval-standards
不等式，可通过环境变量覆盖（浮点字符串）::

    COMPLIANCE_EVAL_RECALL_MIN   — Recall 下限，默认 0.95
    COMPLIANCE_EVAL_FPR_MAX      — FPR 上限，默认 0.05
    COMPLIANCE_EVAL_UNCERTAIN_MAX — UNCERTAIN 比例上限，默认 0.15

数据集：``eval_dataset/samples.json``（格式见同目录 ``README.md``）。
Phase 1 使用 **冻结的** ``vlm_is_anomaly`` 模拟 VLM；不发起 HTTP。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_HARNESS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _HARNESS_DIR.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.chdir(_PROJECT_ROOT)

from src.services.compliance.confidence_classifier import ConfidenceClassifier
from src.services.compliance.divergence_detector import detect_divergence
from src.types.frames import ConfidenceLevel
from src.types.models import InferenceResult, VlmComplianceVerdict
from tests.harness.compliance_eval.metrics import (
    ComplianceEvalThresholds,
    evaluate_confusion_gate,
)

EVAL_DATASET_PATH = _HARNESS_DIR / "eval_dataset" / "samples.json"

RECALL_MIN = float(os.environ.get("COMPLIANCE_EVAL_RECALL_MIN", "0.95"))
FPR_MAX = float(os.environ.get("COMPLIANCE_EVAL_FPR_MAX", "0.05"))
UNCERTAIN_MAX = float(os.environ.get("COMPLIANCE_EVAL_UNCERTAIN_MAX", "0.15"))


def _pred_alarm(
    edge_s: float,
    vlm_is_anomaly: bool,
    classifier: ConfidenceClassifier,
) -> tuple[ConfidenceLevel, bool]:
    """与 ``uncertain_frame_orchestrator._should_publish_kafka`` 同构的 alarm 判定。"""
    lvl = classifier.classify(edge_s)
    edge_inf = InferenceResult(level=lvl, confidence=float(edge_s))
    vlm = VlmComplianceVerdict(
        is_anomaly=bool(vlm_is_anomaly),
        reason="harness",
        confidence=0.5,
    )
    div = detect_divergence(edge_inf, vlm)
    pred = bool(vlm.is_anomaly or div.is_divergent)
    return lvl, pred


def _load_samples(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"未找到评测集：{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("samples.json 顶层须为 JSON 数组")
    out: list[dict[str, Any]] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"第 {i} 条样本不是对象")
        for k in ("id", "edge_s", "gold_violation", "vlm_is_anomaly"):
            if k not in row:
                raise ValueError(f"样本 {row.get('id', i)!r} 缺少字段 {k!r}")
        out.append(row)
    return out


def _accumulate(rows: list[dict[str, Any]], classifier: ConfidenceClassifier) -> tuple[int, int, int, int, int]:
    tp = fn = fp = tn = unc = 0
    for row in rows:
        gold_v = bool(row["gold_violation"])
        edge_s = float(row["edge_s"])
        vlm_a = bool(row["vlm_is_anomaly"])
        lvl, pred_a = _pred_alarm(edge_s, vlm_a, classifier)
        if lvl is ConfidenceLevel.UNCERTAIN:
            unc += 1
        if gold_v and pred_a:
            tp += 1
        elif gold_v and not pred_a:
            fn += 1
        elif not gold_v and pred_a:
            fp += 1
        else:
            tn += 1
    return tp, fn, fp, tn, unc


def main() -> int:
    thresholds = ComplianceEvalThresholds(
        recall_min=RECALL_MIN,
        fpr_max=FPR_MAX,
        uncertain_max=UNCERTAIN_MAX,
    )
    try:
        rows = _load_samples(EVAL_DATASET_PATH)
    except FileNotFoundError as exc:
        print(f"❌ EVAL FAILED: {exc}")
        return 1

    classifier = ConfidenceClassifier()
    tp, fn, fp, tn, n_unc = _accumulate(rows, classifier)
    report = evaluate_confusion_gate(
        tp=tp,
        fn=fn,
        fp=fp,
        tn=tn,
        uncertain_edge_count=n_unc,
        thresholds=thresholds,
    )

    print("=== 合规监控 compliance_eval（帧级 + 冻结 VLM）===\n")
    print(f"样本数: {report.n_total}")
    print(f"混淆矩阵: TP={tp} FN={fn} FP={fp} TN={tn}")
    print(f"边缘 UNCERTAIN 条数: {n_unc}（比例 {report.uncertain_fraction:.4f}）")
    print()
    print(f"Recall:    {report.recall:.4f}（要求 ≥ {thresholds.recall_min}）")
    print(f"FPR:       {report.fpr:.4f}（要求 ≤ {thresholds.fpr_max}）")
    print(f"UNCERTAIN: {report.uncertain_fraction:.4f}（要求 ≤ {thresholds.uncertain_max}）")
    print()

    if report.passed:
        print("✅ EVAL PASSED（门禁同时满足）")
        return 0
    print("❌ EVAL FAILED")
    for line in report.failures:
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
