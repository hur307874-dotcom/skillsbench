# 交接文档（迁移用）——Skill-Bench 评测系统

> 生成：2026-10-03。目的：即使原始对话丢失，凭本文 + 项目目录可完整复现全部工作。
> 代号：skill-bench｜工作区：D:\ai_project\skill-bench

## 一、这个项目在做什么

给"Agent Skill"（给 AI 的说明书，如 TDD 方法论）做**效果审计与修订**的系统：
用任务池考 AI（加载说明书 vs 裸考），机器判分、自动归因、再据此修订 Skill。

**主线问题**：Skills 到底有没有用？
**当前答案（v6.5 定稿）**：**Skills 价值边界论**——
- 能力饱和任务上（修 bug 这类训练数据里全是的东西）：分数无正收益 + 成本 +25~33%；
- 知识缺口任务上（内部约定/专有流程/冷门 API）：**A0 0.40 ≡ 安慰剂 0.40 << Skill 臂 0.90（+0.5）**。
- 一句话：**Skill 不是给模型补课，是给模型递答案。**

## 二、项目结构（迁移必带）

```
D:\ai_project\skill-bench\
├── backend/               评测系统后端
│   ├── orchestrator/      matrix(预设展开) + runner(执行/并发/幂等/预算护栏)
│   ├── cli_driver/        pi / codex / claude 三驱动（臂注入实现）
│   ├── graders/           runner.grade(F2P×P2P) + behavior_signals + process_judge
│   ├── validators/        task_validator（四关，--unidiff-zero）
│   ├── attribution/       归因器（detectors/engine/test_detectors）
│   ├── gate/              pilot_gate（准入判定 + baseline 回填 + 渠道健康）
│   ├── store/db.py        DuckDB（runs/events/signals）
│   ├── api/server.py      FastAPI 8 端点
│   └── llm_client.py      辅助 LLM 统一客户端（DIS relay）
├── scripts/               任务生产：forge_tasks(引擎) / mine_real_tasks / add_p2p
│                          / build_poolv3* / regen_poolv3 / kappa_sheet / pilot_gate
├── tasks/
│   ├── pool-v2/forged-final/   9 个 forged 任务（定版，四关+P2P）
│   ├── pool-v2/forge_specs/    声明式配方 yaml（换任务域只改这个）
│   ├── pool-v3/                3 个 convention-forge 任务（知识缺口）
│   ├── heldout-v2/             3 个新终验任务（轮换）
│   └── generated/              旧合成池（已降级为回归集）
├── skills/                被测 Skill：tdd-v1(冻结) / tdd-v2(被拦) / tdd-v3(定版)
│                          + streamkit-convention / deploykit-spec / fluxdb-semantics
│                          + placebo-cooking（安慰剂臂）
├── matrix/                实验预设 yaml（臂×任务×模型×n）
├── results/               每批次 runs.jsonl + work/<run>/trace.json
│   └── traces.duckdb      全库（700+ run / 11k+ 事件）
├── frontend/index.html    五视图仪表盘（消费 API）
└── docs/                  见下
```

## 三、关键文档（读这四份就能接手）

| 文档 | 内容 |
|---|---|
| `docs/PROJECT_STATUS_REPORT.md` | **v6.5 全景**：任务池三代演进、归因器、边界论、结论稳定性总账 |
| `docs/EXPERIMENT_LOG.md` | 每批次的决策/发现/依据（时间线最全，从 9-23 起） |
| `docs/POOL_V2.md` | 判分哲学（F2P×P2P）、四关、Pilot Gate、正式版口径 |
| `docs/POOL_V3.md` | 知识缺口池设计 + **三条铁律（泄题事故教训）** |

## 四、常用命令（迁移后照跑）

```bash
# 环境：Python 3.13（隔离 venv）
PY="C:/Users/17664/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 跑一批实验
DIS_API_KEY=sk-... "$PY" -m backend.orchestrator.runner matrix/pool-v20-main.yaml \
    --driver pi --batch my-batch            # 支持续跑（run_id 幂等）

# 数据入库 + 行为信号
"$PY" -m backend.store.db ingest results/my-batch

# 任务校验（四关，零 LLM）
"$PY" -m backend.validators.task_validator tasks/pool-v2/forged-final

# 归因（机械 + 指令联动）
"$PY" -m backend.attribution.engine --batch my-batch --skill skills/tdd-v1
"$PY" -m backend.attribution.test_detectors     # 单测

# Pilot Gate 判定 + baseline 回填 + 渠道健康
"$PY" -m backend.gate.pilot_gate results/my-batch --backfill

# 造任务（引擎 + 配方）
"$PY" scripts/forge_tasks.py tasks/pool-v2/forge_specs/more-itertools-10.8.0.yaml

# 起服务（前端 + API）
"$PY" -m uvicorn backend.api.server:app --port 8321
```

## 五、结论与证据（截至 2026-10-02）

| ID | 结论 | 证据强度 |
|---|---|---|
| C1 | v1（原版 tdd）成本持续高于裸考（+25~33% 轮次） | ★★★ 4 批 |
| C2 | v3（修订版）降本，开销介于 v1 与 A0 之间 | ★★★ 4 批 |
| C3 | 能力饱和处分数无正收益 | ★★★ n=5 全矩阵 |
| C4 | v1 弱基座随机性预算失效 | ★★ |
| C5 | **完成率/超时混淆渠道健康度**（方法论） | ★★★ 速度差 10-20 倍 |
| C6 | 弱基座 Skill 零产出税（40% vs 5%） | ★★ 待复测 |
| C7 | **知识缺口处 H1 为正（+0.5）** | ★★ 待 n=5 与扩族确认 |

## 六、未竟事项（接手优先级）

1. **pool-v3 扩族确认**：三族（streamkit/deploykit/fluxdb）n=5 干净批（文档已外迁到
   `%TEMP%/skillbench-v3-skills-x7q2`，防止 agent 搜盘）→ 确认 C7；
2. **κ 校准会话**：`docs/kappa_sheet.md`（20 卡，8 命中+12 无罪）待人工标注，
   ≥0.7 归因器才自动采信；
3. **A1 自主触发臂**：pi 原生 `--skill` 已支持，批次 `auto-probe` 跑过（结果待析）；
4. **docker 沙箱**：从合规项升级为 **pool-v3 结论可信性的前提**（文件系统未隔离，
   agent 会搜盘偷看知识文档）；
5. env 轨、process_judge κ 门启用、报告 v7.0（C7 确认后定稿"边界论"）。

## 七、迁移清单

必拷三处（见对话文件位置说明）：
1. `D:\ai_project\skill-bench\`（项目全部：代码/任务/结果/文档）
2. `C:\Users\17664\.workbuddy\projects\d-ai_project-skill-bench\*.jsonl`（对话原文）
3. `C:\Users\17664\.workbuddy\`（workbuddy.db 会话索引 + MEMORY.md + 连接器配置）

环境依赖：Python 3.13（venv 内需 fastapi/uvicorn/duckdb/pyyaml/pytest）；
DIS relay 需 `DIS_API_KEY`；pi CLI 需在本机可用。
