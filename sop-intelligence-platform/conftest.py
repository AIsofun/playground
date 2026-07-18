"""pytest root conftest — adds the project root to sys.path.

This allows `from src.config.vlm import ...` style imports in all tests
without requiring an installed package.
"""

import sys
from pathlib import Path

import pytest

# Ensure the sop-intelligence-platform/ directory is on sys.path so that
# `from src.xxx import yyy` works in both test files and production modules.
_PROJECT_ROOT = Path(__file__).parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "e2e: SOP 全链路集成测试（需 MinIO + PostgreSQL，见 tests/integration/test_sop_pipeline.py）",
    )
    config.addinivalue_line(
        "markers",
        "integration: 需外部服务的集成测试（COMPLIANCE_E2E=1 / COMPLIANCE_PIPELINE_E2E=1 等，见 tests/integration/README.md）",
    )
