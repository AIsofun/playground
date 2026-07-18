"""``grpc_server`` 内存通道冒烟：metadata + jpeg 分片 → handler 收到 ``UncertainFrameUpload``。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import grpc
import pytest
from grpc import aio

from src.adapters.edge.grpc_server import create_uncertain_frame_upload_aio_server
from src.adapters.edge.proto_gen import frame_upload_pb2
from src.adapters.edge.proto_gen.frame_upload_pb2_grpc import FrameUploadServiceStub
from src.types.frames import ConfidenceLevel, UncertainFrameUpload


def test_upload_uncertain_frame_grpc_smoke() -> None:
    async def _run() -> None:
        received: list[UncertainFrameUpload] = []

        async def handler(u: UncertainFrameUpload) -> None:
            received.append(u)

        server = create_uncertain_frame_upload_aio_server(handler)
        port = server.add_insecure_port("127.0.0.1:0")
        assert port > 0
        await server.start()
        try:
            async with aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = FrameUploadServiceStub(channel)

                async def _chunks():
                    md = frame_upload_pb2.UncertainFrameMetadata(
                        workstation_id="ws-1",
                        sop_id="sop-a",
                        sop_step=3,
                        captured_at="2026-04-14T12:00:00+00:00",
                        edge_confidence=0.55,
                        edge_level=frame_upload_pb2.UNCERTAIN,
                        fsm_state="SOLDER_CHECK",
                    )
                    c0 = frame_upload_pb2.FrameUploadChunk()
                    c0.metadata.CopyFrom(md)
                    yield c0
                    c1 = frame_upload_pb2.FrameUploadChunk()
                    c1.jpeg_chunk = b"\xff\xd8\xff"
                    yield c1
                    c2 = frame_upload_pb2.FrameUploadChunk()
                    c2.jpeg_chunk = b"\xd9"
                    yield c2

                ack = await stub.UploadUncertainFrame(_chunks())
                assert ack.accepted is True

        finally:
            await server.stop(1.0)

        assert len(received) == 1
        u = received[0]
        assert u.workstation_id == "ws-1"
        assert u.sop_id == "sop-a"
        assert u.sop_step == 3
        assert u.edge_confidence == pytest.approx(0.55)
        assert u.edge_level is ConfidenceLevel.UNCERTAIN
        assert u.frame_jpeg == b"\xff\xd8\xff\xd9"
        assert u.fsm_state == "SOLDER_CHECK"
        assert u.captured_at == datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc)

    asyncio.run(_run())


def test_upload_rejects_chunk_before_metadata() -> None:
    async def _run() -> None:
        async def _noop(_u: UncertainFrameUpload) -> None:
            return None

        server = create_uncertain_frame_upload_aio_server(_noop)
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        try:
            async with aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = FrameUploadServiceStub(channel)

                async def _bad():
                    c = frame_upload_pb2.FrameUploadChunk()
                    c.jpeg_chunk = b"x"
                    yield c

                with pytest.raises(grpc.aio.AioRpcError) as ei:
                    await stub.UploadUncertainFrame(_bad())
                assert ei.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        finally:
            await server.stop(1.0)

    asyncio.run(_run())
