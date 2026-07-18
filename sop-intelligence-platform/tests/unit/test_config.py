"""Unit tests for src/config/vlm.py and src/config/storage.py (T02).

TDD: this file was written before the implementations.
All tests must pass (100% DoD) with no I/O or external dependencies.
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# VLMSettings tests
# ---------------------------------------------------------------------------


class TestVLMSettingsDefaults:
    """Default values load correctly without any env overrides."""

    def _clean_settings(self, monkeypatch: pytest.MonkeyPatch) -> "VLMSettings":
        """Construct VLMSettings with env vars stripped to get pure defaults."""
        from src.config.vlm import VLMSettings
        for key in (
            "VLM_BASE_URL", "VLM_MODEL_NAME", "VLM_TIMEOUT_SEC",
            "VLM_MAX_TOKENS", "CONF_LOW", "CONF_HIGH",
        ):
            monkeypatch.delenv(key, raising=False)
        return VLMSettings(_env_file=None)  # type: ignore[call-arg]

    def test_vlm_base_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VLM_BASE_URL == "http://localhost:8000/v1"

    def test_vlm_model_name_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VLM_MODEL_NAME == "Qwen2.5-VL-7B-Instruct"

    def test_vlm_timeout_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VLM_TIMEOUT_SEC == 30

    def test_vlm_max_tokens_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VLM_MAX_TOKENS == 1024

    def test_videomae_window_frames_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VIDEOMAE_WINDOW_FRAMES == 16

    def test_videomae_stride_frames_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VIDEOMAE_STRIDE_FRAMES == 8

    def test_videomae_min_confidence_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.VIDEOMAE_MIN_CONFIDENCE == 0.5

    def test_sop_prompt_path_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.SOP_GENERATION_PROMPT_PATH == ".ai/prompts/sop-generation.txt"

    def test_conf_low_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.CONF_LOW == pytest.approx(0.4)

    def test_conf_high_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._clean_settings(monkeypatch)
        assert s.CONF_HIGH == pytest.approx(0.7)


class TestVLMSettingsEnvOverride:
    """Environment variables override default values (core T02 DoD)."""

    def test_vlm_base_url_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VLM_BASE_URL", "http://gpu-server:9000/v1")
        s = VLMSettings()
        assert s.VLM_BASE_URL == "http://gpu-server:9000/v1"

    def test_vlm_model_name_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VLM_MODEL_NAME", "Qwen2.5-VL-72B-Instruct")
        assert VLMSettings().VLM_MODEL_NAME == "Qwen2.5-VL-72B-Instruct"

    def test_vlm_timeout_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VLM_TIMEOUT_SEC", "60")
        assert VLMSettings().VLM_TIMEOUT_SEC == 60

    def test_videomae_min_confidence_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VIDEOMAE_MIN_CONFIDENCE", "0.7")
        assert VLMSettings().VIDEOMAE_MIN_CONFIDENCE == pytest.approx(0.7)

    def test_conf_low_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("CONF_LOW", "0.3")
        assert VLMSettings().CONF_LOW == pytest.approx(0.3)

    def test_conf_high_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("CONF_HIGH", "0.8")
        assert VLMSettings().CONF_HIGH == pytest.approx(0.8)

    def test_prompt_path_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("SOP_GENERATION_PROMPT_PATH", "/custom/path/prompt.txt")
        assert VLMSettings().SOP_GENERATION_PROMPT_PATH == "/custom/path/prompt.txt"


class TestVLMSettingsValidation:
    """Field-level constraints are enforced by Pydantic v2."""

    def test_conf_low_out_of_unit_interval_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("CONF_LOW", "1.5")
        with pytest.raises(ValidationError):
            VLMSettings()

    def test_conf_high_out_of_unit_interval_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("CONF_HIGH", "-0.1")
        with pytest.raises(ValidationError):
            VLMSettings()

    def test_videomae_min_confidence_above_one_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VIDEOMAE_MIN_CONFIDENCE", "1.1")
        with pytest.raises(ValidationError):
            VLMSettings()

    def test_conf_low_gte_conf_high_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONF_LOW must be strictly less than CONF_HIGH (domain-logic.md invariant)."""
        from pydantic import ValidationError
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("CONF_LOW", "0.7")
        monkeypatch.setenv("CONF_HIGH", "0.7")
        with pytest.raises(ValidationError):
            VLMSettings()

    def test_vlm_timeout_zero_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VLM_TIMEOUT_SEC", "0")
        with pytest.raises(ValidationError):
            VLMSettings()

    def test_vlm_timeout_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError
        from src.config.vlm import VLMSettings
        monkeypatch.setenv("VLM_TIMEOUT_SEC", "-5")
        with pytest.raises(ValidationError):
            VLMSettings()


