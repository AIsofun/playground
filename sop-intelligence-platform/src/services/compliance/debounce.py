"""合规告警去抖动（Debounce）— 避免短时重复触发同一类型告警。

策略：同一工位 + 同一告警类型在 window_sec 内仅触发一次。
不使用 Redis，仅内存字典（单进程部署足够）。

用法示例::

    debouncer = ComplianceDebouncer(window_sec=10.0)
    if debouncer.should_fire("ws-01", "HESITATION_WARNING"):
        # 发送告警
        ...
"""

from __future__ import annotations

import time
from collections import defaultdict


class ComplianceDebouncer:
    """内存级合规告警去抖动器。

    Args:
        window_sec: 同一 (workstation_id, alert_type) 在此窗口内仅触发一次。
    """

    def __init__(self, window_sec: float = 10.0) -> None:
        if window_sec <= 0:
            raise ValueError(f"window_sec must be positive, got {window_sec}")
        self._window_sec = window_sec
        self._last_fire: dict[tuple[str, str], float] = defaultdict(float)

    def should_fire(self, workstation_id: str, alert_type: str) -> bool:
        """判断是否应触发告警。若在窗口内已触发则返回 False。"""
        key = (workstation_id, alert_type)
        now = time.monotonic()
        last = self._last_fire[key]
        if now - last < self._window_sec:
            return False
        self._last_fire[key] = now
        return True

    def reset(self, workstation_id: str | None = None) -> None:
        """重置去抖动状态。不传参则重置所有。"""
        if workstation_id is None:
            self._last_fire.clear()
        else:
            keys_to_remove = [k for k in self._last_fire if k[0] == workstation_id]
            for k in keys_to_remove:
                del self._last_fire[k]
