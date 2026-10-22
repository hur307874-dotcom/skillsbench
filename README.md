# skill-bench

> 一套**独立全栈**的 Agent Skill 评测与优化**产品**（React 前端 + FastAPI 后端 +
> 真实 CLI 执行后端 + Docker 沙箱 + DuckDB trace 仓库）。
> **输入一个 Skill（+ 可选任务集），系统干完剩下全部。**
> 回答三个问题：**这个 Skill 有没有用？有多大用？代价是什么？**
> 方法核心：**Skill 不是黑盒，而是一组可逐条检验的断言；
> 指令级结论建立在「指令→行为→结果」的中介链上。**

极创工作室 2026 二面单人题「Skill 评测与优化」的作答项目。

## 背景与定位

写一个 Skill 只要十分钟，判断它有没有用却几乎没人做——大多数 Skill 的"有效性"来自"俺寻思"。
已有基准给出了冷峻的证据：**SWE-Skills-Bench 实测 49 个公开 Skill 中 39 个零增益
（平均仅 +1.2pp，token 开销最高 +451%）**；SkillTriage 进一步发现 Skill 引入的失效中
最大来源是**过度验证（67/307 例）**——checklist 变成强制劳动。

本项目与相邻工作的定位差异（相关文献已全部核实，见文末）：

> SkillAxe / SkillRevise / WikiSkill 都是**自动优化框架**——LLM 自己改 Skill，
> 用终点分数证明"改好了"；归因服务于下一轮自动编辑，不做预先登记、不控制过拟合。
> 我们做的是**测量与证据产品**：预先登记（git 存证）、placebo 对照、dev/heldout、
> cluster bootstrap、人工抽检一致率、"被证伪的假设"专节——
> 目标是让人能看着证据决定这条指令留不留。
> **一句话：它们让 Agent 改 Skill，我们让人知道该信什么。**

## 评测范围：代码修复 + 开发流程类 Skill

选定编程域因为三个必要条件同时成立：判分自动客观（隐藏 pytest）、
主流 Skill 是流程型（知识型几乎不可能失效）、难度可参数化。
生态佐证：**superpowers 合集 ~28 万 star、290 万+ 安装，为生态采用度第一的 Skill 项目，
14 个 Skill 全为开发流程纪律类**（2026-09 注册表自报数据）。

**可评性三档框架**：判断一条指令能否被评测，统一标准是
"它承诺的好处能否翻译成可自动判定的终态"——
A 可全评（tdd / diagnose / systematic-debugging / code-review 等）/
B 需扩任务族（brainstorming、writing-plans 等）/
C 仅依从可评（worktrees、并行调度等，结论降级为"依从性检验"）。
S1 登记环节自动为每条指令标注可评性等级。

## 被评对象

- **主对象：社区 Skill `tdd`**（superpowers 系，~21.7 万安装）——有真实渐进披露结构
  （首屏 109 行 + 5 个引用文件共 303 行，可测"分层有没有用"），
  且含两条预测有害的指令（反复要求向用户确认；最小化修改与完整性冲突）；
- **通用性验收**：`diagnose`、`improve-codebase-architecture` 等 A 档 Skill
  走同一条接入流程、全程不改代码；
- **归因器校准**：自写"埋针 Skill"（故意埋入 3–4 个已知缺陷），
  给出归因器在已知 ground truth 上的准确率——相邻工作都没做这件事。

## 方法要点

- **失效模式先行**：F-ID 清单预登记，任务、Skill 指令、归因分类法三者共用同一 ID 体系；
- **指令级中介链论证**：① 消融臂测「指令→行为」（二元信号、高功效）；
  ② 全样本测「行为→结果」（观察性关联，主动披露 + 消融作准实验佐证）；
  合成「有效 / 无效 / 有害」三分法；
- **难度翻转是主假设**：同一条指令在琐碎任务上可能有害、在困难任务上有效——
  全局数字会把真相平均掉；D1 档主指标为浪费的轮次/token（通过率有天花板）；
