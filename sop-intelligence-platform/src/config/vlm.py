"""Configuration constants for VLM inference and VideoMAE parameters.

Layer 2 (config/) — only imports from stdlib, pydantic-settings, and src/types/.
Forbidden: src/services/, src/adapters/, src/api/.

All constants are readable directly:
    from src.config.vlm import VLM_BASE_URL, CONF_LOW

All constants can be overridden via environment variables or a .env file at
the project root. Example:
    VLM_BASE_URL=http://gpu-server:9000/v1 python -m pytest

Compliance thresholds (CONF_LOW / CONF_HIGH) are domain-critical values
documented in docs/domain-logic.md. Changing them requires re-running
tests/harness/compliance_eval/run_eval.py and syncing docs/domain-logic.md.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VLMSettings(BaseSettings):
    """Pydantic-settings model for VLM and VideoMAE configuration.

    Fields are populated in priority order:
    1. Direct constructor arguments (e.g. in tests)
    2. Environment variables (same name, case-insensitive)
    3. `.env` file at the project root
    4. Default values defined below
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Ignore extra env vars that don't belong to this settings class.
        extra="ignore",
        # Keep field names case-sensitive for env var matching.
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # VLM HTTP API (vLLM OpenAI-compatible endpoint)
    # ------------------------------------------------------------------

    VLM_BASE_URL: str = "http://localhost:8000/v1"
    """Base URL for the vLLM server (OpenAI-compatible REST API)."""

    VLM_MODEL_NAME: str = "Qwen2.5-VL-7B-Instruct"
    """Model identifier passed in every chat-completion request."""

    VLM_TIMEOUT_SEC: int = 30
    """HTTP request timeout in seconds for VLM API calls."""

    VLM_MAX_TOKENS: int = 1024
    """Maximum tokens to generate per VLM response."""

    # ------------------------------------------------------------------
    # VideoMAE inference parameters
    # ------------------------------------------------------------------

    VIDEOMAE_WINDOW_FRAMES: int = 16
    """Number of frames fed to VideoMAE in a single inference pass."""

    VIDEOMAE_STRIDE_FRAMES: int = 8
    """Sliding-window stride (frames) between consecutive inference passes."""

    VIDEOMAE_MIN_CONFIDENCE: float = 0.5
    """Segments with confidence below this threshold are merged into the
    preceding action (not emitted as independent ActionSegment entries)."""

    # ------------------------------------------------------------------
    # Prompt template
    # ------------------------------------------------------------------

    SOP_GENERATION_PROMPT_PATH: str = ".ai/prompts/sop-generation.txt"
    """Path (relative to project root) of the SOP-generation prompt template.
    Modify the file directly; no code change required."""

    VLM_ANOMALY_CHECK_PROMPT_PATH: str = ".ai/prompts/vlm-anomaly-check.txt"
    """Path (relative to project root) of the compliance / anomaly VLM prompt.
    See docs/module-specs/compliance-service.md §3."""

    # ------------------------------------------------------------------
    # Compliance confidence thresholds  ⚠️  domain-critical
    # Documented in: docs/domain-logic.md
    # After changing: re-run tests/harness/compliance_eval/run_eval.py
    # ------------------------------------------------------------------

    CONF_LOW: float = 0.4
    """Lower bound of the **UNCERTAIN** band (see docs/domain-logic.md).

    Scores in ``[CONF_LOW, CONF_HIGH)`` → UNCERTAIN (gRPC frame upload + VLM).
    Scores strictly below ``CONF_LOW`` → VIOLATION (fast-path alert; no VLM wait).
    """

    CONF_HIGH: float = 0.7
    """Lower bound of the **COMPLIANT** band (see docs/domain-logic.md).

    Scores ``>= CONF_HIGH`` → COMPLIANT (no VLM re-evaluation on the happy path).
    """

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator("VIDEOMAE_MIN_CONFIDENCE", "CONF_LOW", "CONF_HIGH")
    @classmethod
    def _must_be_unit_interval(cls, v: float) -> float:
        """Confidence values must lie in the closed interval [0.0, 1.0]."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"Confidence value must be in [0.0, 1.0], got {v!r}."
            )
        return v

    @field_validator("VLM_TIMEOUT_SEC")
    @classmethod
    def _timeout_must_be_positive(cls, v: int) -> int:
        """A zero or negative timeout makes every VLM call fail immediately."""
        if v <= 0:
            raise ValueError(
                f"VLM_TIMEOUT_SEC must be a positive integer, got {v!r}."
            )
        return v

    @model_validator(mode="after")
    def _conf_ordering(self) -> "VLMSettings":
        """Enforce the domain invariant: CONF_LOW < CONF_HIGH.

        This invariant is documented in docs/domain-logic.md.  Violating it
        produces an undefined three-tier classification (UNCERTAIN zone
        collapses), so we fail fast at startup.
        """
        if self.CONF_LOW >= self.CONF_HIGH:
            raise ValueError(
                f"Domain invariant violated: CONF_LOW ({self.CONF_LOW}) must be "
                f"strictly less than CONF_HIGH ({self.CONF_HIGH}).  "
                f"See docs/domain-logic.md for the three-tier classification spec."
            )
        return self


@lru_cache(maxsize=1)
def get_vlm_settings() -> VLMSettings:
    """Return a cached VLMSettings instance (loaded once at first call).

    The cache can be cleared in tests with:
        get_vlm_settings.cache_clear()
    """
    return VLMSettings()


# ---------------------------------------------------------------------------
# Module-level constants — direct import API
# ---------------------------------------------------------------------------
# Bind once at module load time so callers can do:
#     from src.config.vlm import VLM_BASE_URL
# These names are frozen after the first import of this module.  For dynamic
# env-override testing, instantiate VLMSettings() directly or use the
# get_vlm_settings() getter after cache_clear().
# ---------------------------------------------------------------------------

_s = get_vlm_settings()

VLM_BASE_URL: str = _s.VLM_BASE_URL
VLM_MODEL_NAME: str = _s.VLM_MODEL_NAME
VLM_TIMEOUT_SEC: int = _s.VLM_TIMEOUT_SEC
VLM_MAX_TOKENS: int = _s.VLM_MAX_TOKENS

VIDEOMAE_WINDOW_FRAMES: int = _s.VIDEOMAE_WINDOW_FRAMES
VIDEOMAE_STRIDE_FRAMES: int = _s.VIDEOMAE_STRIDE_FRAMES
VIDEOMAE_MIN_CONFIDENCE: float = _s.VIDEOMAE_MIN_CONFIDENCE

SOP_GENERATION_PROMPT_PATH: str = _s.SOP_GENERATION_PROMPT_PATH
VLM_ANOMALY_CHECK_PROMPT_PATH: str = _s.VLM_ANOMALY_CHECK_PROMPT_PATH

CONF_LOW: float = _s.CONF_LOW
CONF_HIGH: float = _s.CONF_HIGH
