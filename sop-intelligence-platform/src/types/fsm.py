"""
SOP 边缘 FSM 编译产物 — src/types/fsm.py
========================================

与 `src/types/sop.py` 的契约对齐（只读）：

- **节点 ID**：`STEP_0`（`FSMState.BEFORE_START`）、`STEP_{n}`（n 与 `SOPStep.step_id`
  一一对应）、`STEP_DONE`（`FSMState.DONE`）。禁止与 `FSMState` 枚举值漂移。
- **观测符号**：业务节点上 `action_type` 对应 `SOPStep.action_type`（VideoMAE
  `action_class`）；起止节点可为空。
- **拓扑编码（方案 A）**：`FSMGraph.nodes` 为 ``dict[node_id, FSMNode]``（key 与
  ``node_id`` 一致）；`FSMGraph.edges` 为 ``list[tuple[from_id, to_id]]``，JSON 中
  表现为二元列表，便于边缘运行时 O(1) 查节点。
- **运行快照（T04）**：`RuntimeContext` / `FsmViolationRecord` 供 `FSMRunner.snapshot()`
  序列化给前端。

本模块仅依赖 Pydantic / typing / re / enum（及同层 `FSMState`），符合 Layer 1。
"""

from __future__ import annotations

import enum
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from src.types.sop import FSMState

# 业务步骤节点：STEP_1、STEP_2、…（编号与 SOPStep.step_id 一致）
_WORK_STEP_NODE_ID_RE = re.compile(r"^STEP_([1-9]\d*)$")

FSM_START_NODE_ID: str = FSMState.BEFORE_START.value
FSM_TERMINAL_NODE_ID: str = FSMState.DONE.value


class FSMNode(BaseModel):
    """FSM 拓扑中的单个节点（含动作类别、超时、关键帧等运行元数据）。

    `node_id` 为对外状态名；当为 ``STEP_{n}``（n≥1）时，`step_id` 必须等于 n，
    从而在编译期与 `SOPStep.step_id` 物理绑定。
    """

    node_id: str = Field(..., min_length=1, description='FSM 状态名，如 "STEP_0" / "STEP_1" / "STEP_DONE"')
    step_id: int | None = Field(
        default=None,
        description="对应 SOPStep.step_id；仅 STEP_1..STEP_N 有值，起止节点为 None",
    )
    action_type: str | None = Field(
        default=None,
        description="观测符号（VideoMAE action_class）；起止节点可为 None",
    )
    timeout_sec: float | None = Field(
        default=None,
        ge=0.0,
        description="该状态下允许停留的最大秒数；None 表示不启用超时判定",
    )
    keyframe_path: str | None = Field(
        default=None,
        description="关键帧 MinIO 路径（与 SOPStep.keyframe_path 同源）；起止可为 None",
    )

    @field_validator("node_id")
    @classmethod
    def _node_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("node_id 不得为空字符串")
        return v

    @model_validator(mode="after")
    def _align_step_id_with_node_id(self) -> FSMNode:
        if self.node_id == FSM_START_NODE_ID:
            if self.step_id is not None:
                raise ValueError("STEP_0（起始）节点不得绑定 step_id，应保持为 None")
            return self
        if self.node_id == FSM_TERMINAL_NODE_ID:
            if self.step_id is not None:
                raise ValueError("STEP_DONE（终止）节点不得绑定 step_id，应保持为 None")
            return self
        m = _WORK_STEP_NODE_ID_RE.fullmatch(self.node_id)
        if not m:
            raise ValueError(
                f'node_id "{self.node_id}" 非法：应为 {FSM_START_NODE_ID}、'
                f"{FSM_TERMINAL_NODE_ID} 或 STEP_<正整数>（与 SOPStep.step_id 对齐）"
            )
        expected = int(m.group(1))
        if self.step_id != expected:
            raise ValueError(
                f'node_id "{self.node_id}" 要求 step_id=={expected}，与 SOPStep.step_id 对齐，'
                f"收到 step_id={self.step_id!r}"
            )
        if not (self.action_type and self.action_type.strip()):
            raise ValueError(f'业务节点 "{self.node_id}" 必须提供非空的 action_type（观测符号）')
        if not (self.keyframe_path and self.keyframe_path.strip()):
            raise ValueError(f'业务节点 "{self.node_id}" 必须提供非空的 keyframe_path')
        return self


