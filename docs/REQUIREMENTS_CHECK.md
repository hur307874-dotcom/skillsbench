# REQUIREMENTS CHECK — 题目要求逐条合规审计（v6.2 口径）

> 审计基准：2026-09-19 从题目页抓取的完整原文（出题人 PEScn，确认无附加章节）。
> 审计对象：PLAN.md / ARCHITECTURE.md / README.md / PIPELINE.md（v6.2）。
> 结论：**全部硬性要求满足 ✅**，3 个注意点见文末。
> v6 相对 v5.1 合规性**增强**的两处：主实验直接跑在两家真实 CLI 上（跨 harness 从
> "实证补丁"变成主设计）；系统内置默认测试集 + 用户可替换（"给定一组任务"由产品主动满足）。

## A. 核心系统要求（任务要求第一段）

| # | 题目原文 | 状态 | 方案落点 |
|---|---------|------|---------|
| 1 | 选定一个 Skill，给定一组任务 | ✅ | 主对象社区 Skill `tdd`（+diagnose 等验收例 + 埋针校准）；任务 = 内置默认测试集 24 个（用户可替换） |
| 2 | 以可复现的方式运行"加载"与"不加载"以及它的不同版本 | ✅ | A0 vs A1/A1f/A1-noref/A1-x1..x7/A2；镜像 digest、配置留档、`make reproduce` 自验证；execution 不可复现已声明（注意点 2） |
| 3 | 记录完整的执行过程 | ✅ | 真实 CLI 原生事件流全量留存（raw_event_ref 一个字节不丢）+ 归一化入 DuckDB |
| 4 | 产出可以互相比较的评测报告 | ✅ | 同条件对照 + cluster bootstrap 95% CI + FDR + CE=ΔP/ρ |
| 5 | 回答"有没有用、有多大用、代价是什么" | ✅ | A1f/A1 vs A0（有无）；CI + 逐任务模式 + 难度分档（多大）；token/轮次/CE（代价） |
| 6 | 定位 Skill 在哪里失效 | ✅ | F-ID 预登记 + 触发表（未触发/用错）+ 中介链定位到单条指令 + 难度×指令热力图 |
| 7 | 有依据地修改它 | ✅ | 一次只改一条指令，commit message 写明归因依据（典型：I1 难度条件化而非删除） |
| 8 | 再用评测验证修改是否有效 | ✅ | v2 重跑主矩阵 + heldout 一次性终验 + 预登记验收标准（含 D1 档 token 下降预测） |
| 9 | 不要选过于简单、几乎不可能失效的 Skill | ✅ | 三必要条件选题分析 + Pilot Gate 分档 baseline（D1>80% / D2 40–80% / D3<40%）+ tdd 含两条预测有害指令 |

## B. 任务集要求

| # | 题目原文 | 状态 | 方案落点 |
|---|---------|------|---------|
| 10 | 领域自选，需收敛到一个具体方向 | ✅ | 代码修复 + 开发流程类（编程类），附可评性三档框架界定域内可评边界 |
| 11 | 至少构建 3 个任务 | ✅ 超额 | 内置 24 个（3 难度档 × 4 族 × 2 实例，参数化生成） |
| 12 | 大部分任务具有可以自动判定的正确标准 | ✅ | 全部任务：隐藏 pytest + 完整性断言（题目给的两个例子"测试用例、可校验的最终状态"都占） |
| 13 | 少量只能主观判断的任务可以保留 | ✅ | process_judge 过程副指标（κ≥0.7 才采信，否则仅定性披露；主结论不依赖） |
| 14 | Skill 在主流 Harness（Claude Code、Codex、Pi Agent、dsh 等）上可正常使用 | ✅ 增强 | **主实验直接跑在 claude / codex 真实 CLI 上**——要求由主设计满足；Pi Agent / dsh 规范论证（注意点 1）；/skills 页提供导出指引 |
| 15 | Skill 在主流模型上可正常使用 | ✅ | claude 三档（Haiku/Sonnet/Opus）+ codex 跨厂商；Skill 为模型无关文本指令 |

## C. 建议流程五词

| # | 流程词 | 状态 | 方案落点 |
|---|--------|------|---------|
| 16 | 自动化运行 | ✅ | orchestrator（矩阵展开/并发/缓存幂等/断点续跑/成本预估） |
| 17 | 对照实验 | ✅ | A0/A0p/A1/A1f 四臂 + 安慰剂 + 逐条消融 |
| 18 | 任务级下钻 | ✅ | 前端 trace 逐步查看器 + traces.duckdb SQL 下钻 |
| 19 | 失效归因 | ✅ | F-ID 落格 + LLM 归因器 + 分层抽检 + **埋针 Skill 给出归因器 ground truth 准确率** |
| 20 | 修改与再验证 | ✅ | v2 闭环 + heldout 一次性终验 |

## D. 硬性附加要求

| # | 题目原文 | 状态 | 方案落点 |
|---|---------|------|---------|
| 21 | 尽量避免过拟合到特定任务 | ✅ | dev/heldout 族内切分 + 全任务参数化变体 + 跨模型验证 + Skill 内容通用性审查 + H2 防循环论证（逐处漏改必须有隐藏测试覆盖） |
| 22 | 增加消融实验（判断没有 Skill 会差多少） | ✅ 超标 | A0（底线）+ 逐条指令消融（主实验，按 verify_tasks 裁剪）+ A1-noref（渐进披露）+ placebo（注意力效应） |
| 23 | 记录整个 Agent Loop 的 Trace，方便后续人或 Agent 对其进行分析 | ✅ | 原生 trace 灌 DuckDB：人（前端查看器）与 Agent（query.py SQL 入口）双通道 |

