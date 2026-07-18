"""T03 · ActionDetector：ActionSegment vs FSMNode.action_type + 置信度门限。"""

from __future__ import annotations

import pytest

from src.services.fsm.detector import ActionDetector
from src.types.fsm import FSMNode
from src.types.sop import ActionDetectionVerdict, ActionSegment, FSMState


def _segment(
    *,
    action_class: str,
    confidence: float,
    segment_id: int = 1,
) -> ActionSegment:
    return ActionSegment(
        segment_id=segment_id,
        start_frame=0,
        end_frame=16,
        start_time_sec=0.0,
        end_time_sec=0.53,
        action_class=action_class,
        confidence=confidence,
        keyframe_index=8,
    )


def _work_node(*, action_type: str = "tighten_bolt") -> FSMNode:
    return FSMNode(
        node_id="STEP_1",
        step_id=1,
        action_type=action_type,
        timeout_sec=120.0,
        keyframe_path="minio://sop-keyframes/demo/step_1.jpg",
    )


@pytest.fixture
def detector() -> ActionDetector:
    return ActionDetector(conf_low=0.4, conf_high=0.7)


class TestActionDetectorIndustrialScenarios:
    """工业现场常见干扰：类型对但置信低、类型错、起止无期望等。"""

    def test_match_when_type_correct_and_confidence_high(
        self, detector: ActionDetector
    ) -> None:
        seg = _segment(action_class="tighten_bolt", confidence=0.85)
        assert (
            detector.detect(seg, _work_node())
            is ActionDetectionVerdict.MATCH
        )

    def test_uncertain_when_type_correct_but_confidence_between_low_and_high(
        self, detector: ActionDetector
    ) -> None:
        """动作类型正确但置信度处于 (CONF_LOW, CONF_HIGH) 区间 → 不直接 MATCH。"""
        seg = _segment(action_class="tighten_bolt", confidence=0.55)
        assert (
            detector.detect(seg, _work_node())
            is ActionDetectionVerdict.UNCERTAIN
        )

    def test_uncertain_when_confidence_below_low_even_if_type_correct(
        self, detector: ActionDetector
    ) -> None:
        seg = _segment(action_class="tighten_bolt", confidence=0.25)
        assert (
            detector.detect(seg, _work_node())
            is ActionDetectionVerdict.UNCERTAIN
        )

    def test_mismatch_when_type_wrong_with_high_confidence(
        self, detector: ActionDetector
    ) -> None:
        seg = _segment(action_class="wrong_action_entirely", confidence=0.95)
        assert (
            detector.detect(seg, _work_node())
            is ActionDetectionVerdict.MISMATCH
        )

    def test_mismatch_when_type_wrong_with_moderate_confidence(
        self, detector: ActionDetector
    ) -> None:
        """类型完全错误但置信度已超过下阈 → 明确误操作。"""
        seg = _segment(action_class="pick_tool_instead", confidence=0.65)
        assert (
            detector.detect(seg, _work_node())
            is ActionDetectionVerdict.MISMATCH
        )

    def test_uncertain_on_start_node(self, detector: ActionDetector) -> None:
        node = FSMNode(
            node_id=FSMState.BEFORE_START.value,
            step_id=None,
            action_type=None,
            timeout_sec=None,
            keyframe_path=None,
        )
        seg = _segment(action_class="anything", confidence=0.99)
        assert detector.detect(seg, node) is ActionDetectionVerdict.UNCERTAIN

    def test_uncertain_on_done_node(self, detector: ActionDetector) -> None:
        node = FSMNode(
            node_id=FSMState.DONE.value,
            step_id=None,
            action_type=None,
            timeout_sec=None,
            keyframe_path=None,
        )
        assert (
            detector.detect(_segment(action_class="tighten_bolt", confidence=0.99), node)
            is ActionDetectionVerdict.UNCERTAIN
        )


class TestActionDetectorConfig:
    def test_invalid_threshold_order_rejected(self) -> None:
        with pytest.raises(ValueError):
            ActionDetector(conf_low=0.7, conf_high=0.4)
