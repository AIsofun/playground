"""sop_engine 共享字面量：VLM 降级文案与 Mock/抽帧占位 JPEG。"""

from __future__ import annotations

# 与 AnnotatedStep / SOPCompiler 降级语义一致；勿在模块间复制粘贴。
FALLBACK_STEP_DESCRIPTION: str = "[待人工补充]"
FALLBACK_ACTION_OBJECT: str = "（未知）"

# 最小合法 JPEG（SOI + APP0 + EOI），供 MockVideoParser 与测试对齐。
MINIMAL_JPEG_BYTES: bytes = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
)
