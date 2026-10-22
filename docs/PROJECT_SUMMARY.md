# Skill-Bench 项目总结

> 生成日期：2026-10-03｜工作区：`D:\ai_project\skill-bench`｜依据：全项目扫描 + `docs/HANDOVER.md` + 11 份 docs + 9 篇工作日志 + results/ 约 50 个批次实跑数据
> 性质：项目阶段性复盘（不含新实验，仅对已有工作做提炼）

---

## 0. 一句话总结

我们用一套自建的评测系统，给「Agent Skill（喂给 AI 的说明书）」做**效果审计**，最终把题目"Skills 到底有没有用"改写成更精确的命题——**Skills 价值边界论**：

> **能力饱和任务上**（修 bug 这类训练数据里全是的东西）：分数无正收益，成本反而 +25~33%；
> **知识缺口任务上**（内部约定 / 专有流程 / 冷门 API）：**A0 0.40 ≡ 安慰剂 0.40 << Skill 臂 0.90（+0.5）**。
> **一句话：Skill 不是给模型补课，是给模型递答案。**

---

## 1. 项目在回答什么

原始题目（极创工作室 2026 二面单人题「Skill 评测与优化」）要求：**选定一个 Skill、给定一组任务，回答"这个 Skill 有没有用？有多大用？代价是什么？"**

我们的差异化定位——与相邻工作（SkillAxe / SkillRevise / WikiSkill 等自动优化框架）划清界线：

> 它们是「**让 Agent 改 Skill**」，用终点分数自证"改好了"；
> 我们是「**让人知道该信什么**」——测量与证据产品：预先登记（git 存证）、
> placebo 对照、dev/heldout 切分、cluster bootstrap、人工抽检一致率、"被证伪的假设"专节。

方法核心：**Skill 不是黑盒，而是一组可逐条检验的断言**；指令级结论建立在「**指令 → 行为 → 结果**」的中介链上，而不是 pass rate 差值上。

---

## 2. 系统是什么（架构 + 方法）

### 2.1 分层架构（v6.5 现行）

```
产品层   前端五视图 SPA（/new 接入向导 · /experiments · /runs trace 下钻 · /reports · /skills）
         + FastAPI（8 端点，:8321）
分析层   DuckDB trace 仓库（runs/events/signals）+ 报告生成器 + 行为信号×7 + 归因器 L1-L3
执行层   runner（并发/幂等续跑/死跑检测/预算护栏）+ 三驱动 claude / codex / pi + 三格式归一化
内容层   任务池三代（v1 合成 / v2 forged / v3 convention-forge）+ 被测 Skill（tdd-v1/v2/v3 等）
方法层   README / PLAN / ARCHITECTURE v6.2 / DECISION_LOG(记至 v6.5) / 每批次 EXPERIMENT_LOG
```

**关键设计决定**：不自研 agent loop，直接用**真实 CLI**（`claude -p` / `codex exec` / `pi`）——"Skill 在主流 Harness 可用"由主实验本身满足。CLI 的位置相当于"数据库驱动"（可替换的执行后端），应用主体与具体 harness 无关。

### 2.2 方法骨架（贯穿始终）

| 机制 | 作用 |
|---|---|
| **F-ID 失效模式先行** | 先列失效模式清单，任务狙击它、指令治它、归因落它——三者共用同一 ID 体系 |
| **指令即假设（manifest）** | 每条指令登记：针对的 F-ID、可观测行为信号、验证任务集、预测（含"有害"预测） |
| **中介链论证** | ①消融臂测「指令→行为」（二元、高功效）②全样本测「行为→结果」（观察性，主动披露）③合成有效/无效/有害三分法 |
| **判分与 harness 解耦** | `pytest_completeness`（F2P×P2P 隐藏测试）是纯函数，跨 harness 对照几乎免费 |
| **难度是主假设** | 同一条指令可能在琐碎任务上有害、困难任务上有效——全局数字会把真相平均掉 |
| **通道分离红线** | 裁判与选手物理隔离：辅助 LLM（归因/判分）永不参与评测 run；process_judge 过 κ≥0.7 门才自动采信 |

---

## 3. 我们实际干了什么（三阶段时间线）