class FSMGraph(BaseModel):
    """完整步骤拓扑：节点表 + 有向边列表（可表达线性主路径及后续扩展）。"""

    nodes: dict[str, FSMNode] = Field(
        ...,
        description='节点字典，key 必须与 FSMNode.node_id 一致；必须含 STEP_0 与 STEP_DONE',
    )
    edges: list[tuple[str, str]] = Field(
        default_factory=list,
        description="有向边 (from_node_id, to_node_id)，端点必须存在于 nodes",
    )

    @model_validator(mode="after")
    def _validate_topology(self) -> FSMGraph:
        if FSM_START_NODE_ID not in self.nodes:
            raise ValueError(
                f"FSM 必须包含起始节点 {FSM_START_NODE_ID}（对应 FSMState.BEFORE_START / START）"
            )
        if FSM_TERMINAL_NODE_ID not in self.nodes:
            raise ValueError(
                f"FSM 必须包含终止节点 {FSM_TERMINAL_NODE_ID}（对应 FSMState.DONE / END）"
            )
        for key, node in self.nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"nodes 字典 key ({key!r}) 与 FSMNode.node_id ({node.node_id!r}) 不一致"
                )
        for a, b in self.edges:
            if a not in self.nodes:
                raise ValueError(f'边引用了不存在的源节点 "{a}"')
            if b not in self.nodes:
                raise ValueError(f'边引用了不存在的目标节点 "{b}"')
        return self

    @field_validator("edges", mode="before")
    @classmethod
    def _normalize_edges(cls, v: Any) -> list[tuple[str, str]]:
        """允许 JSON 中边以二元列表形式出现。"""
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError("edges 必须为 list")
        out: list[tuple[str, str]] = []
        for item in v:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append((str(item[0]), str(item[1])))
            else:
                raise ValueError(f"每条边应为 [from_id, to_id] 二元组，收到: {item!r}")
        return out


# ---------------------------------------------------------------------------
# 运行时快照与违规记录（T04：FSMRunner 导出）
# ---------------------------------------------------------------------------


class FsmViolationKind(str, enum.Enum):
    """FSM 运行期记录的违规类别。"""

    TIMEOUT = "TIMEOUT"
    MISMATCH = "MISMATCH"


class FsmViolationRecord(BaseModel):
    """单条违规记录，供前端与审计回放。"""

    kind: FsmViolationKind = Field(..., description="违规类型")
    node_id: str = Field(..., min_length=1, description="发生时的 FSM 节点 ID")
    detail: str = Field(default="", description="补充说明（如停留时长与阈值）")


class RuntimeContext(BaseModel):
    """FSM 运行时的可序列化快照（当前步、耗时、告警与违规）。"""

    current_node_id: str = Field(..., min_length=1, description="当前 FSM 节点 ID")
    current_step_id: int | None = Field(
        ...,
        description="当前绑定的 SOP step_id；位于 STEP_0 / STEP_DONE 时为 None",
    )
    dwell_sec: float = Field(..., ge=0.0, description="进入当前节点以来经过的秒数")
    elapsed_sec_since_start: float = Field(
        ...,
        ge=0.0,
        description="自 Runner 创建以来经过的秒数",
    )
    timeout_alert_active: bool = Field(
        ...,
        description="当前节点是否已触发超时告警（直至成功 MATCH 离开该节点）",
    )
    violations: list[FsmViolationRecord] = Field(
        default_factory=list,
        description="累计违规列表（顺序即发生顺序）",
    )
