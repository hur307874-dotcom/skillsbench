# POOL_V2 — 任务池 v2 设计（SWE-bench × Terminal-Bench 双范式）

> 版本：2026-09-30 | 状态：设计定稿（待实施）  
> 上游依据：SWE-bench（F2P/P2P 判分 + Verified 筛选教训）、Terminal-Bench  
> （环境即任务）、SWE-smith（机械破坏批量造虫）、METR（时程难度标定）。  
> 解决的问题：pool-v1 天花板（quick-n3 108/108，收益侧不可测量）。



---

## 1. 双轨架构

```
tasks/pool-v2/
├── code/                  # 轨道 A：代码任务（SWE-bench 范式）
│   ├── mined/             #   真实挖掘（PyPI 版本对 bugfix）
│   ├── forged/            #   机械破坏（SWE-smith 算子注入真包）
│   └── synthetic/         #   合成精选（pool-v1 中有区分度的幸存者）
└── env/                   # 轨道 B：环境任务（Terminal-Bench 范式）
    ├── service/           #   "把服务起起来"类
    └── config/            #   "修通配置/管线"类
```

- **轨道 A 判分**：F2P/P2P 双测试集（pytest，判分纯函数不变）；
- **轨道 B 判分**：`verify.sh` 终态断言协议（机器执行，exit code + 组合断言）；
- 两轨共用：四关校验、Pilot Gate、DuckDB、报告器、臂注入——**runner 零改动**。

## 2. 任务解剖 v2（对比 v1）

```
<task_id>/
├── fixture/               # 考生看到的（不变）
├── solution/oracle.patch  # gold（原 solution/sites/ 合并为单补丁，多站点仍允许多文件）
├── tests/
│   ├── f2p/               # FAIL_TO_PASS：fixture 上必须挂、oracle 后必须过
│   │   └── test_*.py      #   → 部分分来源（N 个独立测试点）
│   └── p2p/               # PASS_TO_PASS：fixture 上就过、oracle 后不许挂
│       └── test_*.py      #   → 回归闸门（全过才算分，见 §3）
├── wrong/wrong_01/        # 预置错解（不变）
├── meta.yaml              # 新字段见 §4
└── INTENT.md              # 不变
```

与 v1 的差异：tests 拆 F2P/P2P 两目录；oracle 统一命名；  
`wrong/` 依然必须判负（判负标准 = F2P 至少挂一个 **或** P2P 挂一个）。

## 3. 判分规则（纯函数，SWE-bench 对齐 + 部分分扩展）

```
resolve = (f2p_passed == f2p_total) AND (p2p_passed == p2p_total)   # SWE-bench 原义，二元
score   = (f2p_passed / f2p_total) × (1 if p2p_passed == p2p_total else 0)
        # 部分分扩展：P2P 是闸门（回归=0），F2P 通过率为分
```

- **P2P 为闸门**：破坏既有行为一票否决（对应我们"修 A 破 B 必死"的双约束传统）；
- **F2P 为刻度**：每任务 5–20 个独立 F2P 测试点，天然落在 0.3–0.9 的连续带——  
  这是天花板问题的直接解法；
- `tests` 字段在 runs.jsonl 扩展为 `f2p: x/y, p2p: z/z`，报告器同步。

## 4. meta.yaml v2

```yaml
task_id: mi-runningmedian-1101
track: code                 # code | env
difficulty: D2              # 类别标签（保留，兼容旧报告）
horizon_minutes: 8          # 【新】人估完成时长（METR 标定，±50% 容忍）
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  （用户视角的症状描述，不泄露根因与修法）
baseline: {}                # 【新】Pilot Gate 回填：{model: f2p_resolve_rate}
```

## 5. 轨道 A 挖掘管线升级（在现有 miner 上改）

```
PyPI 版本对 diff
  → hunk 分类（bugfix / feature / unknown）
  → 【新】F2P/P2P 自动分离：
      F2P = 新版相关测试中「在旧版上执行失败」的测试函数（逐个实跑判定）
      P2P = 同文件中「新旧两版都过」的测试函数（采样 3-5 个，回归闸门）
  → oracle = bugfix hunk 补丁
  → 四关校验（升级：② gold 跑通 = F2P 全过 AND P2P 全过；
              ④ 逐处覆盖改为 F2P 逐测试点回退验证）
  → Pilot Gate（A0 × deepseek-flash × n=3，resolve_rate ∈ [0.4, 0.8] 准入）
```

**SWE-smith 破坏算子**（forged 线批量上量，对真实包注入）：

| 算子            | 例子                     | 狙击       |
| ------------- | ---------------------- | -------- |
| RENAME-LEAK   | 函数改名但留一处调用不改           | F05 漏改   |
| BOUNDARY-FLIP | `<=` → `<`、off-by-one  | F17 基础   |
| CACHE-DROP    | 删除一行失效/刷新调用            | F01 状态污染 |
| ARG-SWAP      | 交换同类型相邻参数              | 表象误导     |
| ALIAS-HIDE    | 把调用点改成别名/partial/再导出形式 | F05 枚举纪律 |

每个算子产出 = 被破坏的真包 + 撤销破坏的 oracle + 用真包既有测试  
（自动分出 F2P/P2P）。**这是 pool-v2 上量的主力**（目标 20+ 任务）。

## 6. 轨道 B 环境任务（Terminal-Bench 范式）

### verify.sh 协议（机器判分，纯 bash/python 断言组合）

```bash
#!/usr/bin/env bash
# verify.sh：终态断言，全部机械判定；exit 0 = 全过
set -e
curl -sf http://localhost:8321/health | grep -q '"status":"ok"'   # 服务存活
curl -sf http://localhost:8321/api/users/1 | grep -q '"timeout":30'  # 行为正确
! curl -sf http://localhost:8321/api/legacy                          # 旧端点已下线
python3 -c "import json; d=json.load(open('out/report.json')); assert d['rows']==42"
```

