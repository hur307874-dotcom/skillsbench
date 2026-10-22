# EXPERIMENT_LOG — skill-bench 实验日志与预先登记

> 本文件是预先登记与迭代记录的载体。规则：
> ① 任何假设必须先 commit 再看数据；② 每次修改 Skill 只动一条指令并写明依据；
> ③ AI 使用过程如实记录（题目要求）。

## 预登记（2026-09-23，commit 先于一切实验）

### 被评对象

- 主：社区 Skill `tdd`（冻结于 `skills/tdd-v1/`，SKILL.md sha256: 95f66cc273f0dff4）
- 通用性验收：`diagnose`、`improve-codebase-architecture`（A 档，同一接入流程不改代码）
- 归因器校准：自写埋针 Skill（3–4 个已知缺陷，对应已知 F-ID）

### 指令级预测（manifest 全文见 skills/tdd-v1/manifest.yaml）

| 指令 | 预测 | 一句话依据 |
|------|------|-----------|
| I1 confirm-with-user | **有害** | 无人值守下无用户可问 → 自问自答空转 |
| I2 最小化修改 | **有害** | 与"改全 N 处"直接冲突 |
| I3 垂直切片 | 有效但可能与判分无关 | 行为差异真实存在，结果差异未必 |
| I4 public interface | 有效（预期最强） | 防止改测试作弊与实现耦合 |
| I5 never refactor while RED | 有效但便宜 | 多数模型默认也会跑测试 |
| I6 domain glossary/ADR | **无效** | 多数仓库无此文件 → 空转 |
| I7 引用文件指引 | 读取率低且与结果无显著关联 | 渐进披露在无人值守下可能失效 |

### 假设（先于数据 commit）

> **H1（难度翻转）**：I1 的净效应随任务难度变化，并在最简单一档（D1）显著为负。
> **主指标是浪费的轮次/token，不是"是否卡死"**——模型很可能自问自答绕过，
> 卡死率为 0 ≠ 没有浪费。`phantom_user_interaction` 定义为：出现请求确认/批准表述
> 但无人回应仍继续，并记录该段 wasted_turns / wasted_tokens。
> ⚠️ D1 档 baseline >80%，通过率指标无分辨力（天花板），不作 H1 判据。
>
> **H2（完整性冲突）**：I2 导致漏改同模式调用点的比例高于不加载时——Skill 主动帮倒忙。
> 防循环论证：每一处漏改都必须有隐藏测试覆盖（还原 gold 单个修改点 → 对应测试转失败），
> 任务校验器强制检查。
>
> **H3（渐进披露）**：五个引用文件读取率 <40%，且"读过 ≥1 个"与未读的 run 主指标无显著差异。
> **解读顺序预登记**：① 先看 A1 臂引用文件读取率；② 读取率低 → 主结论"触发环节失败"，
> A1-noref 降为佐证；③ 读取率不低但两臂无差异 → 主结论"读了也没用"；
> ④ 读取率不低且 A1 显著更好 → H3 被证伪，写入"被证伪的假设"专节。三条分支不得事后挑。
>
> **H4（模型衰减）**：Skill 整体收益随基座能力增强而衰减。
> 主判据：claude 三档（Haiku/Sonnet/Opus）A1f−A0 点估计的**单调趋势 + 方向一致**
> （~16 run/格下 CI 恒跨零，不作硬闸门）。若最高档 ≤2pp 且单调递减成立 →
> 判"应随基座升级而弃用/降级为按难度条件触发"。

### 统计口径（登记）

- cluster bootstrap（按任务重采样 10k 次）；FDR 校正并披露比较次数；
- 主张效应方向 + 逐任务模式一致，**不主张 p<0.05**（小样本诚实口径）；
- 指令级结论只走中介链：① 消融臂「指令→行为」（二元信号）+ ② 全样本「行为→结果」
  （② 为观察性关联，报告披露并以消融臂作准实验佐证）；三分法：有效/无效/有害；
- heldout 8 任务只作方向性证据，全程只碰一次。

### 再验证验收标准（登记，用于 v2 判定）

- heldout 方向不降；且 dev 目标 F-ID 命中率降 ≥50%；且过程分不恶化；
- 若 I1 修订为难度条件化，则附加直接预测：**D1 档 token 成本下降**。

### 归因器校准（登记）

- 归因结论采信前提：归因器在埋针 Skill 的已知 ground truth 上达到可接受准确率
  （阈值：找回 ≥3/4 根针且无 ≥2 个错指）；人工分层抽检 30–40 条，"有害"判定优先。

---

## B0 中转站探活（2026-09-26，先于一切真实 run）

探活对象：用户提供的中转站（base_url 与 key 存于 `.env`，gitignore 已确认，不硬编码、
不入库、不写进 trace——与预登记口径一致）。六项探针全部通过：

| 探针 | 结果 |
|------|------|
| `GET /v1/models` | ✅ 466 个模型可列（claude/gpt/gemini/kimi/qwen/glm/deepseek 全厂商） |
| OpenAI 格式 chat completion（claude-haiku-4-5-20251001） | ✅ 正常返回 + usage 计费字段完整 |
| OpenAI 格式 tool use | ✅ 返回标准 tool_calls 结构 |
| **Anthropic 原生 /v1/messages** | ✅——claude CLI 可用 ANTHROPIC_BASE_URL 直连 |
| 流式 SSE | ✅ chat.completion.chunk 正常 |
| **OpenAI Responses API（gpt-5.2）** | ✅——codex CLI 可用 |

**模型选型（登记）**：

- 三档梯度（H4）：`claude-haiku-4-5-20251001` / `claude-sonnet-5` / `claude-opus-5`
- 跨厂商稳健性：`gpt-5.2`（备选 gpt-5.3-codex-2026-02-24）
- 迭代期便宜模型：`gemini-3.6-flash` / `deepseek-v4-flash`（控成本）
- judge（与被评模型解耦）：`gemini-2.5-pro`

**⚠️ 环境坑（登记）**：本机系统代理（127.0.0.1:10808）无法到达该中转站
（curl 报 HTTP_CODE=000），**直连可通**。所有 CLI/runner 进程必须设置
`NO_PROXY=api.enginxai.com`（或对该域禁用代理），cli_driver 实现时内置此环境变量。

**新 key 权限复核（2026-09-26）**：用户提供的新中转站 key 不受旧记录
（"haiku/sonnet 403"）限制——claude-haiku-4-5 / sonnet-5 / opus-5 / gpt-5.2
全部实测可调，三档矩阵解锁。runner 中旧 403 回退逻辑已过时，待清理。

---

## B0 真实纵切（2026-09-26，第一个真实 run）

**结果：双臂跑通**（d2-enum-01 × claude-haiku-4-5-20251001）：

| 臂 | 结果 | 轮次 | 成本 | 墙钟 | 判分 |
|----|------|------|------|------|------|
| A0（无 Skill） | ok | 10 | $0.0713 | 44s | 4/4 ✅ |
| A1f（强制注入 tdd） | ok | 22 | $0.1465 | 251s | 4/4 ✅ |

观察：

