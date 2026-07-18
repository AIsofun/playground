"""T02 · SOPToFSMCompiler：SOPDocument → FSMGraph（Mock / 纯逻辑）。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.services.fsm.compiler import FSMCompilationError, SOPToFSMCompiler
from src.types.fsm import FSM_TERMINAL_NODE_ID, FSM_START_NODE_ID, FSMGraph
from src.types.sop import SOPDocument, SOPStep


def _doc_two_steps() -> SOPDocument:
    return SOPDocument(
        sop_id="550e8400-e29b-41d4-a716-446655440000",
        product_id="PROD-001",
        version="PROD-001-v1.0",
        steps=[
            SOPStep(
                step_id=1,
                description="拿扳手",
                action_object="扳手",
                keyframe_path="minio://sop-keyframes/job/step_1.jpg",
                video_timestamp=20.0,
                action_type="pick_tool",
                warnings=[],
            ),
            SOPStep(
                step_id=2,
                description="拧紧",
                action_object="螺栓",
                keyframe_path="minio://sop-keyframes/job/step_2.jpg",
                video_timestamp=50.0,
                action_type="tighten_bolt",
                warnings=[],
            ),
        ],
        total_steps=2,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_video_paths=["minio://sop-videos/PROD-001/demo.mp4"],
        status="draft",
    )


class TestSOPToFSMCompilerHappyPath:
    """稳定输出：同一输入 → 同一 FSMGraph。"""

    def test_stable_fsm_graph_two_steps(self) -> None:
        doc = _doc_two_steps()
        compiler = SOPToFSMCompiler()
        d = 100.0
        g1 = compiler.compile(doc, expert_video_duration_sec=d)
        g2 = compiler.compile(doc, expert_video_duration_sec=d)
        assert g1 == g2
        assert set(g1.nodes) == {
            FSM_START_NODE_ID,
            "STEP_1",
            "STEP_2",
            FSM_TERMINAL_NODE_ID,
        }
        assert g1.edges == [
            (FSM_START_NODE_ID, "STEP_1"),
            ("STEP_1", "STEP_2"),
            ("STEP_2", FSM_TERMINAL_NODE_ID),
        ]
        assert g1.nodes["STEP_1"].action_type == "pick_tool"
        assert g1.nodes["STEP_1"].keyframe_path.endswith("step_1.jpg")
        assert g1.nodes["STEP_0"].timeout_sec is None
        assert g1.nodes["STEP_DONE"].timeout_sec is None
        # 总预算 = 100 * 1.5 = 150；按时间轴权重分配，和应为 150
        t1 = g1.nodes["STEP_1"].timeout_sec
        t2 = g1.nodes["STEP_2"].timeout_sec
        assert t1 is not None and t2 is not None
        assert abs((t1 + t2) - 150.0) < 1e-6

    def test_round_trip_fsm_graph_validate(self) -> None:
        doc = _doc_two_steps()
        g = SOPToFSMCompiler().compile(doc, expert_video_duration_sec=80.0)
        dumped = g.model_dump(mode="json")
        again = FSMGraph.model_validate(dumped)
        assert again == g


class TestSOPToFSMCompilerRejections:
    def test_duplicate_action_type(self) -> None:
        doc = _doc_two_steps()
        bad_steps = list(doc.steps)
        bad_steps[1] = bad_steps[1].model_copy(update={"action_type": "pick_tool"})
        bad = doc.model_copy(update={"steps": bad_steps, "total_steps": 2})
        with pytest.raises(FSMCompilationError) as exc:
            SOPToFSMCompiler().compile(bad, expert_video_duration_sec=100.0)
        assert "重复" in str(exc.value) or "action_type" in str(exc.value).lower()

    def test_step_id_not_consecutive_rejected(self) -> None:
        doc = _doc_two_steps()
        bad_second = doc.steps[1].model_copy(update={"step_id": 3})
        bad = doc.model_copy(update={"steps": [doc.steps[0], bad_second], "total_steps": 2})
        with pytest.raises(FSMCompilationError) as exc:
            SOPToFSMCompiler().compile(bad, expert_video_duration_sec=100.0)
        assert "step_id" in str(exc.value)

    def test_non_positive_video_duration(self) -> None:
        with pytest.raises(FSMCompilationError):
            SOPToFSMCompiler().compile(_doc_two_steps(), expert_video_duration_sec=0.0)