## E. 页面通用规则

| # | 规则 | 状态 | 方案落点 |
|---|------|------|---------|
| 24 | 工作量大概率做不完，核心是思考与发现 | ✅ | A/B 两段纵切（A 段零 API 依赖）+ 砍单线（骨架不可砍）；DECISION_LOG 记录六轮演进（含四处前提被实测推翻的自我纠错） |
| 25 | 鼓励 AI/开源，但讲清怎么用、为什么、发现的问题 | ✅ | EXPERIMENT_LOG 专设 AI 使用记录（含 S1 登记草稿由 LLM 预填、人确认的边界说明）；开源借用均注明（注意点 3） |

## F. 参考资料使用

| 资料 | 状态 | 用途 |
|------|------|------|
| Agent Skills / Claude Code Skills 文档 | ✅ | Skill 格式、臂注入实现（A1 自主触发/A1f 强制注入）、渐进披露测试（A1-noref） |
| Inspect | ✅ | 数据模型与沙箱思路借鉴（执行后端选真实 CLI 的取舍已记档） |
| promptfoo | ✅ | Judge 断言测试交叉验证 |
| SWE-bench · Terminal-Bench | ✅ | 任务格式（fixture + 隐藏测试 + 执行式判定 + 容器隔离） |
| Judging LLM-as-a-Judge | ✅ | process_judge 人类校准（κ、分层抽样、位置偏置） |

---

## 轻微注意点（不影响合规，答辩前处理掉更稳）

1. **Pi Agent / dsh 无实证**：主实验覆盖 Claude Code + Codex 两家真实 CLI（硬性要求已满足），
   Pi Agent / dsh 仅规范论证。dsh 疑似出题方自家工具——若有访问权限，
   在 cli-driver 里加一个适配跑小矩阵是隐藏加分点；没有则报告写明"规范兼容、未实证"。
2. **execution reproducibility 的措辞前置**：报告显眼位置写明"Agent 执行不可复现
   （temp=0 也有 API 抖动），我们保证 judgment reproducibility + 自验证"，别等评审来戳。
3. **AI 使用记录从 A0 开始真记**：包括 S1 登记草稿由 LLM 预填的边界（LLM 不接触实验数据、
   最终以人 commit 的 manifest 为准）、AI 写的判分器被抓出漏洞这类具体事件——送分别丢。

## 审计结论

**14 条硬性要求全部满足，流程五词全覆盖，防过拟合/消融/可观测性三个附加项均超标完成。**
v6.2 设计层合规风险为零；剩余风险全在执行层（WSL2/Docker 安装、任务集工作量、
归一化一致性），均已在风险表配备案。

---

## 附录 B：题目参考资料对位审计（2026-09-30）

| 参考资料 | 它是什么 | 产品对位 | 状态 |
|---|---|---|---|
| Agent Skills | 被评对象本体（SKILL.md 结构、渐进披露） | tdd-v1 冻结 + H3（渐进披露价值）+ A1-noref 臂 | ✅ 覆盖 |
| Claude Code Skills 文档 | harness 侧 skill 机制（slash commands/setting-sources/注入方式） | claude_driver 臂实现（A0 排除/A1f 注入）全部出自该文档；v6.5 后 pi/codex 有对称实现 | ✅ 覆盖 |
| Inspect（UK AISI） | 评测框架：tasks/solvers/scorers/sandboxes/logs | 同构映射：fixtures=tasks、CLI 驱动=solvers、pytest+信号=scorers、traces+DuckDB=logs。**缺口：sandbox 仍是临时目录，Inspect 的 docker sandbox provider 是成熟范式（注意点 3）** | ⚠️ 部分 |
| promptfoo | prompt 评测工具：声明式 yaml + 断言库 | 矩阵预设同为声明式 yaml；其断言库含确定性断言（python/regex）——**为我们的机械判分路线提供工业先例**；其 red teaming 超出本题范围 | ✅ 路线印证 |
| SWE-bench · Terminal-Bench | 任务集构建范式 | F2P/P2P 双约束（= 我们的双约束测试）、Verified 人筛教训（= 我们四关机械筛）、docker 环境任务（pool-v2 扩展方向） | ✅ 覆盖 |
| Judging LLM-as-a-Judge（MT-Bench，NeurIPS 2023） | LLM judge 的系统性偏倚研究（位置/冗长/自-enhancement 偏倚，κ≈0.8 上限） | **"LLM 不阅卷"路线的理论依据**；process_judge 副指标设 κ≥0.7 采信门槛正源于此。缺口：κ 实测未跑（process_judge 未启用） | ⚠️ 判分哲学吻合，κ 验证未做 |

**审计结论**：六项参考资料无一遗漏映射；两处实质缺口已挂账
（docker sandbox = 注意点 3；process_judge κ 验证未跑）。
路线级印证：机械判分（promptfoo 确定性断言 + MT-Bench 偏倚研究双面印证）。