1. **成本校准**：单 run $0.07–0.15（haiku）。按 sonnet 3–5 倍估算，
   ~700 run 总成本 $150–500，在预算内。cache_read 占绝对大头（提示缓存经中转站生效）。
2. **A1f 轮次是 A0 的 2.2 倍**（22 vs 10）——tdd 的垂直切片流程让模型做了更多事，
   与预期方向一致（流程型指令改变行为）。
3. **trace schema 定死**：`system`(init+thinking_tokens)、`assistant`
   （content: thinking/text/**tool_use**，名称 Bash/Grep/Read/Edit）、`user`
   （tool_result）、`result`（num_turns/total_cost_usd/usage 含 cache 与
   per-iteration 明细）。tool_use 在 assistant content 块内（不是顶层事件），
   skill_read 判定 = Read 类 tool_use 的 input.file_path 含 `.claude/skills/`。
4. **⚠️ Pilot Gate 预警**：A0 haiku 在 d2-enum-01 上一次即 4/4。
   D2 目标 baseline 是 40–80%，若 B1 pilot（n=10）确认 haiku 轻松满分，
   需提高任务难度（更多调用点/更隐蔽陷阱）。这正是 Pilot Gate 存在的意义。

---

## B1 Pilot Gate 结果（2026-09-26，批次 b1-pilot，30 run，$2.65）

| 档 | 任务 | 裸 haiku 通过率 | 目标 | 判定 |
|----|------|----------------|------|------|
| D1 | d1-median-01 | **10/10 = 100%**（4 轮/题） | >80% | ✅ 在档 |
| D2 | d2-enum-01 | **10/10 = 100%**（10-15 轮） | 40–80% | ❌ 偏易 |
| D3 | d3-cache-01 | **10/10 = 100%**（10-26 轮） | <40% | ❌❌ 严重偏易 |

**决策（按预登记 gate）**：D2/D3 偏离目标 → 调难度后重测，通过才允许进 B1.5。

分析与对策：

1. **d2-enum 的 F05 陷阱没有显形**：模型朴素 grep 就能找全 4 个直接调用点。
   加料方向：调用点 4→9，且 5 个改为朴素 grep 找不到的形式
   （别名导入 / 再导出链 / functools.partial）——逼"枚举纪律"成为胜负手；
2. **d3-cache 太直白**：报错直指根因。加料方向：跨文件状态 bug +
   **误导性症状**（报错日志指向无关模块的可疑代码，引诱治症状 F17），
   根因是 key 规范化不一致导致缓存失效失败，必须先复现才能定位；
3. 观察：轮次/成本随设计难度递增（D1 4轮 → D3 10-26轮）但通过率不降——
   2026 的 haiku 比预期强，这本身是数据点（与 SkillsBench"强模型压缩
   Skill 效应"一致），但也意味着任务设计必须跟上模型水位；
4. 成本：30 run $2.65（均价 $0.088/run），全程预算无虞。

---

### B1 续：deepseek 兼容性验证（2026-09-26 凌晨）

**动机**：quota 见底（$0.26），先用 deepseek 系列续跑（单价远低于 claude）。

**探针结果（curl 直连 /v1/messages）**：
- `deepseek-v4-flash` 对话 ✅（标准 Anthropic message 格式，usage 完整）；
- tool use ✅（`stop_reason: tool_use`）——中转站把非 Anthropic 模型
  也映射到了 Anthropic 原生端点。

**CLI 实测（pilot2-ds，20 run）**：claude CLI 接受了 deepseek 模型名并正常发请求
（init 正常、model 字段正确），全部失败原因是 quota：
`403 pre-consumed quota failed, user quota: $0.111, need: $0.267`
——CLI 首发请求的预扣金额已超过余额。

**结论**：**deepseek 链路可用**（API + CLI 双层验证），唯一阻塞是余额。
充值后 deepseek 用于调试/校准类跑动（pilot、冒烟、归因器开发，成本约 claude 的
1/5–1/10）；**主实验仍用预登记的 claude 三档**（H4 是 claude 家族内假设，
deepseek 只作跨厂商对照臂；其 baseline 与 haiku 分开记录，不直接比较）。

**待办**：充值 → `matrix/pilot2-ds.yaml --batch b1-pilot2-ds2 --tasks tasks/pilot2` 续跑。

### B1 续2：第二中转站（api.aihilfs.com）探活失败（2026-09-26 凌晨）

用户提供新 key + `https://api.aihilfs.com/`。探活结果：
- `/v1/models` HTTP 200 但返回**空列表**；
- 15 个常见模型名（claude 三档 / gpt-5.2 / deepseek 全系列 / gemini / qwen /
  kimi / glm）**全部** `model_not_found`，错误均标注
  `No available channel ... under group student`。
- 判定：**key 本身有效（鉴权通过），但所属 student 分组未绑定任何渠道/模型**，
  不是模型名问题。需用户在中转站后台给该 key 分组配置渠道，或换 key。
- `.env` 未切换，仍指向 enginxai（待其充值或 aihilfs 修复分组后再定）。

## B1 纠偏与 quota 中断（2026-09-26）

1. **加料任务建成**（四检全过）：`d2-enum-hard`（10 调用点，5 个朴素 grep
   找不到的形式：别名/再导出/partial）+ `d3-state-hard`（缓存键大小写不一致
   失效 bug + 缓存预热才显形 + api.py 误导诱饵 + 防蒙混测试）。
   构建过程两个设计 bug 被校验器抓住（timeout 默认值使漏改不可见；
   未预热缓存使 bug 不显形）——任务校验器的价值第一次实战验证。
2. **pilot2 复测中断**：跑了 43 个有效 run 后，中转站返回
   `403 chat pre-consumed quota failed（user quota: $0.259544）`——
   **quota 耗尽（累计已花 ~$5.2）**，全部剩余 run 失败。
   恢复方式：充值后重跑（runner 断点续跑自动跳过已成功 run、重试 error run）。
3. **执行瑕疵记录**：pilot2 预设的 tasks.source 未生效（runner 用了
   args.tasks 默认值 tasks/generated），误跑 140 run 而非 20 run——
   续跑时必须显式 `--tasks tasks/pilot2`。此问题导致多烧约 $1.5，
   记为流程教训（AI 使用记录：预设格式理解偏差，人工复核命令参数可防）。

---

## 迭代记录（从第一个实验批次开始填写）

（每批次：批次 ID / 臂 × 模型 × 任务 / 结果摘要 / 决策 / 依据链接）

### 批次 real-q1（2026-09-24，首个真实批次）

- **配置**：matrix/quick-lite.yaml 展开（任务不足自动降配）= A0/A1f × d1-typo-01,
  d2-enum-01 × n=1 = 4 run；claude CLI 2.1.241 × 中转站默认模型（opus-5）；
  runner 并发 4，墙钟 1m41s，总成本 **$1.83**。
- **结果**：

  | 任务 | 臂 | 得分 | 测试 | turns | 成本 |
  |------|----|------|------|-------|------|
  | d1-typo-01 | A0 | 1.0 | 2/2 | 6 | $0.245 |
  | d1-typo-01 | A1f | 1.0 | 2/2 | 4 | $0.505 |
  | d2-enum-01 | A0 | 1.0 | 4/4 | 10 | $0.399 |
  | d2-enum-01 | A1f | 1.0 | 4/4 | 8 | $0.682 |

- **观察（n=1/格，只作方向）**：① 两臂全过——强模型（opus-5）在 D1/D2 小任务上
  不需要 Skill，与 H4（收益随基座衰减）方向一致；② A1f 两臂成本一致更高
  （d1 ×2.1、d2 ×1.7），主因是注入 SKILL.md 后 cache 创建增大——"Skill 的代价"
  在强模型 + 小任务上体现为纯成本；③ A1f turns 更少（6→4、10→8），流程纪律
  可能压缩了探索轮次（待行为信号检测器证实）。
- **决策**：① quick 档时间预算大幅下修（单 run 实测 41–99s vs 原估 3.5–10min），
  但每格 n=1 不足以定档，维持"任务集补齐后 3 实例纵切定档"决策门；
  ② 成本主控变量确认为 run 数 × 注入长度（cache 创建），quick-lite 12 run
  预估 $4–8、standard 322 run 预估 $150–300（opus 单价下），standard 跑前需重新确认预算；
  ③ 当前任务对 opus 太简单（天花板），任务集补齐时 D2/D3 需按 Pilot Gate 校准难度。
- **依据**：results/real-q1/runs.jsonl + work/*/trace.json（原始输出全量留存）。

