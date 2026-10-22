# 未竟事项接续说明（换机/换人照做即可）

> 生成 2026-10-03。配套 `docs/HANDOVER.md`。所有命令在 `D:\ai_project\skill-bench` 下执行。
> 环境：`PY="C:/Users/17664/.workbuddy/binaries/python/envs/default/Scripts/python.exe"`

---

## 事项 1：pool-v3 确认批（C7 定生死）

### 当前状态（已跑完 3×15=45 run，但样本被死跑侵蚀）

| 族 | A0 | A0p（安慰剂） | A1f-conv（知识 Skill） |
|---|---|---|---|
| streamkit | 有效 2，均分 **1.00** | 有效 1，0.50 | 有效 5，0.92 |
| deploykit | 有效 0（死 4 错 1） | 有效 1，**1.00** | 有效 3，1.00 |
| fluxdb | 有效 0（死 4 错 1） | 有效 1，**1.00** | 有效 4，1.00 |

**两个问题，都还没解决：**
1. **死跑率过高**（A0 臂 60~100% 死跑）→ 样本不足，无法下结论；
2. **A0/A0p 也能拿满分**（streamkit A0 两次 1.0、deploykit/fluxdb 安慰剂 1.0）
   → 说明这两个族的约定仍然**可被推断**，知识缺口没造严。

### 接续步骤

```bash
# 1) 补样本：续跑（run_id 幂等，只跑缺的/死跑的，跑 2-3 轮直到有效 n≥4/臂）
for i in 1 2 3; do
  DIS_API_KEY=sk-... "$PY" -m backend.orchestrator.runner \
      matrix/poolv3-streamkit.yaml --driver pi --batch poolv3c-streamkit
  # deploykit / fluxdb 同理
done

# 2) 每轮后看状态（判定：某臂有效 n<4 → 继续补；死跑率>50% → 先查渠道）
"$PY" -m backend.gate.pilot_gate --health results/poolv3c-streamkit
# → degraded=true 表示降级窗口，本轮数据不可用于完成率类结论

# 3) 若 A0 仍 ≥0.9：约定太易推断 → 按铁律 v3.3 改包（见下）
```

### 设计铁律 v3.3（本次事故新增）

> **约定必须是"反直觉"的——不能是行业通行做法。**
> deploykit 的"阶段顺序校验 + 专属异常"、fluxdb 的"深拷贝/软删/缺键异常"
> 都是强模型见过的常见模式，读 prompt 就能推断全貌。
> 有效做法：约定与常识**反向**（如"缺键返回哨兵而不抛异常"、"错误静默记日志
> 且只在 flush 时抛"），这类规则模型猜不中，只有文档能给。

### C7 判定规则（写死，防自欺）

```
有效样本 n≥4/臂 且 渠道非降级窗口 且 A0 ≤ 0.6 且 A0p ≈ A0 且 A1f-conv ≥ A0 + 0.2
  → C7 成立（Skill 在知识缺口处为正）
任一条不满足 → C7 维持"未证实"，报告中只定性披露
```

---

## 事项 2：κ 校准会话（归因器采信门）

### 当前状态：表已生成，等你标注

- `docs/kappa_sheet.md`：20 张卡片（分层：8 命中 + 12 无罪），每张含
  检测器结论 + 6 条证据摘要；
- `docs/kappa_sheet_calc.json`：机器侧结论（供计算 κ）。

### 接续步骤

1. 打开 `docs/kappa_sheet.md`，逐张卡判 **同意 / 不同意**（不同意请写正确结论）；
2. 把 20 条判定发给我（格式：`1 同意 / 2 不同意：应为无罪 / 3 同意 …`）；
3. 我算 Cohen's κ（脚本约定：`(Po−Pe)/(1−Pe)`，`Po`=一致率，`Pe`=期望一致率）：
   - **κ ≥ 0.7** → 归因器自动采信，输出进主报告数字；
   - **κ < 0.7** → 只定性披露，并据此修检测器（重复本轮）。
4. 重新抽样：`"$PY" scripts/kappa_sheet.py`（seed 固定 20261002，可复现）。

---

## 事项 3：A1 自主触发臂（H2 触发模式）

### 当前状态：批次未产出（`results/auto-probe/` 无 runs.jsonl，当时进程被中断）

### 接续步骤

```bash
# 预设已就绪：matrix/auto-probe.yaml（A0 / A1-auto(pi 原生 --skill) / A1f-v1）
for i in 1 2 3; do
  DIS_API_KEY=sk-... "$PY" -m backend.orchestrator.runner \
      matrix/auto-probe.yaml --driver pi --batch auto-probe
done

# 判读口径（H2）：
#  A1-auto ≈ A0（模型根本没触发/没读）→ 自主触发不可靠
#  A1-auto ≈ A1f-v1（模型自己读了并执行）→ 触发可靠且效果好
#  A1-auto 介于两者 → 触发率不稳定（重点看轮次方差）
```

---

## 事项 4（新）：docker 沙箱——已升级为前提项

pool-v3 实证：agent 会离开 repo 全局搜索"团队文档"并偷读到知识文档
（`skills/streamkit-convention/SKILL.md` 被 A0 满分轨迹直接读取）。

