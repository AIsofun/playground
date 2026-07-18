"""将实时 ``ActionSegment`` 与当前 ``FSMNode`` 的期望动作对齐（服务层）。"""

from __future__ import annotations

from src.config.vlm import CONF_HIGH, CONF_LOW
from src.types.fsm import FSMNode
from src.types.sop import ActionDetectionVerdict, ActionSegment, FSMState

__all__ = ["ActionDetector"]


class ActionDetector:
    """对比 VideoMAE 片段与 FSM 当前节点期望的 `action_type`，输出三态判定。

    阈值默认与 `src/config/vlm.py` 中合规域的 ``CONF_LOW`` / ``CONF_HIGH`` 一致；
    单测可通过构造函数注入覆盖。

    判定顺序（无魔串：边界用 `FSMState`，结果用 `ActionDetectionVerdict`）：

    #. 起止节点（`FSMState` 对应状态名）无期望动作 → ``UNCERTAIN``。
    #. ``segment.confidence < conf_low`` → ``UNCERTAIN``（类别不可信）。
    #. ``segment.action_class`` 与 ``current_node.action_type`` 不一致 → ``MISMATCH``。
    #. 类型一致但 ``confidence < conf_high`` → ``UNCERTAIN``（类型对但置信未达强匹配）。
    #. 否则 → ``MATCH``。
    """

    def __init__(
        self,
        *,
        conf_low: float | None = None,
        conf_high: float | None = None,
    ) -> None:
        low = float(CONF_LOW) if conf_low is None else float(conf_low)
        high = float(CONF_HIGH) if conf_high is None else float(conf_high)
        if low >= high:
            raise ValueError(
                f"conf_low ({low}) 必须严格小于 conf_high ({high})，与域配置一致。"
            )
        self._conf_low = low
        self._conf_high = high

    @property
    def conf_low(self) -> float:
        return self._conf_low

    @property
    def conf_high(self) -> float:
        return self._conf_high

    def detect(self, segment: ActionSegment, current_node: FSMNode) -> ActionDetectionVerdict:
        if current_node.node_id in (
            FSMState.BEFORE_START.value,
            FSMState.DONE.value,
        ):
            return ActionDetectionVerdict.UNCERTAIN

        expected = current_node.action_type
        if expected is None or not expected.strip():
            return ActionDetectionVerdict.UNCERTAIN

        if segment.confidence < self._conf_low:
            return ActionDetectionVerdict.UNCERTAIN

        if segment.action_class != expected:
            return ActionDetectionVerdict.MISMATCH

        if segment.confidence < self._conf_high:
            return ActionDetectionVerdict.UNCERTAIN

        return ActionDetectionVerdict.MATCH