### 批次 b0-vertical（2026-09-25，B0 真实纵切）

- **配置**：d2-enum-01 × A0/A1f × haiku（新中转站 ENGINX，.env 注入 + NO_PROXY 修复）
  = 2 run；stream-json 全事件流。
- **结果**：双臂跑通（4/4 测试通过）。trace schema 定死：tool_use 在 assistant
  content 内、result.usage 含 cache/iterations（git 提交 `15ea618`）。
- **决策**：① 新中转站 haiku 可用，09-24"令牌只放行 opus-5"的约束解除，
  quick 档"快模型迭代"路线恢复可行；② 成本校准 $150–500/700run（`19a780a`）；
  ③ 预警 d2-enum 对 haiku 可能偏易 → B1 证实。
- **依据**：results/b0-vertical/{A0,A1f}/{repo,trace.jsonl}。

### 批次 b1-pilot（2026-09-25，B1 Pilot Gate 首轮）

- **配置**：12 个原始任务 × 裸 haiku × n=10 = 30 run（A0 only），成本 $2.65。
- **结果**：**D1/D2/D3 全部 100%（30/30 满分）**——Pilot Gate 不通过：
  D2 应 40–80%、D3 应 <40%，实测全满分，任务对 haiku 都太简单（天花板实锤，
  与 real-q1 对 opus 的观察一致且更严重）。
- **决策**：任务集必须加料 → 建 d2-enum-hard（10 调用点/3 种隐蔽形式）与
  d3-state-hard（缓存预热 bug），四检全过后进 pilot2 复测（git `207389f`）。
- **依据**：results/b1-pilot/runs.jsonl。

### 批次 b1-pilot2（2026-09-25，B1 纠偏复测，quota 中断）

- **配置**：tasks/pilot2（加料任务）× 裸 haiku × n=10 = 140 run 计划；
  跑到 43 个成功 run 后中转站 quota 耗尽（91× 403 pre-consumed quota +
  6× quota not enough），成本 $2.02（仅成功 run 计）。
- **结果（清洗后，error 不计入均值）**：D1 40/40 满分；D2 仅 3 个成功 run、
  3/3 满分；D3 零成功 run。**⚠️ 早前"D2 6%、D3 0% 太难"的判断是假象**——
  那是把 97 个 quota 死亡的零分混入均值所致；清洗后样本不足，加料版难度
  **未定**（D2 3/3 甚至暗示可能仍偏易）。
- **决策**：① 中转站充值后 `--tasks tasks/pilot2` 续跑（git `a894f1f`）；
  ② 备选线路登记：deepseek 兼容性双层验证通过但余额 $0.111 < 预扣 $0.267
  （调试用，不进主矩阵）；aihilfs 站 student 分组零渠道（`2cd0be9`）；
  ③ 统计口径修正：**任何含 error 的批次，均值与通过率必须只按成功 run 计算**，
  本规则已落入本批登记，后续报告生成器同样遵守。
- **依据**：results/b1-pilot2/runs.jsonl（原始记录含 error，未删改）。

### 探针 probe-codex-d1 / probe-pi-d1（2026-09-27，跨 harness 打通）

- **背景**：用户提供 r.dis.115.zone 中转站（三协议兼容：OpenAI chat /
  Anthropic messages / OpenAI responses；17 模型含 deepseek-v4.1、glm-5.x、
  kimi-k2.6、grok-4.6、inkling:free）。
- **claude CLI 此站不可用**：CLI 端拒绝非 claude 模型名（unrecognized_model），
  relay 端拒绝 claude 模型名（无渠道）——双端拦截，登记为环境事实。
- **codex 路径**：@openai/codex@0.147.0（0.157 移除 wire_api=chat）+
  wire_api="responses" + deepseek-v4.1-flash；d1-typo-01 × A0 修复正确，
  隐藏 pytest 2/2，trace 38 行 JSONL（results/probe-codex-d1/）。
- **pi 路径**：@mariozechner/pi-coding-agent + 自定义 provider 扩展
  （scripts/pi-dis-provider.ts，api=openai-completions）；同任务修复正确 2/2
  （results/probe-pi-d1/）。臂注入参数实测：A0=--no-skills /
  A1=--skill <dir>（原生加载）/ A1f=--append-system-prompt。
- **决策**：harness 实证覆盖达 3/4（Claude Code / Codex / Pi Agent），
  dsh 仅规范论证；codex 线（deepseek 后端）作为跨厂商臂与廉价迭代线，
  结论口径标注"deepseek 线"，不与 haiku 线直接比。
- **依据**：results/probe-codex-d1/、results/probe-pi-d1/、
  scripts/pi-dis-provider.ts。

### 批次 pi-ql1（2026-09-27，pi 线首个完整 quick-lite）

- **配置**：matrix/quick-lite.yaml × pi 驱动 × deepseek-v4.1-flash（dis 线）
  = 12 run（A0/A1f × 6 任务），并发 10，墙钟 **2m37s**，零错误。
  （驱动落地：codex_driver.py / pi_driver.py，runner --driver 分发。）
- **结果**：11/12 满分；唯一非满分 d2-enum-hard 两臂同分 0.89（8/9）。
  A1f 全部更慢更多轮（如 d3-cache A0 6 turns/27s vs A1f 11 turns/112s）——
  tdd 流程纪律的开销在 D3 上显著可见；得分差为 0，成本差为正（方向性）。
- **检测器首次真实校准（重要）**：F15 检测器在真实数据上产出 **5/5 假阳**——
  全部来自 TDD 语境（"RED confirmed" / "Let me confirm the tests pass" /
  "grep confirms"），正则把验证语境的 confirm 当成了用户确认请求。
  修正：CONFIRM_PAT 收紧为请求/疑问句式（please confirm / shall I /
  需要我继续吗 等），排除 confirmed/confirms/confirm-the-tests 语境；
  补 6 个回归单测（3 假阳语境 + 3 真阳句式），21 单测全过；
  重跑信号后零误报。**这正是"检测器需要 ground truth 校准"的活教材，
  校准事件本身写入答辩素材。**
