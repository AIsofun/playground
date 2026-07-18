# compliance_eval 评测集

帧级样本（与 ``docs/eval-standards.md`` §1.2 **帧级**形态一致），用于在 **不调用真实 vLLM** 的前提下回归慢路径门禁逻辑。

## 文件

- ``samples.json`` — JSON 数组，每项一条样本（字段名稳定，供 ``run_eval.py`` 读取）。

## 每条样本字段

| 字段 | 类型 | 说明 |
|------|------|------|
| ``id`` | string | 稳定标识，便于日志定位。 |
| ``edge_s`` | number | 边缘置信度 \(s \in [0,1]\)，经 ``ConfidenceClassifier`` 映射为 COMPLIANT / UNCERTAIN / VIOLATION。 |
| ``gold_violation`` | bool | **真值**：该帧场景是否应视为「违规」（用于 Recall / FPR 的混淆矩阵正类定义）。 |
| ``vlm_is_anomaly`` | bool | **冻结的 VLM 输出**：模拟 ``VlmComplianceVerdict.is_anomaly``；真实部署时该值应由 VLM 推理得到，Harness Phase 1 用固定表做回归。 |

## 预测口径（与 ``run_eval.py`` 一致）

对每条样本计算：

1. ``edge_level = ConfidenceClassifier.classify(edge_s)``（阈值来自 ``src/config/vlm.py``）。
2. ``pred_alarm = vlm.is_anomaly OR divergence``，其中 ``divergence = detect_divergence(edge_inference, vlm_verdict)``，与 ``UncertainFrameSlowPathOrchestrator`` 中 ``_should_publish_kafka`` 的「应外发复核类事件」判定一致（见 ``src/services/compliance/uncertain_frame_orchestrator.py``）。

与 ``ActionDetectionVerdict.UNCERTAIN`` 的区分见 ``docs/eval-standards.md`` §1.2 脚注；本目录统计的 **UNCERTAIN 比例** 仅指 ``ConfidenceLevel.UNCERTAIN``。

## 指标定义

见 ``tests/harness/compliance_eval/metrics.py`` 与 ``docs/eval-standards.md`` §1.1。
