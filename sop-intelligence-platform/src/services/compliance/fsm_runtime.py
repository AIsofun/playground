"""合规场景下的服务端 FSM 运行封装（无 VLM / 无网络）。

将 ``FSMGraph`` 与现有 ``FSMRunner`` + ``ActionDetector`` 组合为单入口：
``on_segment`` 先对当前节点做动作观测对齐，再驱动 Runner 步进/保持。

约束（``src/services/compliance/AGENTS.md``）：
    本模块不得调用 VLM 或任何 HTTP/gRPC 客户端；仅内存态与类型层交互。

行为与 ``docs/module-specs/sop-fsm.md`` T03 及 ``docs/domain-logic.md`` 一致：
    MATCH 沿主链前进；MISMATCH 记违规；UNCERTAIN 不改变节点；
    ``check_timeout`` 委托 ``FSMRunner``（依赖节点 ``timeout_sec``）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.services.fsm.detector import ActionDetector
from src.services.fsm.runtime import FSMRunner
from src.types.fsm import FSMGraph, FSM_TERMINAL_NODE_ID, FSM_START_NODE_ID, RuntimeContext
from src.types.sop import ActionDetectionVerdict, ActionSegment

__all__ = ["ComplianceFsmRuntime", "ComplianceFsmStepResult"]


def _unique_successor(edges: list[tuple[str, str]], src: str) -> str | None:
    """线性主链：返回 ``src`` 的唯一出边目标；若无出边则 None。"""
    dsts = [b for a, b in edges if a == src]
    if not dsts:
        return None
    if len(dsts) != 1:
        raise ValueError(f"节点 {src!r} 出边数不为 1，合规 MVP 仅支持线性主链")
    return dsts[0]


class ComplianceFsmStepResult(BaseModel):
    """单帧/片段观测后的判定与 FSM 快照。"""

    verdict: ActionDetectionVerdict = Field(..., description="ActionDetector 输出")
    context: RuntimeContext = Field(..., description="本步 handle_event 之后的 Runner 快照")


class ComplianceFsmRuntime:
    """服务端合规用 FSM：封装 Runner + Detector，不发起外部 I/O。"""

    def __init__(
        self,
        graph: FSMGraph,
        *,
        clock=None,
        conf_low: float | None = None,
        conf_high: float | None = None,
    ) -> None:
        self._graph = graph
        self._runner = FSMRunner(graph, clock=clock)
        self._detector = ActionDetector(conf_low=conf_low, conf_high=conf_high)

    @property
    def graph(self) -> FSMGraph:
        return self._graph

    def _verdict_bootstrap_start(self, segment: ActionSegment) -> ActionDetectionVerdict:
        """``STEP_0`` 无期望动作：将观测与**主链下一节点**对齐（阈值同 ``ActionDetector``）。"""
        nxt = _unique_successor(self._graph.edges, FSM_START_NODE_ID)
        if nxt is None:
            return ActionDetectionVerdict.UNCERTAIN
        next_node = self._graph.nodes[nxt]
        expected = next_node.action_type
        if expected is None or not expected.strip():
            return ActionDetectionVerdict.UNCERTAIN
        if segment.action_class != expected:
            return ActionDetectionVerdict.MISMATCH
        if segment.confidence < self._detector.conf_low:
            return ActionDetectionVerdict.UNCERTAIN
        if segment.confidence < self._detector.conf_high:
            return ActionDetectionVerdict.UNCERTAIN
        return ActionDetectionVerdict.MATCH

    def _verdict_for_segment(self, segment: ActionSegment, current_id: str) -> ActionDetectionVerdict:
        if current_id == FSM_START_NODE_ID:
            return self._verdict_bootstrap_start(segment)
        return self._detector.detect(segment, self._graph.nodes[current_id])

    def on_segment(self, segment: ActionSegment) -> ComplianceFsmStepResult:
        """对当前节点检测 ``segment``，将 ``verdict`` 交给 Runner 并返回新快照。"""
        snap = self._runner.snapshot()
        current_id = snap.current_node_id
        if current_id == FSM_TERMINAL_NODE_ID:
            verdict = self._detector.detect(segment, self._graph.nodes[current_id])
        else:
            verdict = self._verdict_for_segment(segment, current_id)
        self._runner.handle_event(verdict)
        after = self._runner.snapshot()
        return ComplianceFsmStepResult(verdict=verdict, context=after)

    def check_timeout(self) -> None:
        """若当前节点配置 ``timeout_sec``，按 Runner 规则检查并可能追加 TIMEOUT 违规。"""
        self._runner.check_timeout()

    def snapshot(self) -> RuntimeContext:
        """当前运行快照（线程安全，同 ``FSMRunner.snapshot``）。"""
        return self._runner.snapshot()
