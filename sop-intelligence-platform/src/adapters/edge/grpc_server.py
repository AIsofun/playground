"""边缘 UNCERTAIN 帧 gRPC 入站适配器（``frame_upload.proto``）。

职责：反序列化 client-stream，组装 ``UncertainFrameUpload``，调用注入的异步 handler。
不做三档合规等业务判断（见 ``docs/module-specs/compliance-service.md``）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone

import grpc
from grpc import aio

from src.adapters.edge.proto_gen import frame_upload_pb2
from src.adapters.edge.proto_gen.frame_upload_pb2_grpc import (
    FrameUploadServiceServicer,
    add_FrameUploadServiceServicer_to_server,
)
from src.config.edge import GRPC_UNCERTAIN_FRAME_MAX_BYTES
from src.types.frames import ConfidenceLevel, UncertainFrameUpload

_LOG = logging.getLogger(__name__)

UncertainFrameHandler = Callable[[UncertainFrameUpload], Awaitable[None]]


def _parse_captured_at(raw: str) -> datetime:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _proto_edge_level_to_domain(level: int) -> ConfidenceLevel:
    if level == frame_upload_pb2.UNCERTAIN:
        return ConfidenceLevel.UNCERTAIN
    if level == frame_upload_pb2.COMPLIANT:
        return ConfidenceLevel.COMPLIANT
    if level == frame_upload_pb2.VIOLATION:
        return ConfidenceLevel.VIOLATION
    raise ValueError(f"edge_level 无法映射：{level}")


def _metadata_to_model(
    meta: frame_upload_pb2.UncertainFrameMetadata,
    frame_jpeg: bytes,
) -> UncertainFrameUpload:
    fsm_state: str | None = None
    if meta.HasField("fsm_state"):
        fsm_state = meta.fsm_state or None
    return UncertainFrameUpload(
        workstation_id=meta.workstation_id,
        sop_id=meta.sop_id,
        sop_step=int(meta.sop_step),
        captured_at=_parse_captured_at(meta.captured_at),
        edge_confidence=float(meta.edge_confidence),
        edge_level=_proto_edge_level_to_domain(int(meta.edge_level)),
        frame_jpeg=frame_jpeg,
        fsm_state=fsm_state,
    )


class _FrameUploadServicer(FrameUploadServiceServicer):
    def __init__(self, handler: UncertainFrameHandler) -> None:
        self._handler = handler

    async def UploadUncertainFrame(
        self,
        request_iterator: AsyncIterator[frame_upload_pb2.FrameUploadChunk],
        context: grpc.ServicerContext,
    ) -> frame_upload_pb2.UploadAck:
        meta: frame_upload_pb2.UncertainFrameMetadata | None = None
        buf = bytearray()
        seen_chunk = False

        async for req in request_iterator:
            which = req.WhichOneof("part")
            if which == "metadata":
                if meta is not None:
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "duplicate metadata",
                    )
                if seen_chunk:
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "metadata must precede jpeg_chunk",
                    )
                meta = req.metadata
            elif which == "jpeg_chunk":
                seen_chunk = True
                if meta is None:
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "metadata required before jpeg_chunk",
                    )
                chunk = req.jpeg_chunk
                if chunk:
                    if len(buf) + len(chunk) > GRPC_UNCERTAIN_FRAME_MAX_BYTES:
                        await context.abort(
                            grpc.StatusCode.RESOURCE_EXHAUSTED,
                            f"jpeg exceeds {GRPC_UNCERTAIN_FRAME_MAX_BYTES} bytes",
                        )
                    buf.extend(chunk)
            else:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "empty FrameUploadChunk",
                )

        if meta is None:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "missing metadata",
            )

        try:
            upload = _metadata_to_model(meta, bytes(buf))
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        try:
            await self._handler(upload)
        except Exception:
            _LOG.exception("UncertainFrameUpload handler failed")
            await context.abort(grpc.StatusCode.INTERNAL, "handler failed")

        return frame_upload_pb2.UploadAck(accepted=True, message="ok")


def create_uncertain_frame_upload_aio_server(
    handler: UncertainFrameHandler,
    *,
    max_receive_message_length: int | None = None,
    options: tuple[tuple[str, str | int], ...] | None = None,
) -> aio.Server:
    """构建 ``grpc.aio`` Server，已注册 ``FrameUploadService``。

    调用方负责 ``add_insecure_port`` / ``add_secure_port``、``start``、``stop``。
    """
    _max = max_receive_message_length or (GRPC_UNCERTAIN_FRAME_MAX_BYTES + 65_536)
    base_opts: tuple[tuple[str, str | int], ...] = (
        ("grpc.max_receive_message_length", _max),
    )
    merged = base_opts + (options or ())
    server = aio.server(options=merged)
    add_FrameUploadServiceServicer_to_server(_FrameUploadServicer(handler), server)
    return server
