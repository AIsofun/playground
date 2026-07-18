"""SOP 生成评测指标（T09 Eval Harness）。

Ground Truth 为 ``list[dict]``，字典键名与 ``src.types.sop.SOPStep`` 对齐，
评测使用的子集为：

- ``action_type`` (str, 必填) — 与 ``SOPStep.action_type`` 一致
- ``video_timestamp`` (float, keyframe 指标必填) — 与 ``SOPStep.video_timestamp`` 一致，单位秒，≥ 0
- ``step_id`` (int, 可选) — 与 ``SOPStep.step_id`` 一致；若每条 GT 均含此字段，
  则先按 ``step_id`` 升序再与预测做时序相关匹配；否则保持 GT 列表原有顺序
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.types.sop import SOPDocument, SOPStep

# 与 sop-engine.md T09 规格一致：单步时间偏差阈值（秒）
KEYFRAME_TIMESTAMP_TOLERANCE_SEC: float = 2.0


def _ordered_ground_truth(gt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """若全部 GT 行含 ``step_id``，按 ``step_id`` 升序；否则保持输入顺序。"""
    if not gt:
        return []
    if all("step_id" in row for row in gt):
        return sorted(gt, key=lambda r: int(r["step_id"]))
    return list(gt)


def step_completeness(pred: SOPDocument, gt: list[dict[str, Any]]) -> float:
    """按 ``action_type`` 计算相对 GT 的 Recall（多重集意义下的覆盖比例）。

    算法：对每个动作类别 a，令 n_pred(a)、n_gt(a) 分别为预测步骤与 GT 中该
    ``action_type`` 的出现次数。命中数 = Σ_a min(n_pred(a), n_gt(a))，
    指标 = 命中数 / len(gt)。

    与 ``SOPStep.action_type`` 字段语义一致；比较为精确字符串匹配。

    Args:
        pred: 流水线输出的 ``SOPDocument``（``steps`` 为 ``SOPStep`` 列表）。
        gt: 人工标注步骤列表，每项须含 ``action_type``（与 ``SOPStep`` 对齐）。

    Returns:
        [0.0, 1.0] 的浮点数。``gt`` 为空时返回 1.0（无项可评，视为满足）。
    """
    if not gt:
        return 1.0

    pred_counter = Counter(s.action_type for s in pred.steps)
    gt_types: list[str] = []
    for row in gt:
        gt_types.append(str(row["action_type"]))
    gt_counter = Counter(gt_types)

    keys = set(pred_counter) | set(gt_counter)
    hits = sum(min(pred_counter[k], gt_counter[k]) for k in keys)
    return hits / len(gt)


def keyframe_accuracy(pred: SOPDocument, gt: list[dict[str, Any]]) -> float:
    """关键帧时间戳命中率：贪心按 ``action_type`` 对齐后，逐 GT 步判定时间差。

    对排序后的每个 GT 行，在尚未使用的预测步骤中选取**第一个**
    ``SOPStep.action_type`` 与 GT ``action_type`` 相同的步骤配对；若配对成功且
    ``|SOPStep.video_timestamp - GT['video_timestamp']| <= 2`` 秒则计为命中。
    指标 = 命中数 / len(gt)。

    字段与 ``SOPStep.video_timestamp``、``SOPStep.action_type`` 完全对齐；阈值使用
    模块常量 ``KEYFRAME_TIMESTAMP_TOLERANCE_SEC``。

    Args:
        pred: 含 ``SOPStep`` 的 ``SOPDocument``。
        gt: 每项须含 ``action_type`` 与 ``video_timestamp``（秒，与 ``SOPStep`` 一致）。

    Returns:
        [0.0, 1.0]。``gt`` 为空时返回 1.0。
    """
    if not gt:
        return 1.0

    gt_rows = _ordered_ground_truth(gt)
    pool: list[SOPStep] = list(pred.steps)
    tol = KEYFRAME_TIMESTAMP_TOLERANCE_SEC
    hits = 0

    for row in gt_rows:
        want = str(row["action_type"])
        ts = float(row["video_timestamp"])
        idx = next((i for i, p in enumerate(pool) if p.action_type == want), None)
        if idx is None:
            continue
        step = pool.pop(idx)
        if abs(step.video_timestamp - ts) <= tol:
            hits += 1

    return hits / len(gt_rows)
