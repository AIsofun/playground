# edge_node — Jetson 最小运行时

与 ``edge_node/AGENTS.md`` 一致：本目录**不** import ``src/services`` 或 ``src/adapters``；阈值在 ``fsm_runtime/thresholds.py`` 与 ``src/config/vlm.py`` 手工对齐。

## 功能

- **合规三档**：``fsm_runtime.band.classify_edge_score`` → ``COMPLIANT`` / ``UNCERTAIN`` / ``VIOLATION``（与 ``docs/domain-logic.md`` §2 闭开约定一致）。
- **UNCERTAIN 上送**：``fsm_runtime.upload_worker.UncertainGrpcUploader`` 在**独立线程**内执行 gRPC；主线程仅 ``enqueue``（``put_nowait``），队列满则丢弃并打日志。

## 本地 smoke

```bash
pip install -r edge_node/requirements.txt
# 无网络：仅分档 + 主循环
python edge_node/scripts/smoke_offline_frames.py
# 需已启动服务端 FrameUploadService（见 src/adapters/edge/grpc_server.py）
python edge_node/scripts/smoke_offline_frames.py --grpc --grpc-target 127.0.0.1:50051
```

## Jetson Orin NX 部署注意

1. **Python 与依赖**：使用 JetPack 自带 Python 3.10+ 或 miniforge；在设备上 ``pip install -r edge_node/requirements.txt``。``grpcio`` 在 aarch64 上有官方 wheel，避免源码编译可显著缩短安装时间。
2. **网络**：工位相机/PLC 与云端 gRPC 地址分属不同网段时，**勿**在推理主线程解析 DNS；启动阶段缓存 ``grpc_target`` IP，上传线程独占阻塞。
3. **时钟**：``captured_at_iso`` 依赖系统 UTC；建议启用 NTP/Chrony，否则服务端合规时序分析会偏差。
4. **热与功耗**：持续 4 路 1080p@30 时关注 ``nvpmodel`` 功耗模式与散热；降频后若单帧推理 > 25ms，应按 OTA 规则回滚模型（见 ``edge_node/AGENTS.md``）。
5. **共享类型**：若需读取 FSM 拓扑等，仅允许**只读**引用 ``src/types/sop.py``（路径通过部署时把仓库 ``src/types`` 拷入 ``PYTHONPATH``，或后续发布独立 ``sop_types`` 包）；**禁止**依赖 ``src/services``。

## proto 桩

``edge_node/proto_gen/`` 为 ``proto/frame_upload.proto`` 生成代码的副本，与服务端消息兼容；更新 ``.proto`` 后需在两处重新运行 ``grpc_tools.protoc`` 并同步副本。
