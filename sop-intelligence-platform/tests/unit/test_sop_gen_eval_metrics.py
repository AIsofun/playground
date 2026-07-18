"""T09 · sop_gen_eval.metrics 纯逻辑单测（无 I/O）。"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.types.sop import SOPDocument, SOPStep
from tests.harness.sop_gen_eval.metrics import (
    KEYFRAME_TIMESTAMP_TOLERANCE_SEC,
    keyframe_accuracy,
    step_completeness,
)


def _doc(steps: list[SOPStep]) -> SOPDocument:
    return SOPDocument(
        sop_id="550e8400-e29b-41d4-a716-446655440000",
        product_id="PROD-001",
        version="PROD-001-v1.0",
        steps=steps,
        total_steps=len(steps),
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        source_video_paths=["minio://sop-videos/PROD-001/demo.mp4"],
        status="draft",
    )


def _step(
    step_id: int,
    action_type: str,
    video_timestamp: float,
) -> SOPStep:
    return SOPStep(
        step_id=step_id,
        description="测试步骤",
        action_object="零件",
        keyframe_path=f"minio://sop-keyframes/test/step_{step_id}.jpg",
        video_timestamp=video_timestamp,
        action_type=action_type,
        warnings=[],
    )


class TestStepCompleteness:
    def test_perfect_recall(self) -> None:
        gt = [
            {"action_type": "a", "video_timestamp": 0.0},
            {"action_type": "b", "video_timestamp": 1.0},
        ]
        pred = _doc(
            [_step(1, "a", 0.0), _step(2, "b", 1.0)],
        )
        assert step_completeness(pred, gt) == 1.0

    def test_multiset_recall_partial(self) -> None:
        """GT 两个 a，预测仅一个 a → min 计数之和为 2，分母 3。"""
        gt = [
            {"action_type": "a", "video_timestamp": 0.0},
            {"action_type": "a", "video_timestamp": 1.0},
            {"action_type": "b", "video_timestamp": 2.0},
        ]
        pred = _doc([_step(1, "a", 0.0), _step(2, "b", 2.0)])
        assert step_completeness(pred, gt) == pytest.approx(2.0 / 3.0)

    def test_extra_pred_does_not_reduce_recall(self) -> None:
        gt = [{"action_type": "x", "video_timestamp": 0.0}]
        pred = _doc([_step(1, "x", 0.0), _step(2, "y", 9.0)])
        assert step_completeness(pred, gt) == 1.0

    def test_empty_gt_is_one(self) -> None:
        pred = _doc([_step(1, "x", 0.0)])
        assert step_completeness(pred, []) == 1.0


class TestKeyframeAccuracy:
    def test_all_within_tolerance(self) -> None:
        gt = [
            {"step_id": 1, "action_type": "a", "video_timestamp": 1.0},
            {"step_id": 2, "action_type": "b", "video_timestamp": 5.0},
        ]
        pred = _doc(
            [
                _step(1, "a", 1.0 + KEYFRAME_TIMESTAMP_TOLERANCE_SEC),
                _step(2, "b", 5.0 - KEYFRAME_TIMESTAMP_TOLERANCE_SEC),
            ],
        )
        assert keyframe_accuracy(pred, gt) == 1.0

    def test_boundary_exclusive_over_tolerance(self) -> None:
        gt = [{"action_type": "a", "video_timestamp": 0.0}]
        pred = _doc(
            [_step(1, "a", KEYFRAME_TIMESTAMP_TOLERANCE_SEC + 0.01)],
        )
        assert keyframe_accuracy(pred, gt) == 0.0

    def test_greedy_match_respects_gt_order_not_pred_order(self) -> None:
        """GT 顺序 a→b，预测顺序 b→a，仍应两两正确配对。"""
        gt = [
            {"action_type": "a", "video_timestamp": 1.0},
            {"action_type": "b", "video_timestamp": 2.0},
        ]
        pred = _doc([_step(1, "b", 2.0), _step(2, "a", 1.0)])
        assert keyframe_accuracy(pred, gt) == 1.0

    def test_unmatched_action_type_counts_as_miss(self) -> None:
        gt = [{"action_type": "need", "video_timestamp": 1.0}]
        pred = _doc([_step(1, "other", 1.0)])
        assert keyframe_accuracy(pred, gt) == 0.0

    def test_step_id_sorts_gt_before_matching(self) -> None:
        """GT 字典乱序但含 step_id 时，按 SOPStep.step_id 语义升序对齐。"""
        gt = [
            {"step_id": 2, "action_type": "b", "video_timestamp": 2.0},
            {"step_id": 1, "action_type": "a", "video_timestamp": 1.0},
        ]
        pred = _doc([_step(1, "a", 1.0), _step(2, "b", 2.0)])
        assert keyframe_accuracy(pred, gt) == 1.0

    def test_empty_gt_is_one(self) -> None:
        pred = _doc([_step(1, "a", 0.0)])
        assert keyframe_accuracy(pred, []) == 1.0