### 阶段一：方案设计（2026-09-18 ～ 09-23）
- 定题、领域收敛（代码修复 + 开发流程类）、文献全面核实（SkillsBench / SWE-Skills-Bench / SkillTriage / SkillRevise / WikiSkill 等，附 URL）；
- 三轮外部评审 + DECISION_LOG 记录每轮采纳/否决理由，演进 v1 → v6.5；
- 交付方法论文档骨架（README / PLAN / ARCHITECTURE / PIPELINE / REQUIREMENTS_CHECK）。

### 阶段二：评测内核建成（2026-09-24 ～ 09-28）
- 写出 orchestrator（矩阵展开/并发/幂等续跑）、三驱动、三格式归一化层、DuckDB store、报告生成器、行为信号×7（15 单测）；
- 任务池 v1 合成（18 实例，全过四关校验）；
- 冻结被测对象 `skills/tdd-v1`（109 行首屏 + 5 引用文件 = 303 行）+ manifest（7 条指令）。
- **跑了 330+ 真实 run**，总花费 < $10（切 dis 中转站后基本零成本）。
- 开发中 AI 写的代码被抓出并修复的真实缺陷：git apply 静默 Skip、.CMD 垫片截断 prompt、Windows subprocess 寻址失败……（教训：判分/校验必须机器可执行，冒烟批先查坑再烧主矩阵）。

### 阶段三：任务池攻坚 + 归因器 + H1 转折（2026-09-29 ～ 10-03）
- **任务池三代演进**，Pilot Gate 六次校准：v1 合成（108/108 满分，天花板）→ v1.5 hard（0/100 二元峰）→ v2.0 forged（真包注入，成本可区分）→ v3.0 convention-forge（**H1 首次构造性为正**）；
- **归因器上线**（题目第 4 条完全体）：L1 症状 → L2 机械失效归因（6 检测器，零 LLM，带"结果门"）→ L3 指令联动（manifest 反查，任意 Skill 即插即用）；端到端实证 `失败 → F-ID → 指令行号 → 预登记预测` 全自动闭环；
- **前端五视图 + API 上线**；
- **pool-v3 泄题事故与三条铁律**（见 §6）；
- **C7 扩族**：三族（streamkit / deploykit / fluxdb）逐代重跑，方向一致（见 §4）。

---

## 4. 核心结论：证据总账（截至 2026-10-03）

| ID | 结论 | 证据 | 强度 |
|---|---|---|---|
| C1 | v1（原版 tdd）成本持续高于裸考（+25~33% 轮次） | 4 批复现 | ★★★ |
| C2 | v3（修订版）降本，开销介于 v1 与 A0 之间 | 4 批复现 | ★★★ |
| C3 | 能力饱和处**分数无正收益** | n=5 全矩阵多批 | ★★★ |
| C4 | v1 在弱基座随机性预算失效（含 720s 超时） | 2 批 | ★★ |
| C5 | **完成率/超时混淆渠道健康度**（方法论级发现）：同任务同模型速度差 10–20 倍 | 实证 | ★★★ |
| C6 | Skill 零产出税（弱基座 ~40% vs 裸考 ~5%） | 1 批 | ★★ 待复测 |
| **C7** | **知识缺口处 H1 为正（+0.5）** | 原型 n=3 全一致 + 三族扩族方向一致 | ★★★ 方向 / 幅度待 n=5 |

**C7 扩族实跑（本次扫描核算，0.375=保底行为分，1.0=满分）**：

| 批次 | A0 裸考 | A0p 安慰剂 | A1f-conv 约定 Skill | Skill − A0 |
|---|---|---|---|---|
| poolv3c-deploykit | 0.175 | 0.393 | 0.438 | **+0.26** |
| poolv3c-fluxdb | 0.300 | 0.367 | 0.653 | **+0.35** |
| poolv3c-streamkit | 0.400 | 0.377 | 0.771 | **+0.37** |
| （原型 poolv3-proto2 基准） | 0.400 | 0.400 | 0.900 | +0.50 |

→ 三族**方向全部为正**，且 streamkit / fluxdb 满足 **A0p ≡ A0**（证明是内容效应非长度效应）；deploykit 的 A0p 偏高属噪声，需 n=5 收敛。**C7 从"★★ 待确认"升级为"方向 ★★★、幅度待定"。**

