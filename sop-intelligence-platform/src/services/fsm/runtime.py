"""FSM 运行态：事件驱动步进、超时告警与线程安全快照。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from src.types.fsm import (
    FSMGraph,
    FSM_TERMINAL_NODE_ID,
    FSM_START_NODE_ID,
    FsmViolationKind,
    FsmViolationRecord,
    RuntimeContext,
)
from src.types.sop import ActionDetectionVerdict

__all__ = ["FSMRunner"]


def _build_next_lookup(edges: list[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for src, dst in edges:
        if src in out and out[src] != dst:
            raise ValueError(
                f"FSM 出边不唯一：源节点 {src!r} 同时指向 {out[src]!r} 与 {dst!r}"
            )
        out[src] = dst
    return out


def _assert_reaches_terminal(next_map: dict[str, str]) -> None:
    cur = FSM_START_NODE_ID
    seen: set[str] = set()
    while cur != FSM_TERMINAL_NODE_ID:
        if cur in seen:
            raise ValueError("FSM 主链存在环，无法到达终止节点")
        seen.add(cur)
        nxt = next_map.get(cur)
        if nxt is None:
            raise ValueError(f"FSM 主链中断：节点 {cur!r} 无出边")
        cur = nxt


class FSMRunner:
    """在内存中驱动线性 `FSMGraph`：MATCH 步进、超时告警、违规累积。

    所有公开方法使用 ``threading.RLock`` 保护可变状态，可在多线程（监控线程 +
    推理回调）下并发调用。

    **handle_event**：仅 ``ActionDetectionVerdict.MATCH`` 沿编译器生成的主链前进一步；
    ``MISMATCH`` 记录违规并保持当前节点；``UNCERTAIN`` 不改变状态。

    **check_timeout**：若当前节点配置了 ``FSMNode.timeout_sec``，且停留时间超过阈值，
    则进入 ``timeout_alert_active`` 并追加一条 ``TIMEOUT`` 违规（同一节点停留周期内
    只触发一次，直至 MATCH 离开该节点后重置）。
    """

    def __init__(
        self,
        graph: FSMGraph,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._graph = graph
        self._next = _build_next_lookup(graph.edges)
        _assert_reaches_terminal(self._next)

        self._clock: Callable[[], float] = clock if clock is not None else self._default_clock
        self._lock = threading.RLock()

        self._started_at: float = self._clock()
        self._current_id: str = FSM_START_NODE_ID
        self._entered_at: float = self._started_at
        self._timeout_latched: bool = False
        self._violations: list[FsmViolationRecord] = []

    @staticmethod
    def _default_clock() -> float:
        return time.monotonic()

    def handle_event(self, verdict: ActionDetectionVerdict) -> None:
        with self._lock:
            if verdict is ActionDetectionVerdict.MATCH:
                self._on_match_locked()
            elif verdict is ActionDetectionVerdict.MISMATCH:
                self._on_mismatch_locked()
            # UNCERTAIN：保持状态

    def _on_match_locked(self) -> None:
        if self._current_id == FSM_TERMINAL_NODE_ID:
            return
        nxt = self._next.get(self._current_id)
        if nxt is None:
            return
        self._current_id = nxt
        self._entered_at = self._clock()
        self._timeout_latched = False

    def _on_mismatch_locked(self) -> None:
        self._violations.append(
            FsmViolationRecord(
                kind=FsmViolationKind.MISMATCH,
                node_id=self._current_id,
                detail="观测与当前节点期望 action_type 不一致（已记录，状态保持）",
            )
        )

    def check_timeout(self) -> None:
        with self._lock:
            if self._timeout_latched:
                return
            node = self._graph.nodes[self._current_id]
            limit = node.timeout_sec
            if limit is None:
                return
            now = self._clock()
            dwell = now - self._entered_at
            if dwell > limit:
                self._timeout_latched = True
                self._violations.append(
                    FsmViolationRecord(
                        kind=FsmViolationKind.TIMEOUT,
                        node_id=self._current_id,
                        detail=f"dwell_sec={dwell:.3f} > timeout_sec={limit:.3f}",
                    )
                )

    def snapshot(self) -> RuntimeContext:
        with self._lock:
            now = self._clock()
            node = self._graph.nodes[self._current_id]
            dwell = max(0.0, now - self._entered_at)
            elapsed = max(0.0, now - self._started_at)
            vcopy = [FsmViolationRecord.model_validate(v.model_dump()) for v in self._violations]
            return RuntimeContext(
                current_node_id=self._current_id,
                current_step_id=node.step_id,
                dwell_sec=dwell,
                elapsed_sec_since_start=elapsed,
                timeout_alert_active=self._timeout_latched,
                violations=vcopy,
            )

    def rollback(self) -> bool:
        """回退到前一节点。返回是否成功（起始节点不可回退）。

        线程安全；回退后重置该节点的超时闩锁。
        """
        with self._lock:
            if self._current_id == FSM_START_NODE_ID:
                return False
            # 在 edges 中找到指向当前节点的前驱
            prev_id: str | None = None
            for src, dst in self._graph.edges:
                if dst == self._current_id:
                    prev_id = src
                    break
            if prev_id is None:
                return False
            self._current_id = prev_id
            self._entered_at = self._clock()
            self._timeout_latched = False
            return True