class TestVLMModuleLevelImport:
    """Module-level constants are directly importable (T02 DoD smoke test)."""

    def test_vlm_base_url_importable(self) -> None:
        from src.config.vlm import VLM_BASE_URL
        assert isinstance(VLM_BASE_URL, str)
        assert VLM_BASE_URL.startswith("http")

    def test_vlm_model_name_importable(self) -> None:
        from src.config.vlm import VLM_MODEL_NAME
        assert isinstance(VLM_MODEL_NAME, str)

    def test_vlm_timeout_importable(self) -> None:
        from src.config.vlm import VLM_TIMEOUT_SEC
        assert isinstance(VLM_TIMEOUT_SEC, int)
        assert VLM_TIMEOUT_SEC > 0

    def test_conf_low_importable(self) -> None:
        from src.config.vlm import CONF_LOW
        assert isinstance(CONF_LOW, float)
        assert 0.0 < CONF_LOW < 1.0

    def test_conf_high_importable(self) -> None:
        from src.config.vlm import CONF_HIGH
        assert isinstance(CONF_HIGH, float)
        assert 0.0 < CONF_HIGH <= 1.0

    def test_conf_ordering_invariant(self) -> None:
        from src.config.vlm import CONF_LOW, CONF_HIGH
        assert CONF_LOW < CONF_HIGH, "Domain invariant: CONF_LOW must be < CONF_HIGH"

    def test_videomae_params_importable(self) -> None:
        from src.config.vlm import (
            VIDEOMAE_MIN_CONFIDENCE,
            VIDEOMAE_STRIDE_FRAMES,
            VIDEOMAE_WINDOW_FRAMES,
        )
        assert VIDEOMAE_WINDOW_FRAMES > VIDEOMAE_STRIDE_FRAMES, "Window must exceed stride"
        assert 0.0 <= VIDEOMAE_MIN_CONFIDENCE <= 1.0

    def test_prompt_path_importable(self) -> None:
        from src.config.vlm import SOP_GENERATION_PROMPT_PATH
        assert isinstance(SOP_GENERATION_PROMPT_PATH, str)
        assert SOP_GENERATION_PROMPT_PATH.endswith(".txt")


class TestVLMLayerCompliance:
    """src/config/ must not import from services/, adapters/, or api/."""

    def test_no_import_from_services(self) -> None:
        import ast
        import pathlib
        source = pathlib.Path(__file__).parent.parent.parent / "src" / "config" / "vlm.py"
        # utf-8-sig strips the optional BOM that some editors add on Windows
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else ([node.module] if node.module else [])
                )
                for name in names:
                    if name and any(
                        name.startswith(banned)
                        for banned in ("src.services", "src.adapters", "src.api")
                    ):
                        pytest.fail(f"vlm.py imports from forbidden layer: {name}")

    def test_no_import_from_services_storage(self) -> None:
        import ast
        import pathlib
        source = pathlib.Path(__file__).parent.parent.parent / "src" / "config" / "storage.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else ([node.module] if node.module else [])
                )
                for name in names:
                    if name and any(
                        name.startswith(banned)
                        for banned in ("src.services", "src.adapters", "src.api")
                    ):
                        pytest.fail(f"storage.py imports from forbidden layer: {name}")


# ---------------------------------------------------------------------------
# StorageSettings tests
# ---------------------------------------------------------------------------


