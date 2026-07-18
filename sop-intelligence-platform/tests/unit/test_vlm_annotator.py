"""T04 · VLMAnnotator / MockVLMAnnotator 单元测试。

验证：
  - 导出类型与 src.types.sop 中 T01 定义的 ActionSegment / AnnotatedStep 一致
  - 并发 Semaphore(5)、Prompt 文件加载、JSON 解析降级行为
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.services.sop_engine import vlm_annotator as vlm_mod
from src.services.sop_engine.vlm_annotator import (
    MockVLMAnnotator,
    VLMAnnotator,
    _CONCURRENCY_LIMIT,
    _FALLBACK_ACTION_OBJECT,
    _FALLBACK_STEP_DESCRIPTION,
)
from src.types.sop import ActionSegment, AnnotatedStep


def _segment(segment_id: int, action_class: str = "tighten_bolt") -> ActionSegment:
    return ActionSegment(
        segment_id=segment_id,
        start_frame=0,
        end_frame=16,
        start_time_sec=0.0,
        end_time_sec=0.53,
        action_class=action_class,
        confidence=0.92,
        keyframe_index=8,
    )


class TestExportedTypesMatchT01:
    """vlm_annotator 再导出类型须与 src.types.sop 为同一类对象。"""

    def test_action_segment_is_types_sop_class(self) -> None:
        assert vlm_mod.ActionSegment is ActionSegment

    def test_annotated_step_is_types_sop_class(self) -> None:
        assert vlm_mod.AnnotatedStep is AnnotatedStep

    def test_annotated_step_field_contract(self) -> None:
        """与 T01 / sop.py 中 AnnotatedStep 字段一致（构造成功即通过校验）。"""
        step = AnnotatedStep(
            segment_id=1,
            step_description="描述",
            action_object="螺栓",
            warnings=["注意"],
            raw_vlm_response='{"step_description":"描述"}',
        )
        assert step.segment_id == 1
        assert step.warnings == ["注意"]
        assert isinstance(step.raw_vlm_response, str)


class TestConcurrencyAndExports:
    def test_semaphore_limit_is_five(self) -> None:
        real = VLMAnnotator()
        mock = MockVLMAnnotator()
        assert real._semaphore._value == _CONCURRENCY_LIMIT == 5
        assert mock._semaphore._value == 5

    def test_public_all_exports(self) -> None:
        names = set(vlm_mod.__all__)
        assert names == {"ActionSegment", "AnnotatedStep", "VLMAnnotator", "MockVLMAnnotator"}


class TestMockVLMAnnotator:
    def test_empty_segments_returns_empty_list(self) -> None:
        m = MockVLMAnnotator()
        out = asyncio.run(m.annotate([], {}))
        assert out == []

    def test_default_template_per_segment(self) -> None:
        m = MockVLMAnnotator()
        segs = [_segment(2), _segment(1)]
        out = asyncio.run(m.annotate(segs, {}))
        assert [s.segment_id for s in out] == [1, 2]
        for s in out:
            assert isinstance(s, AnnotatedStep)
            assert s.step_description.startswith("执行 ")
            assert s.action_object == "目标零件"
            assert s.warnings == []

    def test_inject_failure_degrades_without_exception(self) -> None:
        m = MockVLMAnnotator()
        m.inject_responses({1: ""})
        out = asyncio.run(m.annotate([_segment(1)], {}))
        assert len(out) == 1
        assert out[0].step_description == _FALLBACK_STEP_DESCRIPTION
        assert out[0].action_object == _FALLBACK_ACTION_OBJECT
        assert out[0].warnings == []

    def test_inject_valid_json(self) -> None:
        m = MockVLMAnnotator()
        payload = {
            "step_description": "拧紧螺栓",
            "action_object": "M8螺栓",
            "warnings": ["注意扭矩"],
        }
        m.inject_responses({1: json.dumps(payload, ensure_ascii=False)})
        out = asyncio.run(m.annotate([_segment(1)], {}))
        assert out[0].step_description == "拧紧螺栓"
        assert out[0].action_object == "M8螺栓"
        assert out[0].warnings == ["注意扭矩"]

    def test_inject_malformed_json_degrades(self) -> None:
        m = MockVLMAnnotator()
        m.inject_responses({1: "not json {{{"})
        out = asyncio.run(m.annotate([_segment(1)], {}))
        assert out[0].step_description == _FALLBACK_STEP_DESCRIPTION
        assert out[0].action_object == _FALLBACK_ACTION_OBJECT

    def test_empty_action_object_in_json_gets_placeholder(self) -> None:
        m = MockVLMAnnotator()
        m.inject_responses(
            {
                1: json.dumps(
                    {
                        "step_description": "有效描述",
                        "action_object": "",
                        "warnings": [],
                    },
                    ensure_ascii=False,
                )
            }
        )
        out = asyncio.run(m.annotate([_segment(1)], {}))
        assert out[0].step_description == "有效描述"
        assert out[0].action_object == _FALLBACK_ACTION_OBJECT


class TestVLMAnnotatorPromptAndParse:
    def test_load_prompt_template_from_project_file(self) -> None:
        annotator = VLMAnnotator()
        text = annotator._load_prompt_template()
        assert "{product_context}" in text
        assert "{action_class}" in text

    def test_annotate_with_mocked_vlm_call(self, tmp_path: Path) -> None:
        """不发起真实 HTTP：Patch _call_vlm，验证走完整 annotate + 文件加载路径。"""
        prompt = (
            "ctx={product_context}\ncls={action_class}\n"
            '{{"hint":"json in prompt must use doubled braces in file"}}'
        )
        p = tmp_path / "sop-generation.txt"
        p.write_text(prompt, encoding="utf-8")

        annotator = VLMAnnotator(prompt_path=p)
        fake_json = json.dumps(
            {
                "step_description": "步骤",
                "action_object": "零件A",
                "warnings": [],
            },
            ensure_ascii=False,
        )

        async def _run_annot() -> list[AnnotatedStep]:
            with patch.object(annotator, "_call_vlm", new=AsyncMock(return_value=fake_json)):
                return await annotator.annotate([_segment(1)], {1: b"\xff\xd8\xff"}, "PROD-1")

        out = asyncio.run(_run_annot())
        assert len(out) == 1
        assert out[0].step_description == "步骤"
        assert out[0].action_object == "零件A"
