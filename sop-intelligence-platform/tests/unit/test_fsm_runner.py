"""T04 · FSMRunner：五步流程、超时告警、误操作保持、线程安全。"""

from __future__ import annotations

import threading

from src.services.fsm.runtime import FSMRunner
from src.types.fsm import (
    FSMGraph,
    FSMNode,
    FSM_TERMINAL_NODE_ID,
    FSM_START_NODE_ID,
    FsmViolationKind,
    RuntimeContext,
)
from src.types.sop import ActionDetectionVerdict


class FakeMonotonic:
    """可注入的单调时钟，便于控制停留时长。"""

    __slots__ = ("t",)

    def __init__(self, start: float = 0.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


def _five_step_graph() -> FSMGraph:
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
    for i in range(1, 6):
        nid = f"STEP_{i}"
        nodes[nid] = FSMNode(
            node_id=nid,
            step_id=i,
            action_type=f"action_{i}",
            timeout_sec=10.0,
            keyframe_path=f"minio://demo/step_{i}.jpg",
        )
    edges: list[tuple[str, str]] = []
    prev = FSM_START_NODE_ID
    for i in range(1, 6):
        cur = f"STEP_{i}"
        edges.append((prev, cur))
        prev = cur
    edges.append((prev, FSM_TERMINAL_NODE_ID))
    return FSMGraph(nodes=nodes, edges=edges)


def _advance_to_step(runner: FSMRunner, step: int) -> None:
    """从 STEP_0 起经若干次 MATCH 到达 STEP_{step}（1..5）。"""
    assert 1 <= step <= 5
    for _ in range(step):
        runner.handle_event(ActionDetectionVerdict.MATCH)


class TestFSMRunnerHappyPathFiveSteps:
    def test_normal_completion_five_steps(self) -> None:
        clock = FakeMonotonic(0.0)
        g = _five_step_graph()
        r = FSMRunner(g, clock=clock)
        for _ in range(6):
            r.handle_event(ActionDetectionVerdict.MATCH)
        ctx = r.snapshot()
        assert ctx.current_node_id == FSM_TERMINAL_NODE_ID
        assert ctx.current_step_id is None
        assert ctx.violations == []
        assert ctx.timeout_alert_active is False
        assert isinstance(ctx, RuntimeContext)


class TestFSMRunnerMidStepTimeout:
    def test_timeout_on_step_three_then_recover(self) -> None:
        clock = FakeMonotonic(0.0)
        r = FSMRunner(_five_step_graph(), clock=clock)
        _advance_to_step(r, 3)
        assert r.snapshot().current_node_id == "STEP_3"

        clock.advance(11.0)
        r.check_timeout()
        ctx = r.snapshot()
        assert ctx.timeout_alert_active is True
        assert ctx.current_node_id == "STEP_3"
        assert any(v.kind is FsmViolationKind.TIMEOUT for v in ctx.violations)

        r.check_timeout()
        assert len([v for v in r.snapshot().violations if v.kind is FsmViolationKind.TIMEOUT]) == 1

        r.handle_event(ActionDetectionVerdict.MATCH)
        ctx2 = r.snapshot()
        assert ctx2.current_node_id == "STEP_4"
        assert ctx2.timeout_alert_active is False


class TestFSMRunnerMismatchHold:
    def test_mismatch_keeps_state_and_records_violation(self) -> None:
        clock = FakeMonotonic(0.0)
        r = FSMRunner(_five_step_graph(), clock=clock)
        _advance_to_step(r, 2)
        assert r.snapshot().current_node_id == "STEP_2"

        r.handle_event(ActionDetectionVerdict.MISMATCH)
        ctx = r.snapshot()
        assert ctx.current_node_id == "STEP_2"
        assert ctx.current_step_id == 2
        assert len(ctx.violations) == 1
        assert ctx.violations[0].kind is FsmViolationKind.MISMATCH

        r.handle_event(ActionDetectionVerdict.MATCH)
        assert r.snapshot().current_node_id == "STEP_3"


class TestFSMRunnerThreadSafety:
    def test_concurrent_public_methods_no_exceptions(self) -> None:
        clock = FakeMonotonic(0.0)
        g = _five_step_graph()
        r = FSMRunner(g, clock=clock)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                for _ in range(80):
                    r.handle_event(ActionDetectionVerdict.MATCH)
                    r.handle_event(ActionDetectionVerdict.MISMATCH)
                    r.handle_event(ActionDetectionVerdict.UNCERTAIN)
                    r.check_timeout()
                    r.snapshot()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        s = r.snapshot()
        assert s.current_node_id in g.nodes