### 首批 4 个任务设计（docker 恢复前可用 tempdir+子进程实现 lite 版）

| 任务                | 环境             | 目标终态                     | 狙击                 |
| ----------------- | -------------- | ------------------------ | ------------------ |
| env-svc-retry-01  | flask 应用 + 坏配置 | /health 200 + 重试策略生效     | 配置文件多点迁移           |
| env-svc-cache-01  | 缓存层服务          | 写入后读取为新值 AND 命中率>0       | 双约束（同 d3-cache 语义） |
| env-pipe-build-01 | 构建脚本链          | make all 成功 + 产物 hash 匹配 | 长链条顺序              |
| env-svc-port-01   | 端口冲突/守护        | 服务在正确端口响应 + 旧进程被清理       | 环境状态排查             |

判分：verify.sh 断言逐条计分（部分分）+ oracle 脚本存在性校验。

## 7. 规模与节奏

| 阶段         | 内容                                          | 产出              |
| ---------- | ------------------------------------------- | --------------- |
| W1 前半      | miner 升级 F2P/P2P 分离 + 校验器升级 + 判分器升级         | mined 6–8 任务    |
| W1 后半      | forged 算子 ×5 对 more-itertools/cachetools 注入 | forged 15–20 任务 |
| W2 前半      | Pilot Gate 全池校准（n=3）+ horizon 标定            | 池定稿 ~25 任务      |
| W2 后半      | v1/v3 复测（dev 子集 × {A0,A1f} × n=3）           | **"正收益是否存在"首答** |
| docker 恢复后 | env 轨 4 任务 + lite 验证                        | env 轨上线         |

## 8. 验收标准（pool-v2 建成）

1. 池内 ≥25 任务全过四关 + Pilot Gate 在带内（resolve_rate 0.4–0.8）；
2. 任抽 3 任务人工复查：F2P/P2P 划分无错（Verified 教训的机械执行）；
3. v1/v3 复测产出 A0 与 A1f 的可测通过率差（方向不限，有信号即胜利）；
4. 难度字段双轨：类别 D 档 + horizon 分钟数同时落库。

---

## 附录：实施状态（2026-10-01 定稿 pool-v2.0-rc）

### 已实施
- **forge 引擎/配方分离**：引擎 scripts/forge_tasks.py（通用，零任务域/Skill
  硬编码），配方 tasks/pool-v2/forge_specs/*.yaml（声明式算子定义）。
  换任务域 = 新写 yaml；换被评 Skill = 臂注入侧参数，与 forge 无关。
  代码审计：pool 相关脚本零 "tdd" 引用。
- **任务清单（9 个，四关+P2P 全过）**：单 bug ×4（成本区分池）+
  复合 ×5（multi-sieve/dual/taketail/crossfile/triple，分数区分池）。
- **判分**：F2P 通过率 × P2P 闸门（POOL_V2 §3 全落地）；
  校验器支持零上下文补丁（--unidiff-zero）。
- **难度光谱实测（pilot-multi-1/2，deepseek n=3）**：
  | 任务 | A0 | v1 | v3 | 角色 |
  |---|---|---|---|---|
  | multi-taketail | 3/3 (5t) | 3/3 (8t) | 3/3 (8t) | 成本区分 |
  | multi-dual | 2/3 | 3/3 | 3/3 | 正收益苗头 |
  | multi-crossfile | 3/3 | 3/3 | 2/3 | 成本/方差 |
  | multi-sieve | 1/3 | 1/3 | 2/3 | **分数区分（v3 存活优势）** |
  | multi-triple | 1/3 | 0/3 | 0/3 | 地板（Skill 臂全超时） |

### 已知问题（挂账）
- 长单进程多 pytest 批次有静默退出现象（引擎/校验器全量长跑需分批）；
- multi-triple 触地板（Skill 臂 0/3 超时）——Pilot Gate 判定需
  降难度或提 timeout 档位；
- v3 存活率优势（sieve 2/3 vs 1/3）与正收益苗头（dual）均为方向级，
  补 n=5 是 pool-v2.0 正式版的前置条件。

### 未实施
- env 轨（docker 阻塞）；Pilot Gate baseline 全量回填；dev 旧池退役为回归集。

---

## pool-v2.0 正式版（2026-10-02 定版）

### 定版状态
- **任务集定稿**：tasks/pool-v2/forged-final/ 9 个任务（baseline 已回填
  meta，角色标注：带内/天花板侧/地板）；四关 + P2P 全过。
- **生产设施定稿**：forge 引擎 + 声明式配方（forge_specs/）；
  mine 管线（筛选有效、产出为零已登记）；add_p2p 设施。
- **判分定稿**：F2P 通过率 × P2P 闸门；超时计入"未完成"（完成率双轨）；
  horizon_minutes 起步。

### dev 旧池处置（正式决定）
- tasks/generated/ 18 个合成任务**降级为回归集**（用途：Skill 修订后的
  防退化检查，"v3 改动不破坏既有通过能力"）——不再用于主矩阵增益测量
  （天花板，quick-n3 108/108 已证）。
- 主矩阵 dev 子集 = forged-final 中带内+天花板侧 8 个任务
  （multi-triple 地板样本保留在池但不进主矩阵）。
- heldout/ 6 任务维持终验专用（已用过一次，属半曝光；
  下次终验前需用 forge 引擎换配方轮换出新 heldout）。

### pool-v2.0 → v2.1 的前置条件
1. multi 主复测 n=5（进行中：pool-v20-main，60 run）出正式答案；
2. triple 处置（降难度或 timeout 提档）；
3. env 轨（docker 恢复）。