class TestStorageSettingsDefaults:
    """StorageSettings default values (T02 spec + layering.md constants)."""

    def test_minio_bucket_sop_keyframes_default(self) -> None:
        from src.config.storage import get_storage_settings
        get_storage_settings.cache_clear()
        assert get_storage_settings().MINIO_BUCKET_SOP_KEYFRAMES == "sop-keyframes"

    def test_minio_bucket_sop_videos_default(self) -> None:
        from src.config.storage import get_storage_settings
        get_storage_settings.cache_clear()
        assert get_storage_settings().MINIO_BUCKET_SOP_VIDEOS == "sop-videos"

    def test_postgres_table_sop_versions_default(self) -> None:
        from src.config.storage import get_storage_settings
        get_storage_settings.cache_clear()
        assert get_storage_settings().POSTGRES_TABLE_SOP_VERSIONS == "sop_versions"

    def test_minio_bucket_hard_cases_default(self) -> None:
        from src.config.storage import get_storage_settings
        get_storage_settings.cache_clear()
        assert get_storage_settings().MINIO_BUCKET_HARD_CASES == "hard-cases"

    def test_minio_bucket_models_default(self) -> None:
        from src.config.storage import get_storage_settings
        get_storage_settings.cache_clear()
        assert get_storage_settings().MINIO_BUCKET_MODELS == "models"

    def test_data_lake_trigger_threshold_default(self) -> None:
        from src.config.storage import get_storage_settings
        get_storage_settings.cache_clear()
        assert get_storage_settings().DATA_LAKE_TRIGGER_THRESHOLD == 200


class TestStorageSettingsEnvOverride:
    """Environment variables override StorageSettings defaults."""

    def test_minio_bucket_sop_keyframes_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.storage import StorageSettings
        monkeypatch.setenv("MINIO_BUCKET_SOP_KEYFRAMES", "custom-keyframes")
        assert StorageSettings().MINIO_BUCKET_SOP_KEYFRAMES == "custom-keyframes"

    def test_minio_bucket_sop_videos_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.storage import StorageSettings
        monkeypatch.setenv("MINIO_BUCKET_SOP_VIDEOS", "custom-videos")
        assert StorageSettings().MINIO_BUCKET_SOP_VIDEOS == "custom-videos"

    def test_postgres_table_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.storage import StorageSettings
        monkeypatch.setenv("POSTGRES_TABLE_SOP_VERSIONS", "custom_versions")
        assert StorageSettings().POSTGRES_TABLE_SOP_VERSIONS == "custom_versions"

    def test_data_lake_trigger_threshold_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.storage import StorageSettings
        monkeypatch.setenv("DATA_LAKE_TRIGGER_THRESHOLD", "500")
        assert StorageSettings().DATA_LAKE_TRIGGER_THRESHOLD == 500


class TestStorageSettingsValidation:
    """StorageSettings field constraints."""

    def test_data_lake_trigger_threshold_must_be_positive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pydantic import ValidationError
        from src.config.storage import StorageSettings
        monkeypatch.setenv("DATA_LAKE_TRIGGER_THRESHOLD", "0")
        with pytest.raises(ValidationError):
            StorageSettings()

    def test_bucket_name_cannot_be_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError
        from src.config.storage import StorageSettings
        monkeypatch.setenv("MINIO_BUCKET_SOP_KEYFRAMES", "")
        with pytest.raises(ValidationError):
            StorageSettings()


class TestStorageModuleLevelImport:
    """Module-level constants are directly importable."""

    def test_all_constants_importable(self) -> None:
        from src.config.storage import (
            DATA_LAKE_TRIGGER_THRESHOLD,
            MINIO_BUCKET_HARD_CASES,
            MINIO_BUCKET_MODELS,
            MINIO_BUCKET_SOP_KEYFRAMES,
            MINIO_BUCKET_SOP_VIDEOS,
            POSTGRES_TABLE_SOP_VERSIONS,
        )
        assert isinstance(MINIO_BUCKET_SOP_KEYFRAMES, str)
        assert isinstance(MINIO_BUCKET_SOP_VIDEOS, str)
        assert isinstance(POSTGRES_TABLE_SOP_VERSIONS, str)
        assert isinstance(MINIO_BUCKET_HARD_CASES, str)
        assert isinstance(MINIO_BUCKET_MODELS, str)
        assert isinstance(DATA_LAKE_TRIGGER_THRESHOLD, int)
        assert DATA_LAKE_TRIGGER_THRESHOLD > 0

    def test_bucket_names_are_non_empty(self) -> None:
        from src.config.storage import (
            MINIO_BUCKET_HARD_CASES,
            MINIO_BUCKET_MODELS,
            MINIO_BUCKET_SOP_KEYFRAMES,
            MINIO_BUCKET_SOP_VIDEOS,
        )
        for bucket in (
            MINIO_BUCKET_SOP_KEYFRAMES,
            MINIO_BUCKET_SOP_VIDEOS,
            MINIO_BUCKET_HARD_CASES,
            MINIO_BUCKET_MODELS,
        ):
            assert len(bucket) > 0, f"Bucket name must not be empty, got: {bucket!r}"
