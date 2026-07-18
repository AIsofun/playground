"""ComplianceFsmRuntime：步进、误配、超时（无 I/O）。"""

from __future__ import annotations

from src.services.compliance.fsm_runtime import ComplianceFsmRuntime, ComplianceFsmStepResult
from src.types.fsm import (
    FSMGraph,
    FSMNode,
    FSM_TERMINAL_NODE_ID,
    FSM_START_NODE_ID,
    FsmViolationKind,
    RuntimeContext,
)
from src.types.sop import ActionDetectionVerdict, ActionSegment


class _FakeClock:
    __slots__ = ("t",)

    def __init__(self, t: float = 0.0) -> None:
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


def _three_step_graph() -> FSMGraph:
    nodes: dict[str, FSMNode] = {
        FSM_START_NODE_ID: FSMNode(
            node_id=FSM_START_NODE_ID,
            step_id=None,
            action_type=None,
            timeout_sec=None,
            keyframe_path=None,
        ),
        FSM_TERMINAL_NODE_ID: FSMNode(
            node_id=FSM_TERMINAL_NODE_ID,
            step_id=None,
            action_type=None,
            timeout_sec=None,
            keyframe_path=None,
        ),
    }
    for i in range(1, 4):
        nid = f"STEP_{i}"
        nodes[nid] = FSMNode(
            node_id=nid,
            step_id=i,
            action_type=f"act_{i}",
            timeout_sec=5.0,
            keyframe_path=f"minio://b/k{i}.jpg",
        )
    edges: list[tuple[str, str]] = []
    prev = FSM_START_NODE_ID
    for i in range(1, 4):
        cur = f"STEP_{i}"
        edges.append((prev, cur))
        prev = cur
    edges.append((prev, FSM_TERMINAL_NODE_ID))
    return FSMGraph(nodes=nodes, edges=edges)


def _seg(action: str, conf: float, sid: int = 1) -> ActionSegment:
    return ActionSegment(
        segment_id=sid,
        start_frame=0,
        end_frame=8,
        start_time_sec=0.0,
        end_time_sec=0.5,
        action_class=action,
        confidence=conf,
        keyframe_index=4,
    )


def test_happy_path_reaches_done() -> None:
    """STEP_0 引导至 STEP_1 后，须在 STEP_k 上再次观测 ``act_k`` 才 MATCH 至下一步。"""
    rt = ComplianceFsmRuntime(_three_step_graph(), conf_low=0.2, conf_high=0.8)
    r0 = rt.on_segment(_seg("act_1", 0.95, sid=0))
    assert r0.verdict is ActionDetectionVerdict.MATCH
    assert r0.context.current_node_id == "STEP_1"

    r1 = rt.on_segment(_seg("act_1", 0.95, sid=1))
    assert r1.verdict is ActionDetectionVerdict.MATCH
    assert r1.context.current_node_id == "STEP_2"

    r2 = rt.on_segment(_seg("act_2", 0.95, sid=2))
    assert r2.verdict is ActionDetectionVerdict.MATCH
    assert r2.context.current_node_id == "STEP_3"

    r3 = rt.on_segment(_seg("act_3", 0.95, sid=3))
    assert r3.verdict is ActionDetectionVerdict.MATCH
    assert r3.context.current_node_id == FSM_TERMINAL_NODE_ID


def test_mismatch_records_violation_state_unchanged() -> None:
    rt = ComplianceFsmRuntime(_three_step_graph(), conf_low=0.2, conf_high=0.8)
    r = rt.on_segment(_seg("wrong_action", 0.95, sid=1))
    assert r.verdict is ActionDetectionVerdict.MISMATCH
    assert r.context.current_node_id == FSM_START_NODE_ID
    assert len(r.context.violations) == 1
    assert r.context.violations[0].kind is FsmViolationKind.MISMATCH


def test_uncertain_does_not_advance() -> None:
    rt = ComplianceFsmRuntime(_three_step_graph(), conf_low=0.2, conf_high=0.8)
    r = rt.on_segment(_seg("act_1", 0.5, sid=1))
    assert r.verdict is ActionDetectionVerdict.UNCERTAIN
    assert r.context.current_node_id == FSM_START_NODE_ID


def test_timeout_check_appends_timeout_violation() -> None:
    clock = _FakeClock(0.0)
    rt = ComplianceFsmRuntime(_three_step_graph(), clock=clock, conf_low=0.2, conf_high=0.8)
    rt.on_segment(_seg("act_1", 0.95, sid=1))
    clock.advance(6.0)
    rt.check_timeout()
    snap = rt.snapshot()
    assert snap.timeout_alert_active is True
    assert any(v.kind is FsmViolationKind.TIMEOUT for v in snap.violations)


def test_step_result_model() -> None:
    snap = RuntimeContext(
        current_node_id=FSM_START_NODE_ID,
        current_step_id=None,
        dwell_sec=0.0,
        elapsed_sec_since_start=0.0,
        timeout_alert_active=False,
        violations=[],
    )
    m = ComplianceFsmStepResult(
        verdict=ActionDetectionVerdict.MATCH,
        context=snap,
    )
    assert m.verdict is ActionDetectionVerdict.MATCH