- 已做的缓解：知识文档外迁到 `%TEMP%/skillbench-v3-skills-x7q2`，预设指向外迁路径；
- **未做（终解）**：docker 容器隔离文件系统。
- 结论标注要求：docker 恢复前，pool-v3 任何结论须带"**搜索半径缓解**"前缀。

---

## 优先级建议

1. **先跑 auto-probe**（便宜，24 run，补 H2 空缺）；
2. **pool-v3 补样本 + 查渠道**（决定 C7 生死）；
3. **κ 会话**（需你 1 小时，可与 2 并行：你标注时我跑批）；
4. 若 A0 仍满分 → 按 v3.3 改写约定（造"反直觉"规则）；
5. docker 恢复 → pool-v3 干净重跑 → 报告 v7.0 定稿"边界论"。

---

## 事项 5：后端缺口清单（已做 / 未做，含验收标准）

### 已落地（2026-10-02 全清账）

| 件 | 位置 | 状态 |
|---|---|---|
| 归因器 v1（L1-L3） | `backend/attribution/` | ✅ 6 检测器 + 指令联动 + 8 例单测；零 LLM、零 Skill 硬编码 |
| API 服务（FastAPI，8 端点） | `backend/api/server.py` | ✅ 含 `/api/attribution` |
| 前端五视图 | `frontend/index.html` | ✅ 总览/矩阵/任务池/批次/版本链 |
| DB schema（model/dead/tps + 老库迁移） | `backend/store/db.py` | ✅ `_ensure_columns` 幂等 |
| Pilot Gate 自动化 | `backend/gate/pilot_gate.py` | ✅ 判定书 + baseline 回填 + 渠道健康 |
| 渠道健康协议 | `tps` 字段 + gate 判定 | ✅ 批次级降级窗口识别 |
| process_judge（辅助 LLM） | `backend/graders/process_judge.py` | ✅ `--judge` 实调通；κ 未过 → 默认 dry-run |
| 辅助 LLM 统一客户端 | `backend/llm_client.py` | ✅ DIS relay，与评测通道物理隔离 |
| 校验器零上下文补丁 | `--unidiff-zero` | ✅ 支持逐组 site 补丁 |

### 未做（按优先级）

| # | 件 | 说明与验收标准 | 预估 |
|---|---|---|---|
| B1 | **归因器 F17/F19 检测器** | 需事件流带命令输出（当前 events 无 tool_result）。验收：normalize 层补 `tool_result` 事件 + 两检测器上线并通过合成单测 | 3h |
| B2 | **归因器 L4 反事实自检** | 用 `wrong_01` 作预计算决定性错误标注，自检套件全绿 | 2h |
| B3 | **κ 门自动化** | κ≥0.7 后归因输出自动进主报告（当前靠人工声明）。验收：`attribution` 表 + 报告自动引用 | 1h（需 κ 结果） |
| ~~B4~~ | ~~归因结果入库~~ | ✅ **已完成 10-03**（attribution 表 + `ingest_attribution`，实证 24 run→3 条） | — |
| ~~B5~~ | ~~DB 视图更新~~ | ✅ **已完成 10-03**（v_arm_stats 含 model/dead/tps；新增 v_channel_health 32 批） | — |
| B6 | **渠道健康前置探测** | 跑批前先探 tps，降级窗口自动暂停并提示（当前只能事后判定） | 2h |
| B7 | **env 轨 runner 支持** | verify.sh 终态断言协议（docker 阻塞的前置件，协议可先写） | 3h |
| B8 | **docker 沙箱** | runner 改容器执行；**pool-v3 结论可信性的前提** | 半天（需 docker 可用） |
| ~~B9~~ | ~~API 补端点~~ | ✅ **已完成 10-03**（/api/runs/{batch}/{run} 含事件流+归因、/api/log、/api/gate/health） | — |
| ~~B10~~ | ~~单测补齐~~ | ✅ **部分完成 10-03**（backend/tests/test_gate_and_store.py，6 例：Gate 边界/死跑口径/渠道健康/DB 视图/API 路由） | 剩 API 语义测 |
| B11 | **patch 写入 CRLF 隐患** | `Path.write_text` 在 Windows 默认换行 → 补丁可能带 CRLF 导致 git apply 失败。验收：全仓库补丁写入统一 `newline="\n"` | 30min |
| B12 | **heldout 轮换工具化** | heldout-v2 是手写配方；应参数化（换函数即出新终验集） | 2h |
| B13 | **报告生成 CLI** | `report.py` 仅 102 行，v6.5 是手写。验收：`python -m backend.analysis.report --batch X` 产出标准段 | 3h |
| B14 | **前端补视图** | ✅ **部分完成 10-03**（归因视图 + 渠道健康视图已上线）；剩 pool-v3 视图 | 1h |

### 建议执行顺序

```
B11（30min，地基）→ B9/B4/B5（半日，数据面补齐）
→ B1/B2（半日，归因器补全）→ B6（2h，防污染前置）
→ B7/B8（docker 后）→ B3（κ 通过后）→ B10/B12/B13/B14（收尾）
```

> 注意：B8（docker）是 pool-v3 结论可信性的**前提**，不是可选项——
> 其余件是完备性，可随迁移后按需推进。
