"""
T07 · VersionManager 单元测试（TDD 2.0 — 换型 / 增量版本）

验证：
  - save：并发上传关键帧、路径规范化、写入 PostgreSQL 快照
  - diff_update：仅替换 action_type 匹配的步骤，minor +1，未变更步骤 keyframe_path 不变
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.sop_engine.version_manager import (
    VersionManager,
    VersionManagerError,
)
from src.types.sop import ActionSegment, AnnotatedStep, SOPDocument, SOPStep

# 与 video_parser.Mock 一致的最小 JPEG 占位
_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
)


def _segment(
    segment_id: int,
    action_class: str,
    *,
    start_t: float = 0.0,
    end_t: float = 1.0,
) -> ActionSegment:
    return ActionSegment(
        segment_id=segment_id,
        start_frame=segment_id * 10,
        end_frame=segment_id * 10 + 16,
        start_time_sec=start_t,
        end_time_sec=end_t,
        action_class=action_class,
        confidence=0.9,
        keyframe_index=segment_id * 10 + 8,
    )


def _annotated(segment_id: int, **kwargs: object) -> AnnotatedStep:
    base = dict(
        segment_id=segment_id,
        step_description=f"步骤{segment_id}",
        action_object=f"对象{segment_id}",
        warnings=[],
        raw_vlm_response="{}",
    )
    base.update(kwargs)
    return AnnotatedStep.model_validate(base)


def _five_step_doc_v10(*, sop_id: str | None = None) -> SOPDocument:
    pid = "PROD-001"
    sid = sop_id or str(uuid.uuid4())
    paths = [
        f"minio://sop-keyframes/{sid}/step_{i}.jpg"
        for i in range(1, 6)
    ]
    steps = []
    for i in range(5):
        steps.append(
            SOPStep(
                step_id=i + 1,
                description=f"描述{i + 1}",
                action_object=f"零件{i + 1}",
                keyframe_path=paths[i],
                video_timestamp=float(i),
                action_type=f"type_{i + 1}",
                warnings=[],
            )
        )
    return SOPDocument(
        sop_id=sid,
        product_id=pid,
        version=f"{pid}-v1.0",
        steps=steps,
        total_steps=5,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_video_paths=["minio://sop-videos/PROD-001/base.mp4"],
        status="draft",
    )


@pytest.fixture
def mock_minio() -> MagicMock:
    m = MagicMock()
    m.upload_keyframe = AsyncMock(
        side_effect=lambda sop_id, step_id, _: f"sop-keyframes/{sop_id}/step_{step_id}.jpg"
    )
    return m


@pytest.fixture
def mock_pg() -> MagicMock:
    m = MagicMock()
    m.save_sop_version = AsyncMock(side_effect=lambda doc: doc.sop_id)
    m.get_sop_by_id = AsyncMock(return_value=None)
    return m


@pytest.fixture
def vm(mock_minio: MagicMock, mock_pg: MagicMock) -> VersionManager:
    return VersionManager(minio=mock_minio, postgres=mock_pg)


class TestSave:
    """DoD：save 后 keyframe_path 以 sop-keyframes/ 为路径核心（经 minio:// 前缀）。"""

    def test_uploads_and_persists_paths(
        self, vm: VersionManager, mock_minio: MagicMock, mock_pg: MagicMock
    ) -> None:
        sop_id = str(uuid.uuid4())
        doc = _five_step_doc_v10(sop_id=sop_id)
        # 占位路径（保存前可被任意非空字符串）
        for i, st in enumerate(doc.steps, start=1):
            st.keyframe_path = f"pending://local/step_{i}.jpg"

        kb = {i: _MINIMAL_JPEG for i in range(1, 6)}
        out = asyncio.run(vm.save(doc, keyframe_bytes=kb))

        assert mock_minio.upload_keyframe.await_count == 5
        assert mock_pg.save_sop_version.await_count == 1
        for st in out.steps:
            assert st.keyframe_path.startswith("minio://sop-keyframes/")
            assert "/step_" in st.keyframe_path
            assert re.search(r"step_\d+\.jpg$", st.keyframe_path)

    def test_save_requires_bytes_per_step(self, vm: VersionManager) -> None:
        doc = _five_step_doc_v10()
        with pytest.raises(VersionManagerError):
            asyncio.run(vm.save(doc, keyframe_bytes={1: _MINIMAL_JPEG}))


class TestDiffUpdateChangeType:
    """换型：5 步中仅第 3 步变更 → v1.0 → v1.1，其余 keyframe_path 不变。"""

    def test_bumps_minor_and_preserves_other_keyframe_paths(
        self,
        vm: VersionManager,
        mock_minio: MagicMock,
        mock_pg: MagicMock,
    ) -> None:
        base = _five_step_doc_v10()
        mock_pg.get_sop_by_id = AsyncMock(return_value=base)

        # 仅第 3 步（action_type type_3）换型片段
        seg = _segment(99, "type_3", start_t=9.0, end_t=9.5)
        ann = _annotated(
            99,
            step_description="新型号专用扭矩工序",
            action_object="新型号螺栓",
        )
        kb = {99: _MINIMAL_JPEG}

        out = asyncio.run(
            vm.diff_update(
                base.sop_id,
                new_segments=[seg],
                new_annotations=[ann],
                keyframe_bytes_by_segment_id=kb,
            )
        )

        assert out.version == "PROD-001-v1.1"
        assert out.sop_id != base.sop_id
        assert out.total_steps == 5

        for i in (1, 2, 4, 5):
            assert out.steps[i - 1].keyframe_path == base.steps[i - 1].keyframe_path

        assert out.steps[2].description == "新型号专用扭矩工序"
        assert out.steps[2].action_object == "新型号螺栓"
        assert out.steps[2].video_timestamp == 9.0
        assert out.steps[2].action_type == "type_3"
        assert out.steps[2].keyframe_path.startswith("minio://sop-keyframes/")
        assert base.sop_id in out.steps[0].keyframe_path  # 未改步骤仍指向旧快照路径
        assert out.sop_id in out.steps[2].keyframe_path  # 新步骤上传到新 sop_id 下

        mock_pg.save_sop_version.assert_awaited()

    def test_diff_update_missing_base_raises(
        self, vm: VersionManager, mock_pg: MagicMock
    ) -> None:
        mock_pg.get_sop_by_id = AsyncMock(return_value=None)
        with pytest.raises(VersionManagerError):
            asyncio.run(
                vm.diff_update(
                    str(uuid.uuid4()),
                    new_segments=[_segment(1, "type_1")],
                    new_annotations=[_annotated(1)],
                    keyframe_bytes_by_segment_id={1: _MINIMAL_JPEG},
                )
            )