- **真实 CLI 主实验**：claude / codex 真实执行后端，跨 harness 合规由主实验本身满足；
- **可复现**：共享镜像 digest、纯函数判分、预登记 git 存证、
  `make reproduce` 重算并**自验证**（与原始分数逐条比对）；
- **可下钻**：全量 Trace 灌入 DuckDB，前端查看器 + SQL 双入口。

## 快速开始（WSL2 内）

```bash
docker compose up -d                    # api / worker / web

# 接入一个 Skill（也可用 CLI）
skill-bench init ~/.claude/skills/tdd   # 规则切分 + LLM 预填登记草稿 → manifest.yaml
skill-bench validate-tasks tasks/generated/
skill-bench run --matrix matrix/main.yaml
skill-bench report <batch-id>

# 前端：接入向导 / 实验看板 / trace 下钻 / 报告页
open http://localhost:3000

# 从原始 trace 重算全部分数与报告，并与原始分数逐条比对（自验证）
make reproduce
```

## 目录结构

```
skill-bench/
├── docker-compose.yaml     # api / worker / web
├── failure_modes.yaml      # F-ID 失效模式清单（预登记）
├── tasks/                  # families/ + generated/（内置默认测试集 24 实例）
├── skills/                 # tdd-v1/（含 manifest）placebo/ tdd-v2/ needle/ ...
├── images/                 # 共享任务镜像（digest 锁定）
├── backend/                # orchestrator / cli_driver / normalize / graders / analysis / api
├── frontend/               # React SPA（/new /experiments /runs /reports /skills）
├── results/                # <batch_id>/ + traces.duckdb
├── docs/                   # EXPERIMENT_LOG / REPORT / DECISION_LOG / PIPELINE /
│                           # REQUIREMENTS_CHECK / TASK_FORMAT
└── Makefile                # reproduce（含自验证）
```

## 文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 应用形态、执行后端与臂注入、核心数据结构、判定与分析
- [PLAN.md](PLAN.md) — 执行计划：交付标准、实验臂、假设预登记、预算、A/B 两段流程
- [docs/PIPELINE.md](docs/PIPELINE.md) — 产品全通路（输入 → 报告 → 闭环，含质量门与人工介入点）
- [docs/REQUIREMENTS_CHECK.md](docs/REQUIREMENTS_CHECK.md) — 题目要求逐条合规审计
- [docs/DECISION_LOG.md](docs/DECISION_LOG.md) — 方案演进记录（v1→v6.2，每轮批评与采纳/否决理由）

## 相关工作（全部逐条核实）

静态基准：**SkillsBench**（[arXiv:2602.12670](https://arxiv.org/abs/2602.12670)，curated +16.2pp、SWE 仅 +4.5pp）、
**SWE-Skills-Bench**（[arXiv:2603.15401](https://arxiv.org/abs/2603.15401)，39/49 零增益、token 最高 +451%）、
**SkillGenBench**（[arXiv:2605.18693](https://arxiv.org/abs/2605.18693)）、
**SkillLearnBench**（[arXiv:2604.20087](https://arxiv.org/abs/2604.20087)）。

自动优化与归因框架（定位对位见上文）：**SkillAxe**（[arXiv:2606.10546](https://arxiv.org/abs/2606.10546)，Microsoft）、
**SkillTriage**（[arXiv:2608.11888](https://arxiv.org/abs/2608.11888)，307 例失效、最大源过度验证 67 例）、
**SkillRevise**（[arXiv:2606.01139](https://arxiv.org/abs/2606.01139)，SkillsBench 36%→61.6%）、
**WikiSkill**（[arXiv:2608.27454](https://arxiv.org/abs/2608.27454)，Google；自述不评估 triggering）。

工具与基础设施：agent-skills-eval（[npm](https://www.npmjs.com/package/agent-skills-eval)）、
Inspect AI、Terminal-Bench、promptfoo、SWE-bench。
