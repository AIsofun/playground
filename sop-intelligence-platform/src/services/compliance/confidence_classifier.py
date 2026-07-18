"""将连续置信度分数映射为合规三档（服务层）。

阈值一律来自 ``src/config/vlm.py``（构造时可注入覆盖，供单测与 Harness），
禁止在本模块对分档边界使用硬编码浮点字面量（须用 ``CONF_LOW``/``CONF_HIGH`` 或注入值）。

分档语义见 ``docs/domain-logic.md``：
    VIOLATION:   score < CONF_LOW
    UNCERTAIN:   CONF_LOW <= score < CONF_HIGH
    COMPLIANT:   score >= CONF_HIGH
"""

from __future__ import annotations

from src.config.vlm import CONF_HIGH, CONF_LOW
from src.types.frames import ConfidenceLevel

__all__ = ["ConfidenceClassifier"]


class ConfidenceClassifier:
    """把边缘标量置信度 :math:`s \\in [0,1]` 映射为 ``ConfidenceLevel``。"""

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
                f"conf_low ({low}) 必须严格小于 conf_high ({high})，与 src/config/vlm.py 域不变量一致。"
            )
        self._conf_low = low
        self._conf_high = high

    @property
    def conf_low(self) -> float:
        return self._conf_low

    @property
    def conf_high(self) -> float:
        return self._conf_high

    def classify(self, score: float) -> ConfidenceLevel:
        """返回 ``COMPLIANT`` / ``UNCERTAIN`` / ``VIOLATION``。"""
        s = float(score)
        if not 0.0 <= s <= 1.0:
            raise ValueError(f"score 必须在 [0.0, 1.0] 内，收到 {s!r}")

        if s < self._conf_low:
            return ConfidenceLevel.VIOLATION
        if s < self._conf_high:
            return ConfidenceLevel.UNCERTAIN
        return ConfidenceLevel.COMPLIANT
