# compliance_eval（合规监控 Harness）

- **指标与门禁**：`docs/eval-standards.md` §1.1  
- **实现**：`metrics.py`（统计）、`run_eval.py`（读数据集 + 调用分档与分歧检测）  
- **数据集**：`eval_dataset/README.md`、`eval_dataset/samples.json`

## 运行

在项目根目录：

```bash
python tests/harness/compliance_eval/run_eval.py
```

成功时退出码 `0` 并打印 `✅ EVAL PASSED`；任一指标未达标则退出码 `1` 并列出原因。

## 与 VLM Prompt 的关系

- 冻结字段 `vlm_is_anomaly` 模拟 **VLM 复核输出**；真实评测应调用 vLLM 并由 `.ai/prompts/vlm-anomaly-check.txt` 驱动，契约见 `docs/module-specs/compliance-service.md` §3。  
- 修改该 Prompt 或阈值后须重新生成/更新 `samples.json` 或接入在线推理，并保证本 Harness 仍满足 `eval-standards.md`。
