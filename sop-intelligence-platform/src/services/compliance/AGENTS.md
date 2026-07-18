# AGENTS.md — compliance 子模块专属规则

> **覆盖范围**：`src/services/compliance/` 目录。全局规则见根目录 `AGENTS.md`。

---

## 一、模块职责边界

```
fsm_runtime.py             ← 服务端 FSM 运行（共享 src/types/sop.py 类型定义）
confidence_classifier.py   ← 三档置信度分类逻辑（COMPLIANT / UNCERTAIN / VIOLATION）
divergence_detector.py     ← 大小模型分歧检测 → 触发数据湖写入
```

本模块是服务端 Slow Path 的核心，处理边缘节点上传的 `UNCERTAIN` 帧，调用 VLM 深度推理后输出最终判定。

---

## 二、置信度阈值修改规则（强制）

置信度阈值是整个系统的核心参数，修改影响面极广：

```
修改步骤（必须全部完成，否则不得提交）：

1. 修改 src/config/vlm.py 中的常量：
   CONF_LOW: float = 0.4    # UNCERTAIN 下界（低于此值 = VIOLATION）
   CONF_HIGH: float = 0.7   # COMPLIANT 下界（高于此值 = 合规）

2. 同步更新 docs/domain-logic.md 中"置信度三档定义"章节

3. 重新运行 tests/harness/compliance_eval/run_eval.py
   必须满足：Recall > 0.95，FPR < 5%，UNCERTAIN 比例 < 15%

4. 如果 UNCERTAIN 比例 > 15%，说明阈值区间过宽，回滚修改并分析原因

5. Commit message 格式：
   "config(vlm): adjust confidence thresholds LOW=X HIGH=Y, see docs/domain-logic.md"
```

**禁止**：在 `confidence_classifier.py` 中硬编码数值（如 `if score > 0.7`），必须引用 `src/config/vlm.py` 中的常量。

---

## 三、分歧检测规则

`divergence_detector.py` 的逻辑必须遵循：

```python
# 正确的分歧判定逻辑
def is_divergent(edge_result: InferenceResult, vlm_result: InferenceResult) -> bool:
    # 边缘模型判定合规，但 VLM 判定异常 → 分歧
    if edge_result.level == ConfidenceLevel.COMPLIANT and vlm_result.is_anomaly:
        return True
    # 边缘模型判定违规，但 VLM 否决 → 分歧（同样有价值）
    if edge_result.level == ConfidenceLevel.VIOLATION and not vlm_result.is_anomaly:
        return True
    return False
```

分歧帧写入数据湖时必须附带：
- `source: "auto"`（区分人工标记）
- `label`: VLM 的结论（作为伪标签）
- `sop_step`：当前 SOP 步骤 ID
- `workstation_id`：工位标识

---

## 四、Kafka 事件发布规则

通过 `src/adapters/messaging/kafka_producer.py` 发布事件，格式必须严格遵循：

```json
{
  "timestamp": "ISO8601",
  "workstation_id": "string",
  "event_type": "SOP_VIOLATION | BATCH_DEFECT | MODEL_CHANGEOVER",
  "sop_step": "integer",
  "frame_path": "minio://bucket/path.jpg",
  "confidence": "float"
}
```

**禁止**：直接在本模块实例化 Kafka Producer，必须调用 `src/adapters/messaging/kafka_producer.py`。

---

## 五、禁止行为清单

- ❌ 在 `fsm_runtime.py` 中调用 VLM API（VLM 调用在 compliance_service 的 gRPC 处理层）
- ❌ 在 `confidence_classifier.py` 中硬编码阈值数值
- ❌ 修改阈值而不同步更新 `docs/domain-logic.md`
- ❌ 分歧帧写入 MinIO 后不写 PostgreSQL 元数据（两步必须原子完成或有补偿机制）
