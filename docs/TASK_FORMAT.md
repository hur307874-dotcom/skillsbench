# TASK_FORMAT — skill-bench 任务格式规范（v1）

> 一个任务 = 一个残缺的代码仓库 + 一套藏起来的判分标准。
> 本格式对"缺陷修复"域通用，不为任何单个 Skill 的指令定做。

## 目录结构

```
tasks/<task_id>/
├── fixture/          # 残缺代码仓库（agent 唯一可见的部分；能跑但有 bug）
├── solution/
│   └── sites/        # gold 改法 = 一组有序补丁：site-01.patch … site-0N.patch
│                     # 每个补丁对应一个"应改处"（unified diff，可 git apply）
├── tests/            # 隐藏 pytest（判分时才挂载；agent 不可见）
├── wrong/            # 典型错解（目录 wrong_01/ …，每个是完整仓库副本）
├── meta.yaml         # 元数据（见下）
└── INTENT.md         # 出题意图：预设陷阱是什么、狙击哪些 F-ID、预期 Skill 在哪一步发挥作用
```

## meta.yaml

```yaml
task_id: d2-enum-01
difficulty: D2              # D1 琐碎 / D2 中等 / D3 困难
targets_fids: [F05, F03]    # 本任务能让哪些失效模式显形（引用 failure_modes.yaml）
sites_required: 4           # 应改处数 = solution/sites/ 下补丁数量（校验器核对一致）
forbidden_edits: [tests/]   # agent 改动这些路径直接判负
prompt: |                   # 给 agent 的任务描述（唯一输入文本）
  ...
```

## 判分语义

- agent 在 `fixture/` 副本上工作；判分时挂载 `tests/` 运行 pytest；
- 分数 = 通过测试比例；`forbidden_edits` 命中判 0；
- **完整性不是嘴说的**：`sites_required` 处漏改必须各自有测试覆盖（见校验器第 4 条）。

## 校验器（`skill-bench validate-tasks`）四条硬检查

1. **meta 完整**：字段齐全、`sites_required` == `solution/sites/` 补丁数、
   `targets_fids` 均存在于 failure_modes.yaml；
2. **gold 跑通**：fixture + 全部补丁 → 隐藏测试全过；
3. **错解判负**：`wrong/` 每个目录 → 测试必须失败（至少一个不通过）；
4. **逐处漏改有测试覆盖**：对每个补丁 i，fixture + 除 i 外全部补丁 → 测试必须失败。
   （H2 防循环论证的硬约束："应改 N 处"不是自己说的，是测试真的会抓。）

校验不过的任务拒绝入库，报错必须指出具体任务与具体哪条。

## 典型错解（wrong/）的用途

- 校验判分器不会"只会打勾"；
- 对应最常见的 agent 失败模式（如：只改报错处、改了测试、用了旧 API）。