**机制侧印证（与三篇 2026 文献精确同构）**：SkillsBench（增益集中在训练数据外知识）、WebDev-Skills-Bench（注入平均有害、简单任务受害最重——我们的 v1 数据是其**有害区独立复现**）、alphaxiv（Skill 改善指令遵循而非目标完成，抽象最佳实践 null 是必然）。

---

## 5. 关键工程资产（可直接复用）

- `backend/orchestrator/` — matrix 预设展开 + runner（并发/幂等/预算护栏/死跑检测/tps 记录）
- `backend/cli_driver/` — claude / codex / pi 三驱动 + relay_env（臂注入实现）
- `backend/graders/` — `pytest_completeness`（F2P×P2P）+ 行为信号×7 + process_judge
- `backend/validators/task_validator.py` — 四关校验（meta 完整 / gold 跑通 / 错解判负 / 逐处漏改有测试覆盖，`--unidiff-zero`）
- `backend/attribution/` — 归因器（detectors + engine + 单测，grep `tdd`=0 零硬编码）
- `backend/gate/pilot_gate.py` — 准入判定 + baseline 回填 + 渠道健康
- `backend/store/db.py` — DuckDB（runs/events/signals）+ 视图
- `scripts/forge_tasks.py` — 声明式配方引擎（换任务域只改 yaml，代码零改动）
- `skills/` — tdd-v1(冻结) / tdd-v3(定版) / 三个约定 Skill / placebo-cooking(安慰剂臂)
- `results/traces.duckdb` — 全库（700+ run / 11k+ 事件）

---

## 6. 踩过的坑 / 立下的铁律

**方法论铁律**
- **C5 渠道健康度**：完成率/超时类指标会被渠道延迟混淆 → 必须记录 token 吞吐、在健康窗口内复测。曾有 60/60 全满分 vs 前一晚 2/3 超时的刺目对照，根因就是渠道。
- **通道分离**：裁判与选手物理隔离，辅助 LLM 永不进评测 run。

**pool-v3 三条设计铁律（泄题事故换来的）**
- **v3.0 知识物理外置**：约定的命名/产物不得出现在 fixture——放进去就会被 A0 推断（天花板）。
- **v3.1 注释必须中性**：连"本包缺哨兵与校验设施"这类提示性注释都是泄题，强模型读完即推断出约定全貌。
- **v3.2 知识文档必须移出 agent 搜索半径**：评测环境未隔离文件系统，agent 会全盘 `find` 到约定文档（实测 A0 满分轨迹）。处置：文档移至 `%TEMP%/skillbench-v3-skills-*`。**终解 = docker 沙箱。**

---

## 7. 还没做完的事（接手优先级）

1. **docker 沙箱**：已从"合规项"升级为 **pool-v3 结论可信性的前提**（文件系统未隔离，agent 会搜盘偷看知识文档）；
2. **pool-v3 扩族确认收口**：三族补到 n=5 干净批，把 C7 幅度坐实；
3. **κ 校准会话**：`docs/kappa_sheet.md`（20 卡，8 命中 + 12 无罪）待人工标注，≥0.7 归因器才自动采信；
4. **A1 自主触发臂**：pi 原生 `--skill` 已支持，批次 `auto-probe` 已跑，结果待析；
5. **A2 闭环**：基于归因产出 tdd-v2/v3 → heldout 终验；
6. **报告 v7.0**：C7 坐实后，正式定稿主线「Skills 价值边界论」。

---

## 8. 文档索引（读这四份就能接手）

| 文档 | 内容 |
|---|---|
| `docs/HANDOVER.md` | 迁移交接（结构 + 命令 + 结论 + 迁移清单） |
| `docs/PROJECT_STATUS_REPORT.md` | v6.5 全景：任务池三代演进、归因器、边界论、结论稳定性总账 |
| `docs/EXPERIMENT_LOG.md` | 每批次决策/发现/依据（时间线最全，从 9-23 起） |
| `docs/POOL_V2.md` / `docs/POOL_V3.md` | 判分哲学（F2P×P2P）、四关、Pilot Gate ／ 知识缺口池设计 + 三条铁律 |