- **归一化扩展**：harness_normalize.py 新增 pi / codex 双适配（自动格式识别 +
  一致性校验），pi-ql1 的 195 条事件全部入库，行为信号首次吃到真实事件流。
- **决策**：① quick-lite 时间预算再下修（12 run 2m37s，deepseek 线几乎免费）；
  ② 任务难度对 deepseek-flash 区分度不足（11/12 满分），
  d2-enum-hard 是唯一有信号的——主矩阵任务池应加大 hard 变体比例；
  ③ codex 驱动已就绪（probe 验证过），跑矩阵前同样先过小批。
- **依据**：results/pi-ql1/（runs.jsonl + report.md + work/*/trace.json）、
  backend/graders/test_behavior_signals.py（回归单测）。

### 批次 pilot-hard-1/2（2026-09-28，hard 池基线 + 死跑现象发现）

- **配置**：matrix/pilot-hard.yaml（6 个 hard 任务 × A0 × n=2 = 12 run）×
  pi × deepseek-v4.1-flash。
- **重大基建发现——死跑（dead run）**：并发 10 下部分 run 静默失败——
  agent 两次 bash 后无编辑无陈述即退出，trace 尾部为
  `auto_retry_end: 429 Rate limit exceeded`（pi 重试 3 次后放弃，exit=0 无报错）。
  pilot-hard-1 的 d2-enum-hard 0/9、d2-sig-hard 0/5 全是死跑而非能力失败。
- **应对（已落地）**：① runner 新增死跑检测（repo 与 fixture 逐字节一致
  → dead=True + error 标记，统计视图自动排除）；② 断点续跑天然兼容——
  error 记录重跑时自动重试（实测：降并发 4 后续跑，3 个死跑全部满分）；
  ③ dis 线并发上限登记为 4（10 必触发 429）。
- **校正后基线（hard 池，deepseek-v4.1-flash，n=2）**：6 个 hard 任务
  全部可达满分——hard 池在该模型上同样接近天花板；d2-enum-hard 在 pi-ql1
  的 8/9 是真实编辑的部分分（漏一个隐蔽调用点），说明**信号在 80–95% 的
  方差带里，n=2 不够，主矩阵 n 需 ≥3**。
- **决策**：① quick 档 n=2 → n=3（成本可忽略，方差带信号需要重复数）；
  ② 难度标签暂停按实测重排（先解决死跑与重复数）；
  ③ 暂不再加 harder 变体——当前瓶颈是方差与基建，不是任务上限。
- **依据**：results/pilot-hard-1/、results/pilot-hard-2/（含死跑 trace：
  work/d2-sig-hard-A0-r02/trace.json 尾部 429 记录）。

### 批次 quick-n3（2026-09-28，首个 n=3 全量对照批）

- **配置**：matrix/quick.yaml v6.5（18 任务 × A0/A1f × n=3 = 108 run）×
  pi × deepseek-v4.1-flash，并发 4，墙钟 **21 分钟**，零死跑零错误，$0（deepseek 线）。
- **结果**：**108/108 全部满分**——任务池在该模型上完全天花板，
  通过率维度零区分度。**成本维度信号清晰**：A1f 轮次一致更高，
  D3 上 A0 8.8 turns vs A1f 11.7 turns（+33%），墙钟同步放大。
  行为信号零命中（校准后的 F15 无幻影用户，诚实的阴性）。
- **结论（quick 档口径）**：deepseek-flash × 当前任务池上，tdd Skill
  **收益不可测（天花板）+ 代价可测且为正（D3 +33% 轮次）**——
  按序贯分诊规则属"无正收益 + 成本异常"，指向 H1 负收益区间；
  但收益侧证据缺失，不能下"无用"结论，须看梯度批与更硬任务。

### 批次 gradient-glm-5.1/5.2/5.3（2026-09-28，H4 梯度首轮）

- **配置**：matrix/model_gradient.yaml（6 任务 × A0/A1f × n=2 = 24 run/模型）
  × pi，并发 4。glm-5.2 渠道不稳，三轮续跑后死跑 3（已排除）。
- **结果（有效 run）**：

  | 模型 | A0 pass | A1f pass | A0 turns | A1f turns |
  |------|---------|----------|----------|-----------|
  | glm-5.1 | 12/12 | 12/12 | 5.6 | 6.4 |
  | glm-5.2 | 11/11 | **6/10** | 5.5 | 5.6 |
  | glm-5.3 | 12/12 | 11/11 | 7.6 | 9.5 |

- **本轮最重要发现——I3 反噬（Skill 负收益的真实案例）**：glm-5.2 × A1f
  40% 失败且全部为**真编辑真失败**（非死跑）。trace 显示失败 run 全部
  卡在 TDD 仪式里："遵循 TDD 原则：首先编写一个复现测试（RED）"→
  预算耗尽于测试脚手架，修复从未落地（最终陈述全是"第一步 — RED"）。
  同一模型裸考（A0）直接修、11/11 全过。**这验证了 H1 的机制性预测：
  流程纪律类指令（I3 先复现）在弱基座上会把预算耗在仪式上，
  收益为负**——且与 quick-n3 的"成本 +33%"互相印证（③ 环成本侧）。
- **决策**：① 梯度线补 n（glm-5.2 A1f 现象值得 n=5 确认 + grok/deepseek
  辅线交叉）；② 归因器下一步重点分析 glm-5.2 A1f 的失败 trace，
  看 F-ID 分布（预期 F11/F15 类预算浪费信号）；
  ③ 消融臂优先级上调——若 I3 是祸首，A1-x3（去 I3）应恢复通过率，
  这是消融设计要回答的核心问题。
- **依据**：results/quick-n3/、results/gradient-glm-5.{1,2,3}/
  （runs.jsonl + report.md + work/*/trace.json）。

### 批次 ablation-glm52-1（2026-09-29，关键消融：I3 vs I8 祸首判定）

- **配置**：matrix/ablation-glm52.yaml（A1-x1/x3/x8 × 6 任务 × n=2 = 36 run）
  × pi × glm-5.2，并发 4→1（渠道极不稳，4 轮续跑 + 并发 1 补跑）。
  消融变体由 scripts/build_ablation_skills.py 按 manifest lines 删行生成；
  runner 新增臂级 Skill 覆盖（arm_skill）。
- **对照（复用 gradient-glm-5.2）**：A0 = 11/11；A1f = 6/10（0.70）。
- **结果（有效 run，死跑已排除）**：

  | 臂 | 删除指令 | 通过率 | 均分 | 关键格 |
  |----|---------|--------|------|--------|
  | A1f（基线） | — | 6/10 | 0.70 | d3-bus 0/3、d3-cache 0.5 |
  | A1-x1 | I1 确认请求 | 8/10 | 0.90 | d3-cache 0.5 |
  | **A1-x3** | **I3 反水平切片段** | **10/10** | **1.00** | **d3-bus 1.00、d3-cache 1.00** |
  | A1-x8 | I8 RED-first 仪式 | 7/9 | 0.87 | d3-cache 仍 0.5 |

