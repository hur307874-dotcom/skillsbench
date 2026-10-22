# ARCHITECTURE — skill-bench 系统设计（v6.2）

> v6.2 口径：独立全栈**产品**；执行后端为**真实 CLI**（claude -p / codex exec，
> 可替换驱动），不自研 agent loop（v6 实测 `claude -p --output-format stream-json`
> 原生输出完整事件流后推翻 v5 的自研决定）；领域收敛为代码修复 + 开发流程类，
> 含可评性三档框架。

## 1. 应用形态总览

```
┌──────────────────────────────────────────────────────────────┐
│ 前端（React SPA）                                              │
│  /new          接入向导五步（选 Skill → 校验 → 指令拆解确认      │
│                → 登记确认[系统预填草稿+可评性标注] → 矩阵配置）    │
│  /experiments  实验看板（job 状态/成本/进度）                    │
│  /runs/:id     Trace 逐步下钻查看器（答辩演示核心）              │
│  /reports/:batch 对照表/散点图/难度×指令热力图/触发表/三分法表     │
│  /skills       Skill 与 manifest 管理、导出到 Claude Code/Codex  │
└──────────────┬───────────────────────────────────────────────┘
               │ HTTP/WebSocket
┌──────────────▼───────────────────────────────────────────────┐
│ 后端（Python + FastAPI）                                       │
│  ├─ orchestrator   矩阵 → job 队列、并发、缓存幂等、断点续跑     │
│  ├─ cli-driver     真实 CLI 驱动与臂注入（claude / codex 适配）  │
│  ├─ normalize      两家 JSONL → 统一 trace（只映射不丢弃）       │
│  ├─ graders        pytest_completeness / 行为信号检测器 /        │
│  │                 process_judge（可选副指标）                   │
│  ├─ analysis       behavior_detect / mediation / stats / 归因    │
│  └─ store          DuckDB（traces + scores + jobs）+ 文件工件    │
├──────────────▼───────────────────────────────────────────────┐
│ 执行层（WSL2 + Docker）                                        │
│  共享镜像（Python+pytest，digest 锁定）；每 run 一个容器；       │
│  fixture 任务时挂载、隐藏测试判分时挂载                          │
└──────────────────────────────────────────────────────────────┘
```

CLI 的位置相当于**数据库驱动**——可替换的执行后端，不是应用本身。
应用主体（编排、trace 仓库、分析、前端）与具体 harness 无关。

## 2. 执行后端与臂注入（v6 核心变更）

### 2.1 真实 CLI 驱动

| 臂 | claude CLI 实现 | codex CLI 实现 |
|----|----------------|----------------|
| A0 | `--disable-slash-commands` + `--setting-sources` 排除 Skill | `--ignore-user-config` 等效排除 |
| A1 | 挂载 Skill 目录，模型自主决定读不读（原生 skill_read 事件） | 对称实现 |
| A1f | `--append-system-prompt-file` 注入 SKILL.md 全文 | `-c` 注入 |
| A1-noref | SKILL.md 保留读取指引，引用文件不落盘 | 对称 |

A0 的"确实没加载"不靠信任 flag——**B1.5 全臂冒烟**逐项人工验证后才允许烧主矩阵。

### 2.2 归一化层（v6 最大技术风险，两道防线）

1. **原始 JSONL 一律原样留存**（`raw_event_ref`），归一化只映射不丢弃；
2. **一致性自动化测试**：两家各 3 条真实 run，归一化前后事件数、工具序列、
   token 合计必须一致（不靠肉眼）。

### 2.3 与主流 Harness 的合规关系

主实验直接跑在 claude / codex 真实 CLI 上——题目"Skill 在主流 Harness 上可正常使用"
由主实验本身满足（v5 的外推声明已不需要）。Pi Agent / dsh 走规范论证（未实证，报告声明）。
前端 /skills 页提供"导出到 Claude Code / Codex"指引。

## 3. 核心数据结构

### 3.1 `failure_modes.yaml`（预登记）

F-ID 失效模式清单（F03 不跑测试就收工、F05 漏改调用点、F07 改测试代替改实现、
**F15 等待不存在的用户**、**F16 批量造测试**……），任务狙击它、指令治它、归因落它。

### 3.2 `skills/<name>/manifest.yaml`（指令级假设映射）

```yaml
- id: I1
  text: "Confirm with user / Get user approval（L51-56, L58）"
  targets: [F15]
  behavior_signal: phantom_user_interaction   # 纯函数检测器，信号库选取
  verify_tasks: [d1-*, d2-enum-*]             # 消融臂只在这些任务上跑
  evaluability: A                              # A 可全评 / B 需扩任务族 / C 仅依从
  prediction: 有害（无人值守下诱发自问自答空转）
```

登记草稿由系统 LLM 预填，**人只勾选确认**；以 git commit 的 manifest 为准（预登记存证）。

### 3.3 任务（产品输入；系统内置默认测试集）

```
tasks/<task_id>/
├── fixture/        残缺代码仓库（agent 唯一可见）
├── solution/       gold 改法（仅自检用）
├── tests/          隐藏 pytest（判分时才挂载）
└── meta.yaml       difficulty / targets_fids / sites_required / forbidden_edits
```

内置默认测试集：3 难度档（D1 琐碎 / D2 中等 / D3 困难）× 4 族 × 2 实例 = 24 个，
参数化生成，dev 16 / heldout 8 族内切分。与任何具体 Skill 无关、不为被评 Skill 定做。
**任务校验器**强制四条：meta 完整 / gold 跑通 / 典型错解判负 / **逐处漏改有测试覆盖**
（还原单个修改点 → 对应测试转失败；H2 防循环论证的硬约束）。

