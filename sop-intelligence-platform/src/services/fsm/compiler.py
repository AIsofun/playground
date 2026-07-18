"""将已校验的 `SOPDocument` 编译为 `FSMGraph`（方案 A 拓扑）。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.types.fsm import FSMGraph, FSMNode, FSM_START_NODE_ID, FSM_TERMINAL_NODE_ID
from src.types.sop import SOPDocument, SOPStep

__all__ = ["FSMCompilationError", "SOPToFSMCompiler"]

_TIME_EPS = 1e-6


class FSMCompilationError(Exception):
    """FSM 编译失败：与 `SOPCompilationError` 区分，用于 SOP→FSM 规则违反。"""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}


class SOPToFSMCompiler:
    """SOP 文档 → 线性 `FSMGraph`：一步一节点，起止为合成节点。

    **重复 action_type**：MVP 策略为 **拒绝编译**（边缘观测无法唯一步骤消歧）。

    **timeout_sec**：在专家视频时长 ``expert_video_duration_sec`` 上整体加 **50%**
    冗余得到总预算 ``1.5 * D``，再按各步 `video_timestamp` 与上一步的间隔比例
    （最后一步吸收「末步时间戳 → 视频结束」的尾部）分配到每个业务节点。
    ``STEP_0`` / ``STEP_DONE`` 不设超时（``None``）。
    """

    def compile(
        self,
        doc: SOPDocument,
        *,
        expert_video_duration_sec: float,
    ) -> FSMGraph:
        if expert_video_duration_sec <= 0:
            raise FSMCompilationError(
                "expert_video_duration_sec 必须为正数",
                details={"expert_video_duration_sec": expert_video_duration_sec},
            )

        try:
            doc = SOPDocument.model_validate(doc.model_dump())
        except ValidationError as e:
            raise FSMCompilationError(
                "SOPDocument 校验失败",
                details={"errors": e.errors()},
            ) from e

        steps = sorted(doc.steps, key=lambda s: s.step_id)
        n = len(steps)
        if n == 0:
            raise FSMCompilationError("steps 不得为空", details={"steps": "empty"})

        for idx, s in enumerate(steps, start=1):
            if s.step_id != idx:
                raise FSMCompilationError(
                    "step_id 必须与列表顺序一致且为 1..N",
                    details={
                        "expected_step_id": idx,
                        "got_step_id": s.step_id,
                        "step_index": idx - 1,
                    },
                )

        action_types: set[str] = set()
        for s in steps:
            if s.action_type in action_types:
                raise FSMCompilationError(
                    "存在重复 action_type，当前策略为拒绝编译（边缘无法唯一步骤绑定）",
                    details={"action_type": s.action_type},
                )
            action_types.add(s.action_type)

        timeouts = _per_step_timeout_sec(
            steps,
            expert_video_duration_sec=expert_video_duration_sec,
        )

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

        for s, timeout_sec in zip(steps, timeouts, strict=True):
            nid = f"STEP_{s.step_id}"
            nodes[nid] = FSMNode(
                node_id=nid,
                step_id=s.step_id,
                action_type=s.action_type,
                timeout_sec=timeout_sec,
                keyframe_path=s.keyframe_path,
            )

        edges: list[tuple[str, str]] = []
        prev = FSM_START_NODE_ID
        for s in steps:
            cur = f"STEP_{s.step_id}"
            edges.append((prev, cur))
            prev = cur
        edges.append((prev, FSM_TERMINAL_NODE_ID))

        try:
            return FSMGraph.model_validate({"nodes": nodes, "edges": edges})
        except ValidationError as e:
            raise FSMCompilationError(
                "FSMGraph 校验失败",
                details={"errors": e.errors()},
            ) from e


def _per_step_timeout_sec(
    steps: list[SOPStep],
    *,
    expert_video_duration_sec: float,
) -> list[float]:
    """按时间轴间隔比例分配 ``1.5 * D`` 到各业务步骤。"""
    d = float(expert_video_duration_sec)
    budget = 1.5 * d

    prev_t = 0.0
    spans: list[float] = []
    for s in steps:
        spans.append(max(s.video_timestamp - prev_t, _TIME_EPS))
        prev_t = s.video_timestamp

    if steps:
        tail = max(0.0, d - steps[-1].video_timestamp)
        spans[-1] = max(spans[-1] + tail, _TIME_EPS)

    total = sum(spans)
    if total <= 0:
        return [budget / len(steps)] * len(steps)
    return [budget * (w / total) for w in spans]