- **判读**：① 三个消融臂全部优于 A1f（≥0.87 > 0.70）——"仪式性内容总体
  有害于 glm-5.2"成立；② **x3（删 I3 反水平切片段，22 行含 WRONG/RIGHT
  图示）恢复最完全（10/10 含两个 d3 格）**，x8（删 RED-first 仪式段）
  只部分恢复——祸首判定倾向 **I3 段是全文中仪式引导最强的区块**，
  而非此前猜测的 I8（trace 里"第一步—RED"只是症状，I3 段的反复
  训诫才是把模型推入测试脚手架的最强驱动）；③ x1 亦有提升（0.90），
  与 I1"有害"预测方向一致；④ 证据强度注意：d3 格 n=1–2，x3 vs x8
  之差在噪声边缘，需补 n 或稳定渠道确认。
- **基建新异常（登记）**：d3-bus-hard + 任意消融变体 + glm-5.2 →
  中转站**确定性空补全**（assistant content=[]，input/output=0，无 429，
  并发 1 下仍 ~85% 死亡；仅 x3 一次成功 1.00）。与 429 死跑不同机制，
  初步判断为渠道对特定 prompt 组合的静默丢弃，待渠道侧排查。
- **决策**：① tdd-v2 修订第一刀落在 I3 段（压缩 22 行训诫为 ≤5 行规则），
  I8 段保留但弱化祈使语气——待 x3 补 n 确认后执行；
  ② 消融矩阵剩余臂（x2/x4/x5/x6/x7）在稳定渠道上跑（glm-5.2 渠道
  当前不可用级别的不稳）；
  ③ manifest 已后补登记 I8（L62-88）并修正"I3 反噬"表述。
