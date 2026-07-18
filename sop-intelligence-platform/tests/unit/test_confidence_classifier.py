"""ConfidenceClassifier 分档与边界。"""

from __future__ import annotations

import math

import pytest

from src.config import vlm as vlm_config
from src.config.vlm import CONF_HIGH, CONF_LOW
from src.services.compliance.confidence_classifier import ConfidenceClassifier
from src.types.frames import ConfidenceLevel


@pytest.fixture(autouse=True)
def _restore_vlm_settings_cache() -> None:
    yield
    vlm_config.get_vlm_settings.cache_clear()


def test_init_rejects_inverted_thresholds() -> None:
    with pytest.raises(ValueError, match="必须严格小于"):
        ConfidenceClassifier(conf_low=0.6, conf_high=0.6)
    with pytest.raises(ValueError, match="必须严格小于"):
        ConfidenceClassifier(conf_low=0.8, conf_high=0.2)


def test_classify_rejects_out_of_range() -> None:
    c = ConfidenceClassifier()
    with pytest.raises(ValueError, match="必须在"):
        c.classify(-1e-9)
    with pytest.raises(ValueError, match="必须在"):
        c.classify(1.0 + 1e-9)


def test_default_thresholds_boundaries() -> None:
    """边界与 ``CONF_LOW``/``CONF_HIGH`` 对齐；分档比较中不出现魔数。"""
    c = ConfidenceClassifier()
    low, high = float(CONF_LOW), float(CONF_HIGH)

    just_below_low = math.nextafter(low, -1.0)
    assert c.classify(just_below_low) is ConfidenceLevel.VIOLATION

    assert c.classify(low) is ConfidenceLevel.UNCERTAIN

    mid = (low + high) / 2.0
    assert low < mid < high
    assert c.classify(mid) is ConfidenceLevel.UNCERTAIN

    just_below_high = math.nextafter(high, -1.0)
    assert just_below_high >= low, "测试前提：阈值有序且区间非空"
    assert c.classify(just_below_high) is ConfidenceLevel.UNCERTAIN

    assert c.classify(high) is ConfidenceLevel.COMPLIANT

    just_above_high = math.nextafter(high, 2.0)
    if just_above_high <= 1.0:
        assert c.classify(just_above_high) is ConfidenceLevel.COMPLIANT

    assert c.classify(0.0) is ConfidenceLevel.VIOLATION
    assert c.classify(1.0) is ConfidenceLevel.COMPLIANT


def test_injected_thresholds_narrow_band() -> None:
    """注入阈值便于独立验证比较链，不依赖默认 env。"""
    c = ConfidenceClassifier(conf_low=0.5, conf_high=0.6)
    assert c.conf_low == 0.5
    assert c.conf_high == 0.6

    assert c.classify(0.49) is ConfidenceLevel.VIOLATION
    assert c.classify(0.5) is ConfidenceLevel.UNCERTAIN
    assert c.classify(0.55) is ConfidenceLevel.UNCERTAIN
    assert c.classify(math.nextafter(0.6, -1.0)) is ConfidenceLevel.UNCERTAIN
    assert c.classify(0.6) is ConfidenceLevel.COMPLIANT
    assert c.classify(0.99) is ConfidenceLevel.COMPLIANT
