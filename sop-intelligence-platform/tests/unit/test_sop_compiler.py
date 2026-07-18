"""
T05 · SOPCompiler 单元测试（TDD 2.0）

验证：
  - AnnotatedStep → SOPStep 映射（step_id 从 1 递增，与 segment 顺序一致）
  - Pydantic 全量校验与 SOPDocument 往返 model_validate
  - warnings=None 等防御性修正 + 日志
  - 非法 / 不完整标注数据（类 VLM 解析失败）降级为占位值，不中断编译
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.services.sop_engine.sop_compiler import (
    SOPCompilationError,
    SOPCompiler,
)
from src.types.sop import ActionSegment, AnnotatedStep, SOPDocument, SOPStep


def _segment(
    segment_id: int,
    *,
    action_class: str = "pick_up_bolt",
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
        step_description=f"步骤{segment_id}描述",
        action_object=f"对象{segment_id}",
        warnings=[],
        raw_vlm_response="{}",
    )
    base.update(kwargs)
    return AnnotatedStep.model_validate(base)


@pytest.fixture
def compiler() -> SOPCompiler:
    return SOPCompiler()


class TestCompileHappyPath:
    """DoD：3 个 AnnotatedStep → total_steps==3 且 step_id 从 1 编号。"""

    def test_three_steps_mapping_and_total(
        self, compiler: SOPCompiler
    ) -> None:
        segments = [
            _segment(1, start_t=0.0, end_t=0.5),
            _segment(2, start_t=1.0, end_t=1.5),
            _segment(3, start_t=2.0, end_t=2.5),
        ]
        ann = [
            _annotated(1, step_description="拿扳手", action_object="扳手"),
            _annotated(2, step_description="拧紧", action_object="螺栓"),
            _annotated(3, step_description="检查", action_object="工件"),
        ]
        paths = {
            1: "minio://sop-keyframes/job/step_1.jpg",
            2: "minio://sop-keyframes/job/step_2.jpg",
            3: "minio://sop-keyframes/job/step_3.jpg",
        }
        doc = compiler.compile(
            product_id="PROD-001",
            annotated_steps=ann,
            segments=segments,
            keyframe_paths=paths,
            source_video_paths=["minio://sop-videos/PROD-001/demo.mp4"],
            version="v1.0",
        )
        assert doc.total_steps == 3
        assert len(doc.steps) == 3
        assert doc.steps[0].step_id == 1
        assert doc.steps[1].step_id == 2
        assert doc.steps[2].step_id == 3
        assert doc.steps[0].description == "拿扳手"
        assert doc.steps[0].action_object == "扳手"
        assert doc.steps[0].keyframe_path == paths[1]
        assert doc.steps[0].video_timestamp == 0.0
        assert doc.steps[0].action_type == "pick_up_bolt"
        assert doc.product_id == "PROD-001"
        assert doc.version == "PROD-001-v1.0"
        assert doc.status == "draft"
        uuid.UUID(doc.sop_id)  # valid UUID


class TestPydanticRoundTrip:
    """输出的 SOPDocument 可通过 model_dump → model_validate 全量再校验。"""

    def test_model_validate_roundtrip(self, compiler: SOPCompiler) -> None:
        segments = [_segment(1)]
        ann = [_annotated(1)]
        paths = {1: "minio://b/k.jpg"}
        doc = compiler.compile(
            product_id="P",
            annotated_steps=ann,
            segments=segments,
            keyframe_paths=paths,
            source_video_paths=["minio://sop-videos/P/a.mp4"],
        )
        again = SOPDocument.model_validate(doc.model_dump(mode="json"))
        assert again.model_dump(mode="json") == doc.model_dump(mode="json")


class TestWarningsNormalization:
    """AnnotatedStep.warnings 为 None 时修正为 [] 并打警告日志。"""

    def test_warnings_none_normalized_and_logged(
        self, compiler: SOPCompiler, caplog: pytest.LogCaptureFixture
    ) -> None:
        raw = AnnotatedStep.model_construct(
            segment_id=1,
            step_description="有效描述",
            action_object="对象",
            warnings=None,
            raw_vlm_response="not-json{{{",
        )
        caplog.set_level(logging.WARNING)
        doc = compiler.compile(
            product_id="P",
            annotated_steps=[raw],
            segments=[_segment(1)],
            keyframe_paths={1: "minio://b/x.jpg"},
            source_video_paths=["minio://sop-videos/P/v.mp4"],
        )
        assert doc.steps[0].warnings == []
        assert any("warnings" in r.message.lower() for r in caplog.records)


class TestDefensiveDegradation:
    """模拟未经验证的残缺对象（类似 VLM 非法 JSON 后的未校验实例）：降级为占位值。"""

    def test_invalid_constructed_step_degrades_like_vlm_fallback(
        self, compiler: SOPCompiler, caplog: pytest.LogCaptureFixture
    ) -> None:
        bad = AnnotatedStep.model_construct(
            segment_id=7,
            step_description="",
            action_object="",
            warnings=None,
            raw_vlm_response="<<<invalid-json>>>",
        )
        caplog.set_level(logging.WARNING)
        doc = compiler.compile(
            product_id="P",
            annotated_steps=[bad],
            segments=[_segment(7)],
            keyframe_paths={7: "minio://b/s7.jpg"},
            source_video_paths=["minio://sop-videos/P/v.mp4"],
        )
        assert doc.steps[0].step_id == 1
        assert doc.steps[0].description == "[待人工补充]"
        assert doc.steps[0].action_object == "（未知）"
        assert doc.steps[0].warnings == []


class TestCompilationErrors:
    def test_empty_annotated_steps_raises(self, compiler: SOPCompiler) -> None:
        with pytest.raises(SOPCompilationError) as ei:
            compiler.compile(
                product_id="P",
                annotated_steps=[],
                segments=[],
                keyframe_paths={},
                source_video_paths=["minio://sop-videos/P/v.mp4"],
            )
        assert ei.value.details

    def test_missing_keyframe_path_raises(self, compiler: SOPCompiler) -> None:
        with pytest.raises(SOPCompilationError):
            compiler.compile(
                product_id="P",
                annotated_steps=[_annotated(1)],
                segments=[_segment(1)],
                keyframe_paths={},
                source_video_paths=["minio://sop-videos/P/v.mp4"],
            )

    def test_segment_id_mismatch_raises(self, compiler: SOPCompiler) -> None:
        with pytest.raises(SOPCompilationError):
            compiler.compile(
                product_id="P",
                annotated_steps=[_annotated(1)],
                segments=[_segment(2)],
                keyframe_paths={1: "minio://b/a.jpg"},
                source_video_paths=["minio://sop-videos/P/v.mp4"],
            )


class TestFullValidationStrict:
    """最终 SOPDocument 必须通过严格 Pydantic 构造（失败则 SOPCompilationError）。"""

    def test_total_steps_mismatch_would_fail_pydantic(self) -> None:
        with pytest.raises(ValidationError):
            SOPDocument(
                sop_id=str(uuid.uuid4()),
                product_id="P",
                version="P-v1",
                steps=[
                    SOPStep(
                        step_id=1,
                        description="d",
                        action_object="o",
                        keyframe_path="minio://b/x.jpg",
                        video_timestamp=0.0,
                        action_type="t",
                        warnings=[],
                    )
                ],
                total_steps=99,
                created_at=datetime.now(timezone.utc),
                source_video_paths=["minio://sop-videos/P/v.mp4"],
            )