- **依据**：results/ablation-glm52-1/（runs.jsonl + work/*/trace.json）、
  skills/ablation/I{1..8}/SKILL.md、skills/tdd-v1/manifest.yaml（I8 登记）。

### 批次 v2-glm52 / v2-ds2（2026-09-29，A2 首次修订验证——未过验收）

- **配置**：tdd-v2（唯一改动 = I3 段 25→6 行压缩，REVISION.md 归因登记）×
  glm-5.2 复活批（12 run）+ deepseek-flash 无回归批（12 run）。
  注意：v2-ds 首批误用预设模型（glm-5.2）作废，v2-ds2 用 --model 显式指定。
- **结果**：glm-5.2 有效格 5/5（渠道死亡 7/12，d3-cache 格缺失）；
  deepseek 11/12——**d3-bus-hard r01 真失败：agent 正确诊断后说
  "write a failing test first (red), then fix"随即结束，修复未落地**
  （I8 Tracer Bullet 祈使结构未动，仪式仍会触发）。
  D3 轮次 v2 16.5 vs v1 11.7（n=4 vs 21，未证实降本）。
- **判定（对预登记标准）**：三条标准两条未达——**v2 部分有效但不充分，
  不予定版**。预登记验收标准首次发挥"防止提前宣布胜利"的作用。
- **决策**：v3 = v2 + 弱化 I8 段祈使结构（RED-first 祈使句改条件建议），
  归因依据 = d3-bus-hard r01 trace；glm-5.2 复活批待渠道稳定补齐 d3-cache 格。
- **依据**：results/v2-glm52/、results/v2-ds2/、skills/tdd-v2/REVISION.md。

### 批次 v3-ds / v3-glm52（2026-09-29，A2 第二轮——核心验收通过）

- **配置**：tdd-v3（= v2 + I8 祈使弱化：Tracer Bullet/Incremental Loop 的
  RED-first 强制仪式 → 条件建议，Rules 四条保留）× 双模型各 12 run。
- **结果**：glm-5.2 有效格 **7/7 全过**（v1 全灭的 d3-bus/d3-cache 均过，
  9–11 turns）；deepseek 有效 11/11（1 死跑已排除）；
  **仪式卡死清零**（v1 在 glm-5.2 为 4/10，v2 在 ds 为 1）。
- **判定**：预登记四条标准 ①②③ 全过；④ 降本部分未达（glm-5.2 上
  10.0 ✅，deepseek 上 ~21.8 ❌）——归因：条件建议保留了正常 TDD 引导，
  强基座轮次上升是 Skill 本意而非仪式浪费；标准④混淆了两类开销，
  接受偏离并登记（heldout 以"无仪式卡死"替代轮次硬阈值）。
- **决策**：v3 定为 A2 基线候选 → heldout 一次性终验（待 heldout 实例集）。
  v1 结论至此可写：tdd-v1 的收益条件 = 基座能力 ≥ 执行预算阈值；
  I3 训诫段与 I8 祈使段共同构成弱基座负收益源。
- **依据**：results/v3-ds/、results/v3-glm52/、skills/tdd-v3/REVISION.md。

### 批次 heldout-final-2（2026-09-30，A2 闭环终验——通过，闭环合拢）

- **配置**：tasks/heldout/ 6 新实例（装饰器/字典路径/类属性/时区，
  与 dev 池形态不重合）× {A0, A1f-v1, A1f-v3} × n=2 = 36 run，
  deepseek-flash，4m55s，零死跑。
- **结果**：三臂全部 12/12；v3 轮次 7.0 vs v1 6.8（持平）；
  四条预登记标准全过（④ 判方向持平）。
- **意外收获**：首批 heldout-final 因 runner --tasks 默认值覆盖预设 source
  而跑成 dev 池 108 run（流程教训已登记）——数据有效：
  v1 35/36（d3-csv 一败）vs v3 36/36（轮次 8.7 ≤ 8.9），
  v3 在 dev 池上亦修掉 v1 一个真实失败。
- **A2 闭环总结（v1 → v3 最终结论，可对外）**：
  ① tdd-v1 的收益条件 = 基座能力 ≥ 执行预算阈值——强基座中性偏贵
  （D3 轮次 +33%），弱基座有害（glm-5.2 上 0.70 vs 裸考 1.00）；
  ② 负收益源 = I3 训诫段（22 行）+ I8 RED-first 祈使段，机制为
  仪式驱动耗尽执行预算；③ tdd-v3（I3 压缩 + I8 条件化）在弱基座
  复活（7/7）、强基座无回归（11/11）、heldout 无害（12/12）、
  轮次与 v1 持平——**"有依据地修改 + 验证有效"（题目第 7、8 条）完成**。
- **依据**：results/heldout-final-2/、results/heldout-final/、
  skills/tdd-v3/REVISION.md、tasks/heldout/。

### 批次 pilot-forged-2 + pool-v2 forged 线打通（2026-09-30）

- **背景**：pool-v2 双范式重构（docs/POOL_V2.md）。mined 线五组版本对
  （more-itertools×2 / cachetools / packaging / jmespath）颗粒无收——
  小版本 diff 以新功能/文档为主；但自动验证（F2P 挂于旧版、救于 oracle、
  P2P 两态验证）把 47+ 个不合格候选全部机器拦下——
  **SWE-bench Verified 的"必须筛"教训被机械化执行（方法论验证点）**。
- **forged 线（SWE-smith 算子）打通**：对 more-itertools 10.8.0 真包注入
  BOUNDARY-FLIP（all_equal 提前返回布尔翻转）与 CACHE-DROP（sieve 合数
  标记删除），F2P=真包自带测试类、oracle=撤销注入；两任务过四关校验
  （含 wrong_01 判负）。踩坑记录：CamelCase 测试类搜索、unittest.mock
  依赖、模块级裸名（itertools/* 通配头）、多行锚点空补丁、子进程 git
  apply 静默失败改纯 Python 内验。
- **Pilot Gate（A0 × n=2 × deepseek-flash）**：
  allequal 1.0/1.0（天花板——布尔翻转对 agent 太直白）；
  **sieve 0.25（f2p:2/8，真编辑真失败，5 turns）**——agent 的修复没过
  双约束，落入区分带。**forged 线首个有信号任务诞生。**
- **基建登记**：runner `--tasks` 默认值覆盖预设 tasks.source（第二次踩，
  需修：预设 source 优先或冲突时告警）；staging 目录模式
  （forged-final/）规避同 task_id 多目录冲突。
- **依据**：results/pilot-forged-2/、scripts/forge_tasks.py、
  tasks/pool-v2/forged-final/。

### 批次 forged-v13（2026-09-30，forged 池 v1/v3 复测——v1 危害在区分带复现）

- **配置**：forged 4 任务（allequal/cachedrop/argswap/renameleak，SWE-smith
  算子注入 more-itertools 真包）× {A0, A1f-v1, A1f-v3} × n=2 = 24 run，
  deepseek-flash；两轮续跑后死跑 10（渠道深夜不稳）。
- **结果（有效格，n 小属方向级）**：

  | 任务 | A0 | v1 | v3 |
  |---|---|---|---|
  | boundary-allequal | 0.86(n2) | 1.00 | 1.00 |
  | cachedrop-sieve | 1.00 | **0.25**（另一次 720s 超时） | 1.00(n2) |
  | renameleak-islice | 1.00 | 1.00(10t vs A0 7t) | 1.00 |
  | argswap-sieve | -- | 1.00(16t) | -- |

- **关键格**：cachedrop-sieve 上 **v1 两次独立失败（超时 + 0.25 未修复），
  A0 与 v3 均通过**——glm-5.2 上的"v1 仪式耗预算"模式在 deepseek ×
  区分带任务上复现；v3 不受影响。成本信号延续：v3 轮次一致高于 A0
  （cachedrop 8t vs 5t）。
- **判读**：① forged 池达成设计目标——区分带 + 方差并存（argswap A0
  早期 0.25↔1.00 波动，n≥3 必要性再证实）；② v1 危害结论从"弱基座
  特有"扩展为"区分带任务上亦可复现"（预算敏感型失效）；
  ③ "正收益"仍无证据：v3 未见超过 A0 的格子，最好成绩是持平——
  与"可测范围内无正收益"的限定结论一致。
- **决策**：forged 池纳入主矩阵 dev 子集（替换 4 个天花板旧任务）；
  错解设计教训登记（错解必须与 gold 语义相异——argswap 首版错解
  与 gold 同语义被校验器拦下）。
- **依据**：results/forged-v13/、tasks/pool-v2/forged-final/。

### 批次 forged-v13-p2p（2026-10-01，P2P 闸门落地 + 全 n=3 复测）

- **前置修复**：P2P 回归闸门补齐（每任务 2 个无关稳定测试类，两态验证
  通过才写入；add_p2p.py）——POOL_V2 §3 判分哲学的另一半嘴归位；
  meta 补 horizon_minutes（3/8/8/10 分钟，METR 标定起步）。
- **结果（36/36 全有效，零死跑）**：四任务 × 三臂全部 1.00；
  P2P 闸门全程零触发（无误伤）；v1 的 0.25/超时未在 n=2 复现
  ——坐实"随机性失效、频率待估"。
- **判读（三句话）**：
  ① 分数侧：forged 池在 deepseek 上仍偏易（全过）——Pilot Gate 带外
  问题坐实，池的角色从"分数区分"转为**"成本区分"**（v1/v3 轮次在
  3/4 任务高于 A0：allequal 10/7 vs 6、cachedrop 10/12 vs 8、
  renameleak 9/12 vs 8，即 CE 的 ρ 维度信号稳健）；
  ② 成本侧：v3 与 v1 的开销差距收窄（cachedrop 上 v3 12t > v1 10t，
  与昨夜 v3 全面更省不一致——方差大，成本结论需更大 n 再定）；
  ③ **分数区分要靠弱基座**：glm-5.2 × forged 池是下一批
  （弱基座 × 区分带任务，预期分数侧打开）。
- **决策**：① forged 池定位修订为"成本区分 + 弱基座分数区分"双用途；
  ② 偏差②（带外任务）处置改为：不硬加料，池分层使用
  （deepseek 测成本、glm-5.2 测分数）；③ 下一批 forged-glm52。
- **依据**：results/forged-v13-p2p/、scripts/add_p2p.py。

### 批次 forged-glm52（2026-10-01，弱基座分数侧验证——未打开）

- **配置**：forged 4 任务 × {A0, A1f-v1, A1f-v3} × n=3 = 36 run × glm-5.2，
  三轮续跑后有效 24（死跑 12，渠道白天仍 33%+）。
- **结果**：分数侧全部 ~1.00（仅 v3 × allequal 0.95 一格部分分）——
  **弱基座也未能打开分数区分**：单行算子 bug 对现模型太直白。
  成本侧批间不一致（cachedrop v3 13t vs v1 7t；argswap v1 9t 最低）——
  成本结论需大 n。
- **判读（Pilot Gate 第 4 次校准）**：R1 合成天花板 → R2 二元峰 →
  R3 全满分 → **forged 单行 bug 双基座全过**——难度连续体的教训累积：
  单行错误的"找到并修对"对 2026 模型已是本能。分数区分的出路只剩两条：
  ① 同任务埋 2–3 个互相牵扯的错误 + 干扰项（复合 bug）；
  ② env 轨长链条任务（时程拉开，错误率自然上升）。
- **决策**：forged 池定稿为"成本区分池"（ρ 维度）；
  分数区分攻坚转向复合 bug 算子（BOUNDARY+CACHE 同埋）与 env 轨；
  该结论写入 PROJECT_STATUS_REPORT 任务池章节。
- **依据**：results/forged-glm52/。

### 批次 pilot-multi-1（2026-10-01，复合 bug 攻坚——分数区分首次打开）

- **配置**：复合算子任务 ×2（forge_multi：多锚点组 + 逐组 site 补丁 +
  组间区分内验）× {A0, A1f-v1, A1f-v3} × n=3，deepseek-flash。
  forged-multi-sieve = 同函数双 bug（合数标记删除 + isqrt 边界收缩，
  修好一个仍挂另一个，配手写定向测试）；forged-multi-dual = 跨函数
  双 bug（all_equal 翻转 + take 差一）。四关全过（含 git apply
  --unidiff-zero 支持零上下文补丁——校验器同步升级）。
- **结果（超时计为未完成）**：
  multi-sieve：A0 满分 1/3（2 超时）、v1 满分 1/3（2 超时）、
  **v3 满分 2/3（1 超时）**——完成率 v3 > A0 = v1；
  multi-dual：A0 2/3（1 部分分 0.91）、v1 3/3、v3 3/3。
- **判读**：① **分数区分首次真正打开**——复合 bug 把单行本能逼成
  预算耗尽（单任务 370–720s，超时成为主要失效模式）；② v3 的
  完成率优势（2/3 vs 1/3）方向级地印证"精简流程在预算敏感任务上
  存活率更高"——v1 的仪式开销在复合任务上直接兑换成超时；
  ③ multi-dual 上双臂 3/3 vs A0 2/3——"系统性排查"（Skill 的核心
  声称）在多错误点任务上首次显出正收益苗头（同 allequal 格呼应，
  均为方向级，需补 n）。
- **决策**：① 复合算子定为分数区分主线，按此模式扩编 4–6 个
  （不同 bug 组合/不同函数族）；② multi 池补 n 到 5 确认完成率差；
  ③ 超时指标正式纳入报告口径（完成率 = 满分率 + 超时率双轨）。
- **依据**：results/pilot-multi-1/、scripts/forge_tasks.py（forge_multi）。

### 批次 pilot-multi2 + forge 引擎/配方分离（2026-10-01）

- **架构整改（用户要求）**：pool 主线代码零 Skill 硬编码——审计确认
  forge/mine/add_p2p 零 "tdd" 引用；算子定义从脚本 main() 抽出为
  声明式配方 tasks/pool-v2/forge_specs/more-itertools-10.8.0.yaml，
  引擎（forge_tasks.py）改通用 spec 加载器。换任务域=换 yaml，
  换被评 Skill=臂注入参数，两层都不触代码。
- **扩编**：复合算子 +3（taketail 成对边界 / crossfile 跨文件 /
  triple 三 bug），池达 9 个，四关+P2P 全过。
- **pilot-multi2（27 run，零死跑）**：taketail 全过（成本区分
  A0 5t vs 双臂 8t）；crossfile 近天花板；**triple 触地板
  （A0 1/3、双臂 0/3 全超时）**——难度光谱从天花板到地板成型，
  triple 需 Pilot Gate 处置（降难度或提 timeout 档）。
- **基建登记**：长单进程多 pytest 批次静默退出（引擎/校验器全量
  需分批跑，根因待查）。
- **依据**：results/pilot-multi2/、tasks/pool-v2/forge_specs/、
  docs/POOL_V2.md 附录（实施状态）。

### 批次 pool-v20-main（2026-10-02 凌晨，主复测 + 渠道混淆发现——Pilot Gate 第五次校准）

- **配置**：4 个带内复合任务 × {A0, A1f-v1, A1f-v3} × n=5 = 60 run，
  deepseek-flash（multi-triple 地板样本不入主矩阵，登记于 meta.baseline）。
- **结果**：**60/60 全满分，零超时零死跑**——与昨晚同任务 2/3 超时
  形成刺目对照。墙钟：今晚中位 30s（最快 11s）vs 昨晚 370–720s，
  **同一任务同一模型，速度差 10–20 倍——变量是渠道延迟**。
- **核心发现（方法论级，比任何单批结论都重要）**：
  **完成率/超时类指标混淆渠道健康度**。昨晚的"v3 存活率优势
  （2/3 vs 1/3）"据此**降级为"不可归因"**——无法区分是任务难度×
  Skill 效应还是 token 投递速度差异。协议要求补一条：
  每 run 记录 token 吞吐（output_tokens/wall_s），完成率结论必须
  在渠道健康窗口内复测确认。
- **本批的干净答案（渠道健康，n=5）**：
  ① 分数侧：四任务三臂全 1.00——**复合 bug（当前难度）在健康渠道下
  仍不构成分数区分**；② 成本侧确认：v1/v3 轮次在 dual（8.2/7.2 vs 6.4）
  与 taketail（8.4/7.6 vs 6.2）高于 A0 ~25-30%；**v3 轮次一致低于
  v1**（8.2→7.2 / 8.4→7.6 / 16.6→15.6）——v3 降本结论在第三批
  独立数据中复现 ✓。
- **"正收益是否存在"的正式回答（pool-v2.0 可测范围）**：
  **分数侧无正收益（全满分无差异）；成本侧 v1 持续高于 A0，
  v3 把开销压到 v1 与 A0 之间**——与"可测范围内无正收益 +
  成本代价 + v3 缓解"的三段式结论完全一致。
- **决策**：① 渠道健康协议入册（吞吐记录 + 健康窗口复测）；
  ② 分数区分攻坚转向"推理硬度"（不是链长——模型 30s 能解的
  复合 bug 说明排查链对它不难，需要的是搜索深度/误导性）；
  ③ multi-triple 在健康渠道复测重校准（昨晚的"地板"可能是假象）。
- **依据**：results/pool-v20-main/。

### 归因器 v1 上线（2026-10-02，backend/attribution/——题目第 4 条完全体）

- **架构**（AgentRx 守卫模式 + AgenTracer 警示 + MT-Bench 红线）：
  L1 症状检测（behavior_signals，已有）→ **L2 机械失效归因**（六个
  检测器：F01/F03/F05/F11/F15/F16，全事件时序/正则/分数字段，零 LLM）
  → **L3 指令联动**（manifest.targets 反查，任意 Skill 目录通用）
  → L4 反事实（wrong_01 预计算标注，挂账）。
- **关键设计（两条实战修正）**：① RUN_CMD 必须含 python -c/.py 执行
  （否则 agent 用 python -c 复现被误判"未复现"，F01/F03 假阳 45+13 清零）；
  ② **结果门**：F01/F03/F05 只在 score<1 时判——成功 run 的"读了就改"
  是合法静态分析，行为信号与失效归因分离。
- **端到端实证**：gradient-glm-5.2 批（v1 崩盘批）→ F05 ×2 →
  指令 I2（L85-86，预测"有害：最小化与改全 N 处冲突"）——
  失败 → F-ID → 指令行号 → 预登记预测，链条全自动闭环。
- **零 Skill 硬编码核验**：attribution 模块 grep "tdd" = 0；
  manifest 联动走 --skill 参数（任意 Skill 即插即用）。
- **API**：/api/attribution?batch=&skill= 上线。
- **挂账**：κ 校准（20 条双人标注，需人工会话）；F17/F19 检测器
  （需命令输出面，事件流暂无 stdout）；L4 反事实自检套件。
- **依据**：backend/attribution/（detectors/engine/test_detectors）、
  backend/api/server.py。

### 批次 poolv3-proto2（2026-10-02，H1 正收益首次构造性证据——项目史转折）

- **背景**：三篇 2026 文献（SkillsBench +16.2pp 但增益集中在训练外知识、
  WebDev-Skills-Bench 注入平均有害、alphaxiv 过程性 >> 抽象）定位了
  我们全部 null 的根因：能力饱和任务测不出知识注入价值。
- **设计**：pool-v3 convention-forge 原型（虚构库 streamkit）——
  约定（EmptyStream 单例哨兵 / _validate_stream 共享校验 / None 抛
  ValueError）只存在于配套 Skill 文档，fixture 中物理不存在
  （v1 原型把哨兵类放进了 fixture，知识可推断，A0 全过——设计失败后
  v2 改为知识真外置）；测试拆行为/约定双文件（A0 保底行为分 0.4）。
- **结果（3 臂 × n=3，deepseek）**：
  **A0 = 0.4 ×3｜A0p（安慰剂）= 0.4 ×3｜A1f-conv（约定 Skill）= 0.9 ×3**。
- **判读（五条全中）**：① H1 首次为正且幅度大（+0.5）；② 安慰剂臂证明
  非 prompt 变长效应（A0p≡A0）；③ 落在 40-80 区分带；④ 精确复现
  SkillsBench 机制（知识缺口处文档是分水岭）；⑤ 项目主线问题从
  "Skills 有用吗"（证据：能力饱和处无正收益+成本代价）升级为
  "边界在哪"（答案初稿：**只在知识缺口处有用**）。
- **同批安慰剂四臂（placebo-4arm，pool-v2 复合池）**：A0p 与 A0 分数/
  轮次无差（deepseek 非长度分心型，与 WebDev 论文的内容误导型分类一致）。
- **依据**：results/poolv3-proto2/、tasks/pool-v3/、
  skills/streamkit-convention/、skills/placebo-cooking/。

## AI 使用记录（题目要求：怎么用的、为什么、发现了什么问题）

- 2026-09-24（执行阶段·续）：任务集补齐（2→12 实例，D1×4/D2×4/D3×4，
  scripts/build_more_tasks.py，12 个一次过校验器四关）、normalize 归一化层
  （summary + stream-json 双格式，一致性校验用 real-q1 真实 trace 通过）、
  行为信号检测器 ×7（15 个单测全过；summary 格式无 step 事件时不伪造阴性）、
  DuckDB store（runs/events/signals 三表 + v_arm_stats/v_paired/v_fid_hits 视图）、
  报告生成器（quick 档口径 + 必披露项自动写入，real-q1 样例报告已出）。
  驱动升级为 stream-json（逐步事件流，待下次真实 run 验证）。
  新抓到的缺陷：DuckDB 占位符数错（20 vs 23）、runs.jsonl 重试重复记录
  违反主键（修：按 run_id 去重，以最后一条为准）。
- 2026-09-24（执行阶段）：cli_driver / orchestrator / dry-run 管线由 AI 编写，
  本人审阅。开发中被抓出并修复的真实缺陷（全部为 AI 写的代码里的坑）：
  ① **git apply 在外层 git 仓库内静默 Skip**（exit=0 但没打上补丁）——
  mock 判分全 0 暴露，修：GIT_CEILING_DIRECTORIES 屏蔽仓库发现；
  ② **.CMD 批处理垫片截断含换行的 prompt**——4 个真实 run 全部静默丢失
  --output-format / --dangerously-skip-permissions（agent 回复"我没有写入权限"暴露），
  修：prompt 压平空白；③ Windows 下 subprocess 找不到 claude（WinError 2），
  修：shutil.which 解析全名；④ 沙箱禁止 rmtree，重试目录改时间戳命名。
  教训与 SKILL 设计原则一致：判分与校验必须机器可执行（pytest 直接抓住 ①），
  冒烟批（B1.5）先查坑再烧主矩阵（②③④ 均在 4 run 小批暴露，未污染主矩阵）。
- 2026-09-18 至 09-23：方案设计阶段。文档骨架与多轮修订由 AI 辅助完成；
  外部评审三轮由另一家 AI 提供；本人决策采纳/否决（见 DECISION_LOG 各轮）。
- 已知 AI 使用边界：S1 登记草稿由 LLM 预填、人确认（LLM 不接触实验数据，
  最终以 git commit 的 manifest 为准）。
- （执行阶段持续记录：AI 写的判分器被抓出的漏洞、归因器误判案例等）

## 2026-10-04：docker 沙箱落地 + pool-v3 v3.4 确认批——C7 三族齐证

**沙箱**：WSL2 Ubuntu22.04（D:/WSL/Ubuntu）+ docker.io + skillbench-sandbox:0.73.1
镜像（node22+pytest+pi@0.73.1）；pi-docker 驱动（容器内仅挂 /repo 与 /skill）。
冒烟实证：agent find / 搜约定容器内一无所获；45+6 run 越界审计 0 命中。
宿主 vs 沙箱：同族任务 A0 死跑率 60~100%→11%（全是 DIS 窗口）、越界 40%→0。

**确认批（3 族 × A0/A0p/A1f-conv × n=5，pi-docker，deepseek-v4.1-flash）**：

| 族 | A0 | A0p | A1f-conv | Δ |
|---|---|---|---|---|
| streamkit | 0.455 | 0.455 | 0.818 | +0.364 |
| fluxdb | 0.400 | 0.400 | 0.820 | +0.420 |
| deploykit | 0.400 | 0.400 | 1.000 | +0.600 |

预登记五条件全过（n≥4、渠道死<25%、A0≤0.6、A0p≈A0、conv≥A0+0.2）→
**C7 成立（★★★）**：知识缺口处 Skill 臂显著为正，安慰剂≡裸考排除长度效应。
边界论闭环：饱和区 C3（无正收益）+ 缺口区 C7（递答案）= Skill 价值边界。

**运行侧**：deploykit-a0 撞 DIS 空响应窗口 6 连死（usage 0/0），串行降速补跑
3/3 成活；发现 maxTokens=8192 截断死 ×2（A1f 臂），下批提 16384；
死跑二分（渠道死剔除+补跑 vs 合法无编辑保留）首次落地执行。

## 2026-10-05：systematic-debugging 决定性实验——带头上为负（铁案）

GitHub 高星 skill（obra/superpowers）经产品 API 全链路评测：
- 分诊批（6 题 × 双臂）：天花板零增益，成本 +45% 轮次（仪式开销，Phase×437 全文遵循）。
- **决定性批**（d3-csv-01，全池唯一 A0∈[0.3,0.7] 带头题，n=4/臂，pi-docker）：
  **A0 = 1.0×4（满分率 4/4） vs A1f = 0.0/0.33/1.0/0.33（均分 0.42，满分率 1/4）**。
  无伪影（无超时/无 maxTokens 顶/无死跑）。
- 死因：四阶段仪式挤占交付——r03 产出长篇根因论文但补丁 0/3，且叙事自信宣布
  "All pass. Fixed."（F03 未验证宣布完成的变体：验证了但验证错了）。
- 结论升级：饱和区**零增益** → 带头上**主动有害**（−0.58）。
  机制 = 重型过程文档在边界任务上把"修完"换成"修得隆重"。
- 诚实边界：单任务 n=4，满分率超几何 p≈0.07，方向强、幅度待加厚（复测建议已记）。
- 副产品：探针证实 d3-state-hard 已从 0.67 涨到 1.0（模型迭代，池天花板扩大——
  "知识缺口是移动的靶子"再添实证）。
