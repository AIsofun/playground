# AGENTS.md — edge_node 专属规则

> **覆盖范围**：`edge_node/` 目录下所有代码。  
> 本模块**独立部署于 NVIDIA Jetson Orin NX 16GB**，不在 `src/` 分层体系内。

---

## 一、硬件约束（绝对红线）

| 指标 | 目标值 | 超出后果 |
|------|--------|---------|
| YOLOv10 推理延迟 | < 20ms / 帧 | 工位实时性失效，FSM 判定滞后 |
| FSM 判定延迟 | < 5ms | 叠加总延迟超标 |
| gRPC 上传超时 | 2s（超时丢弃，记录本地日志）| 不得阻塞主线程 |
| 支持摄像头路数 | 最多 4 路 1080p@30fps | 资源超限 |
| 内存占用峰值 | < 12GB（预留 4GB 给系统）| OOM 导致进程崩溃 |

---

## 二、主线程实时性约束（最高优先级）

**主推理线程（GStreamer → YOLOv10 → ByteTrack → FSM）中：**

- ❌ **禁止**任何网络 I/O（HTTP 请求、gRPC 调用、数据库查询）
- ❌ **禁止**文件读写操作（日志写入除外，且必须异步）
- ❌ **禁止**Python GIL 密集型操作（使用多进程而非多线程）

**gRPC 帧上传**必须在**独立线程**中完成：
```python
# 正确模式：主线程放入队列，独立线程消费上传
upload_queue.put_nowait(frame)  # 主线程，非阻塞
# 独立 uploader_thread 从队列取帧，调用 gRPC stub
```

---

## 三、三档置信度输出规范

FSM 判定结果必须输出以下三档之一，**禁止直接输出浮点分数**给下游：

```python
class ConfidenceLevel(Enum):
    COMPLIANT  = "COMPLIANT"   # score > 0.7  → 本地日志，不上传
    UNCERTAIN  = "UNCERTAIN"   # 0.4 <= score <= 0.7 → 截帧 gRPC 上传
    VIOLATION  = "VIOLATION"   # score < 0.4 或触发关键规则 → 直接路由告警
```

阈值来源：与服务端保持一致，在 `edge_node/` 中维护**独立的常量文件**（不 import `src/config/`），数值必须与 `src/config/vlm.py` 同步。

---

## 四、OTA 热更新规则

边缘节点通过轮询 MinIO `models/` 版本文件接受更新：

- 检查间隔：开机时立即检查，之后每小时检查一次
- 更新内容：TensorRT `.engine` 文件 + FSM 状态机定义文件（JSON）
- **切换方式**：旧模型继续推理直到新模型加载完成，**切换必须无停机**
- 回滚机制：新模型推理延迟 > 25ms 时（超出阈值 25%），自动回滚到上一版本并告警

---

## 五、PatchCore 约束（Phase 2）

- PatchCore 特征库建立需要良品图像，换型时必须先重建特征库再启用检测
- **禁止**在 PatchCore 未重建特征库时启用异常检测（会产生大量误报）
- PatchCore 运行于**独立进程**，与主推理线程并行，不得争抢 TensorRT 资源
- 特征库重建流程参见 `.ai/skills/patchcore-setup.md`

---

## 六、日志规范

- 每帧判定结果必须写入本地 SQLite 滚动日志（保留 24 小时）
- `VIOLATION` 帧：写日志 + 上传事件（gRPC 异步）
- `UNCERTAIN` 帧：写日志 + 上传帧图像（gRPC 异步队列）
- `COMPLIANT` 帧：仅写本地日志，不上传

---

## 七、禁止行为清单

- ❌ 在主推理线程中调用任何阻塞 I/O
- ❌ 直接 import `src/services/` 或 `src/adapters/` 中的任何模块
- ❌ 在 OTA 更新期间中断当前帧的推理（热切换，无停机）
- ❌ 未重建 PatchCore 特征库就启用异常检测
- ❌ 硬编码摄像头 IP 地址（必须从配置文件读取）
