# deploykit 发布规范（团队流水线纪律）

适用：deploykit 流水线执行器的使用与修复。血泪教训换来的规范，逐条必须遵守。

## 规范 P1：阶段集合与顺序固定

流水线必须**严格**按以下五阶段、此顺序执行，缺一/乱序一律拒绝：

```
preflight → canary → bake → promote → postcheck
```

- 顺序或集合违规必须抛 **`PhaseOrderError`**（`PipelineError` 的子类，
  独立类型——运维按异常类型分流告警，抛基类会漏告警）。

## 规范 P2：阶段门禁

- **canary** 必须携带 `health_check` 回调（缺失即拒绝）；
- **promote** 执行前必须存在灰度成功标记：
  `context["canary_success"] is True`
  （canary 的 fn 负责写入该标记；标记缺失或为 False 一律拒绝）。
- 门禁违规必须抛 **`GateError`**（同样是 `PipelineError` 的独立子类）。

## 规范 P3：校验先于执行

所有顺序/门禁检查必须在**任何阶段 fn 执行之前**完成——
绝不允许"跑了一半才发现乱序"。

## 验收清单

1. 乱序/缺阶段 → PhaseOrderError？
2. canary 缺 health_check → GateError？
3. canary_success 缺失/为 False 时 promote → GateError？
4. 全合规流水线照常执行、报告 executed 顺序正确？
