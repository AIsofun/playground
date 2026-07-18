"""Qwen2.5-VL（vLLM OpenAI 兼容）多模态标注；Prompt 来自配置路径；失败降级。"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any

from src.config.vlm import get_vlm_settings
from src.types.sop import ActionSegment, AnnotatedStep

from .fallbacks import FALLBACK_ACTION_OBJECT, FALLBACK_STEP_DESCRIPTION

logger = logging.getLogger(__name__)

_CONCURRENCY_LIMIT = 5
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.5

__all__ = ["ActionSegment", "AnnotatedStep", "VLMAnnotator", "MockVLMAnnotator"]

# 单测与降级断言使用（非公开 API）
_FALLBACK_STEP_DESCRIPTION = FALLBACK_STEP_DESCRIPTION
_FALLBACK_ACTION_OBJECT = FALLBACK_ACTION_OBJECT


class VLMAnnotator:
    """并发上限 ``_CONCURRENCY_LIMIT``；模板懒加载缓存。"""

    def __init__(
        self,
        vlm_base_url: str | None = None,
        vlm_model: str | None = None,
        timeout_sec: int | None = None,
        max_tokens: int | None = None,
        prompt_path: Path | str | None = None,
    ) -> None:
        s = get_vlm_settings()
        self._vlm_base_url = (vlm_base_url if vlm_base_url is not None else s.VLM_BASE_URL).rstrip("/")
        self._vlm_model = vlm_model if vlm_model is not None else s.VLM_MODEL_NAME
        self._timeout_sec = timeout_sec if timeout_sec is not None else s.VLM_TIMEOUT_SEC
        self._max_tokens = max_tokens if max_tokens is not None else s.VLM_MAX_TOKENS
        self._prompt_rel = s.SOP_GENERATION_PROMPT_PATH
        self._semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)
        self._resolved_prompt_path = (
            Path(prompt_path).resolve()
            if prompt_path is not None
            else Path(__file__).resolve().parents[3] / s.SOP_GENERATION_PROMPT_PATH
        )
        self._prompt_template: str | None = None

    async def annotate(
        self,
        segments: list[ActionSegment],
        keyframes: dict[int, bytes],
        product_context: str = "",
    ) -> list[AnnotatedStep]:
        if not segments:
            return []
        template = self._load_prompt_template()
        tasks = [
            self._annotate_single(
                segment=seg,
                keyframe_bytes=keyframes.get(seg.segment_id, b""),
                product_context=product_context,
                template=template,
            )
            for seg in segments
        ]
        results: list[AnnotatedStep] = list(await asyncio.gather(*tasks))
        return sorted(results, key=lambda s: s.segment_id)

    def _load_prompt_template(self) -> str:
        if self._prompt_template is not None:
            return self._prompt_template
        path = self._resolved_prompt_path
        if not path.exists():
            raise FileNotFoundError(
                f"VLM Prompt 模板不存在：{path}（期望项目根下 {self._prompt_rel!r}）",
            )
        self._prompt_template = path.read_text(encoding="utf-8")
        logger.debug("已加载 VLM Prompt：%s（%d 字符）", path, len(self._prompt_template))
        return self._prompt_template

    async def _annotate_single(
        self,
        segment: ActionSegment,
        keyframe_bytes: bytes,
        product_context: str,
        template: str,
    ) -> AnnotatedStep:
        async with self._semaphore:
            prompt_text = template.format(
                product_context=product_context or "（未指定）",
                action_class=segment.action_class,
            )
            raw_response = await self._call_vlm(prompt_text, keyframe_bytes)
            return self._parse_vlm_response(raw_response, segment.segment_id)

    async def _call_vlm(self, prompt_text: str, image_bytes: bytes) -> str:
        import httpx

        if image_bytes:
            b64_image = base64.b64encode(image_bytes).decode("ascii")
            user_content: list[dict[str, Any]] = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                },
                {"type": "text", "text": prompt_text},
            ]
        else:
            logger.warning("segment 无关键帧，纯文本调用 VLM")
            user_content = [{"type": "text", "text": prompt_text}]

        payload: dict[str, Any] = {
            "model": self._vlm_model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": self._max_tokens,
            "temperature": 0.1,
        }

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=float(self._timeout_sec)) as client:
                    response = await client.post(
                        f"{self._vlm_base_url}/chat/completions",
                        json=payload,
                    )
                    response.raise_for_status()
                    data: dict[str, Any] = response.json()
                    return str(data["choices"][0]["message"]["content"])
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        "VLM 调用失败 (attempt %d/%d)，%.1fs 后重试：%s",
                        attempt, _MAX_RETRIES, wait, exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.warning(
                        "VLM 调用失败 (attempt %d/%d)，使用降级占位：%s",
                        attempt, _MAX_RETRIES, exc,
                    )
        return ""

    def _parse_vlm_response(self, raw_response: str, segment_id: int) -> AnnotatedStep:
        fallback = AnnotatedStep(
            segment_id=segment_id,
            step_description=FALLBACK_STEP_DESCRIPTION,
            action_object=FALLBACK_ACTION_OBJECT,
            warnings=[],
            raw_vlm_response=raw_response,
        )
        if not raw_response.strip():
            logger.warning("segment_id=%d：VLM 空响应", segment_id)
            return fallback

        json_text = self._extract_json_block(raw_response)
        if not json_text:
            logger.warning("segment_id=%d：无 JSON 块，原文前 200 字：%s", segment_id, raw_response[:200])
            return fallback

        try:
            data: dict[str, Any] = json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning("segment_id=%d：JSON 失败 %s", segment_id, exc)
            return fallback

        step_description = str(data.get("step_description") or "").strip()
        action_object = str(data.get("action_object") or "").strip()
        raw_warnings = data.get("warnings", [])
        if not isinstance(raw_warnings, list):
            logger.warning("segment_id=%d：warnings 类型 %s，置 []", segment_id, type(raw_warnings).__name__)
            raw_warnings = []
        warnings = [str(w).strip() for w in raw_warnings if str(w).strip()]

        if not step_description:
            step_description = FALLBACK_STEP_DESCRIPTION
        if not action_object:
            action_object = FALLBACK_ACTION_OBJECT

        return AnnotatedStep(
            segment_id=segment_id,
            step_description=step_description,
            action_object=action_object,
            warnings=warnings,
            raw_vlm_response=raw_response,
        )

    @staticmethod
    def _extract_json_block(text: str) -> str:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return ""
        return text[start : end + 1]


class MockVLMAnnotator(VLMAnnotator):
    """不访问网络；可 ``inject_responses``；默认 JSON 由 ``action_class`` 生成。"""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)
        self._injected: dict[int, str] = {}

    def inject_responses(self, responses: dict[int, str]) -> None:
        self._injected = dict(responses)

    async def annotate(
        self,
        segments: list[ActionSegment],
        keyframes: dict[int, bytes],
        product_context: str = "",
    ) -> list[AnnotatedStep]:
        if not segments:
            return []
        tasks = [self._mock_annotate_single(seg) for seg in segments]
        results = list(await asyncio.gather(*tasks))
        return sorted(results, key=lambda s: s.segment_id)

    async def _mock_annotate_single(self, segment: ActionSegment) -> AnnotatedStep:
        async with self._semaphore:
            raw = self._injected.get(
                segment.segment_id,
                json.dumps(
                    {
                        "step_description": f"执行 {segment.action_class} 操作",
                        "action_object": "目标零件",
                        "warnings": [],
                    },
                    ensure_ascii=False,
                ),
            )
            return self._parse_vlm_response(raw, segment.segment_id)