## 4. Trace schema（纵切时定死）

```json
{"type":"run_meta","run_id":"t07-A1f-sonnet-r03","model":"...","cli":"claude-code@2.1",
 "skill_content_hash":"sha256:...","instruction_ids":["I1","I2","I4"],
 "ablated_instruction":"I3","inject":"forced","arm":"A1-x3"}
{"type":"step","i":1,"role":"assistant","text":"...","tokens":{"in":1200,"out":340}}
{"type":"tool_call","i":2,"name":"Grep","args":{"pattern":"http_get"},"duration_ms":95}
{"type":"skill_read","path":"SKILL.md","i":2,"via":"native"}
{"type":"behavior","name":"phantom_user_interaction","present":true,
 "wasted_turns":3,"wasted_tokens":2400}
{"type":"grade","score":0.5,"grader":"pytest_completeness",
 "detail":{"tests":"4/6","sites_fixed":3,"sites_required":5}}
{"type":"f_id_hits","ids":["F05"],"source":"attribution"}
```

全部灌入 `results/traces.duckdb` + 视图 + `analysis/query.py`——人（前端查看器）
与 Agent（SQL 入口）双通道可下钻。

## 5. 判定与分析

### 5.1 判定器（纯函数为主）

- **pytest_completeness**：隐藏测试 + 完整性断言；纯函数、与 harness 无关——
  跨 CLI 对照几乎免费的根本原因；
- **行为信号检测器 ×7**：trace → 0/1（不调 LLM，带单元测试）；中介链①环的功效来源；
- **process_judge**（可选副指标）：四条二元 rubric；κ<0.7 仅定性披露；砍单线第一位。

### 5.2 分析线

- **stats**：cluster bootstrap（按任务）/ FDR / CE=ΔP/ρ；口径"方向 + 逐任务模式，不主张 p<0.05"；
- **mediation**：① 消融臂「指令→行为」（二元、高功效）；② 全样本「行为→结果」
  （观察性关联，披露 + 消融准实验佐证）；合成有效/无效/有害三分法；
- **attribution**：失败先分叉「未触发/用错」→ F-ID 落格 → LLM 归因器 →
  分层抽检 30–40 条（有害优先）；
- **埋针校准**：自写埋针 Skill（已知缺陷）给出归因器 ground truth 准确率。

### 5.3 模型维度

claude 三档（Haiku/Sonnet/Opus）× A0/A1f 测 H4 衰减——**主判据为三档点估计的
单调趋势 + 方向一致**（~16 run/格下 CI 恒跨零，不作硬闸门）；codex 一档做跨厂商稳健性。
被评模型走 CLI 原生认证（中转站 base_url+key 从环境变量读，不硬编码、不入库、不写进 trace）。

## 6. 可复现性（两层 + 自验证）

- **execution reproducibility**：做不到（API 抖动），不假装；
- **judgment reproducibility**：`make reproduce` 从 trace 重算全部分数与报告，
  **并与原始 score 逐条比对输出一致性报告**——答辩可现场演示。

## 7. 目录结构

```
skill-bench/
├── docker-compose.yaml       # api / worker / web
├── failure_modes.yaml        # F-ID 清单（预登记）
├── tasks/
│   ├── families/             # 任务族定义（参数化模板）
│   └── generated/            # 内置默认测试集 24 实例（dev 16 / heldout 8）
├── skills/                   # tdd-v1/（冻结+manifest）placebo/ tdd-v2/ needle/ ...
├── images/                   # 共享任务镜像（digest 锁定）
├── backend/
│   ├── orchestrator/         # 矩阵展开 / 队列 / 缓存幂等
│   ├── cli_driver/           # claude / codex 驱动与臂注入
│   ├── normalize/            # 两家 JSONL → 统一 trace（+一致性测试）
│   ├── graders/              # pytest_completeness / behavior_signals / process_judge
│   ├── analysis/             # mediation / stats / attribution / needle_calibration / report
│   └── api/                  # FastAPI
├── frontend/                 # React SPA（/new /experiments /runs /reports /skills）
├── results/                  # <batch_id>/（批次 = 同模型版本 + 同镜像 digest）
├── docs/                     # EXPERIMENT_LOG / REPORT / DECISION_LOG / PIPELINE /
│                             # REQUIREMENTS_CHECK / TASK_FORMAT
└── Makefile                  # reproduce（含自验证）
```

## 8. 风险与备案

| 风险 | 备案 |
|------|------|
| **归一化层信息损耗**（v6 最大技术风险） | 原始 JSONL 原样留存；一致性自动化测试（§2.2） |
| WSL2/Docker 未装 | A0 第一件事一次性解决；镜像 digest 锁定 |
| A0 排除 flag 语义不符（A0 非真基线） | B1.5 全臂冒烟逐项人工验证 |
| 任务集工作量超期 | 先 3 实例走通全流程再批量；降为每档 4 个（共 12） |
| H1 因模型绕过测不出 | 主指标 = 浪费轮次/token（非卡死率） |
| 730 run 中途发现任务缺陷 | B1.5 冒烟（~20 run）先查坑 |
| API 成本超支 | 消融按 verify_tasks；断点续跑；中端模型迭代 |
| process_judge κ 不达标 | 仅定性披露；必要时整块砍（主结论不依赖） |
