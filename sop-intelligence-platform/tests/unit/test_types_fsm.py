"""
T01 · FSM 类型层单元测试（TDD 2.0）

验证 FSMNode / FSMGraph 的 Pydantic 校验、与 SOPStep.step_id 的节点约定，
以及 JSON 序列化往返。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.types.fsm import FSMGraph, FSMNode
from src.types.sop import FSMState


def _three_step_fsm_graph() -> FSMGraph:
    """构造 3 个业务步骤（STEP_1..STEP_3）+ 起止节点的线性拓扑。"""
    nodes = {
        FSMState.BEFORE_START.value: FSMNode(
            node_id=FSMState.BEFORE_START.value,
            step_id=None,
            action_type=None,
            timeout_sec=None,
            keyframe_path=None,
        ),
        "STEP_1": FSMNode(
            node_id="STEP_1",
            step_id=1,
            action_type="pick_tool",
            timeout_sec=120.0,
            keyframe_path="minio://sop-keyframes/demo/step_1.jpg",
        ),
        "STEP_2": FSMNode(
            node_id="STEP_2",
            step_id=2,
            action_type="tighten_bolt",
            timeout_sec=90.0,
            keyframe_path="minio://sop-keyframes/demo/step_2.jpg",
        ),
        "STEP_3": FSMNode(
            node_id="STEP_3",
            step_id=3,
            action_type="inspect",
            timeout_sec=60.0,
            keyframe_path="minio://sop-keyframes/demo/step_3.jpg",
        ),
        FSMState.DONE.value: FSMNode(
            node_id=FSMState.DONE.value,
            step_id=None,
            action_type=None,
            timeout_sec=None,
            keyframe_path=None,
        ),
    }
    edges = [
        (FSMState.BEFORE_START.value, "STEP_1"),
        ("STEP_1", "STEP_2"),
        ("STEP_2", "STEP_3"),
        ("STEP_3", FSMState.DONE.value),
    ]
    return FSMGraph(nodes=nodes, edges=edges)


class TestFSMGraphSerialization:
    """3 步 FSM：序列化 / 反序列化 round-trip。"""

    def test_model_dump_and_validate_round_trip(self) -> None:
        graph = _three_step_fsm_graph()
        payload = graph.model_dump(mode="json")
        raw = json.dumps(payload, ensure_ascii=False)
        restored = FSMGraph.model_validate(json.loads(raw))
        assert restored == graph
        assert restored.nodes["STEP_2"].step_id == 2
        assert restored.nodes["STEP_2"].action_type == "tighten_bolt"

    def test_model_dump_json_round_trip(self) -> None:
        graph = _three_step_fsm_graph()
        raw = graph.model_dump_json()
        restored = FSMGraph.model_validate_json(raw)
        assert restored == graph


class TestFSMGraphBoundaryValidators:
    """必须包含 STEP_0（START）与 STEP_DONE（END）。"""

    def test_missing_start_rejected(self) -> None:
        base = _three_step_fsm_graph()
        nodes = {k: v for k, v in base.nodes.items() if k != FSMState.BEFORE_START.value}
        with pytest.raises(ValidationError) as exc:
            FSMGraph(nodes=nodes, edges=[])
        assert "STEP_0" in str(exc.value) or "起始" in str(exc.value)

    def test_missing_done_rejected(self) -> None:
        base = _three_step_fsm_graph()
        nodes = {k: v for k, v in base.nodes.items() if k != FSMState.DONE.value}
        with pytest.raises(ValidationError) as exc:
            FSMGraph(nodes=nodes, edges=[])
        assert "STEP_DONE" in str(exc.value) or "终止" in str(exc.value)


class TestFSMNodeStepIdAlignment:
    """node_id 与 SOPStep.step_id 物理对齐（STEP_n ↔ n）。"""

    def test_step_node_mismatch_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FSMNode(
                node_id="STEP_2",
                step_id=1,
                action_type="x",
                timeout_sec=None,
                keyframe_path="minio://b/k.jpg",
            )

    def test_start_done_must_not_bind_step_id(self) -> None:
        with pytest.raises(ValidationError):
            FSMNode(
                node_id=FSMState.BEFORE_START.value,
                step_id=1,
                action_type=None,
                timeout_sec=None,
                keyframe_path=None,
            )
