# POOL_V3 卡死归因诊断（2026-10-03 晚）

> 触发：用户反馈 pool-v3 在之前运行中"卡死"。方法：复盘 POOL_V3.md / NEXT_STEPS.md +
> 逐 run 解剖 poolv3c-* 三批 trace。**结论：卡死是三层问题叠加，且发现 NEXT_STEPS
> 漏掉的第四层——搜盘泄题通道全部打穿（A0 满分的真实机制）。**

## 一、pool-v3 是什么（30 秒版）

知识缺口任务池：三个虚构内部库（streamkit 空输入哨兵 / deploykit 发布门禁 /
fluxdb KV 语义），约定只写在配套 Skill 文档里，测试拆"行为分（保底 0.4）+
约定分（0.5）"双文件。三臂对照：A0 裸考 / A0p 安慰剂（烹饪文档）/ A1f-conv 注入约定。
目的：确认 C7——"Skill 只在知识缺口处有用"（原型 poolv3-proto2：0.40 / 0.40 / 0.90）。

## 二、卡死的三层归因

### ① 运行层：渠道空响应 + 超时堆积（批次爬不动的直接原因）

- `poolv3c-deploykit` A0：8/15 撞 720s 超时上限、7/15 标记死跑、**0 个干净 run**；
  fluxdb A0 同样 0 干净。每个超时吃满 12 分钟并发槽 → 45 run 的批次拖到被中断
  （A1f-conv 只跑完 7~12/15）。
- trace 铁证：fluxdb A0-r03/r04 完整事件流中 `message_end` 的
  **content=[] 且 usage in=0/out=0**——DIS relay 返回空响应，pi 静默结束（exit=0）。
  另一类是连接挂起、0 轮次直到 720s 被 runner 杀掉。
- 这是已知"渠道健康"问题（C5）在 pool-v3 的复发，不是任务设计问题。

### ② 判定层：死跑口径把合法结果误删（统计被污染）

- runs.jsonl 同一 run_id 有 2~3 条重试记录——不去重直接统计会放大死跑率。
- 更关键：`dead_run: 未修改任何文件` 混合了两种完全不同的东西——
  - **渠道死**（usage=0，fluxdb r03/r04）→ 确实该剔除；
  - **合法探索后放弃**（usage 正常、工具调用 7~16 次后判断无从下手）——
    **这在知识缺口任务里是 A0 的合法结果（拿 0.4 保底）**，剔除它会把 A0 均分
    严重高估（NEXT_STEPS 表里 streamkit A0"有效 2、均分 1.00"就是这么来的：
    只数了猜中的，没数放弃的）。
- 后果：NEXT_STEPS 的"有效 n"口径偏窄且方向性偏估，C7 判定规则的分母口径需重写。

### ③ 设计层：约定可推断（v3.3，已记录）

prompt 剧情 + fixture 脚手架把答案剧透完了：deploykit 的 PHASES 顺序直接写在
fixture 里；fluxdb 的"值被改坏→深拷贝 / 键找不回→软删（fixture 里 revive 就是
NotImplementedError）/ 大小写重复→小写归一"逐句对应；异常名都是自然命名。
NEXT_STEPS 已立铁律 v3.3（约定必须反直觉），此诊断确认无误。

## 三、新发现：搜盘泄题四通道全部打穿（A0 满分的真实机制）

`poolv3c-streamkit/work/conv-streamkit-empty-A0-r05/trace.json` 逐工具调用还原，
一个 A0（无注入）run 的完整作弊链：

1. 在自己 repo 里 find → 跳出 repo，读了自己 run 的 `trace.json`；
2. `find results/poolv3c-streamkit -name '*.md'/'*.json'` → 扫整个批次目录；
3. `find results/.../work -name '__init__.py'` → **读同批次其他 run 的 repo（跨臂污染）**；
4. `ls -R tasks && ls -R skills` 扫工作区 →
   **`read skills/streamkit-convention/SKILL.md`**——工作区副本还在！
   （10-02 外迁 %TEMP% 只复制了文件、没删原件）；
5. `grep -rl "streamkit" tasks/` → **cat INTENT.md + tests/f2p/test_convention.py
   ——隐藏测试（判分标准）直接读取**；
6. 照着读到的规范 + 测试改写代码，自跑 pytest 通过后收工。

**推论（修正 NEXT_STEPS 的归因）**：A0/A0p 满分不是（或不只是）"约定太易推断"，
而是"搜盘读答案 + 可推断"的混合。这意味着：
- 铁律 v3.3 单独不够——约定改成反直觉后，agent 仍能搜盘读文档/读测试；
- docker 沙箱的需求升级：容器内必须同时**不可见** skills 副本、tasks/*/solution、
  tasks/*/tests、同批 work 目录、%TEMP% 外迁路径。

## 四、风险外溢（待查，影响面超出 pool-v3）

通道 (b)(c) 与 pool-v3 无关：**pool-v2 历史批次的 agent 同样能搜到
`tasks/pool-v2/forged-final/*/solution` 和隐藏测试**。pool-v2"健康渠道下全满分"
的结论可能被同类污染。建议抽查 pool-v20-main 的 A0 trace 有无越界 read
（grep `skills/`、`solution`、`tests/f2p` 的读取事件）。

## 五、处置建议（按序）

1. **立做（零成本）**：删除工作区 skills/ 下三个约定文档副本（外迁已存在 %TEMP%）；
   检查 tasks/ 下 solution/tests 的 agent 可见性——评测 run 的 cwd 与搜索半径问题。
2. **口径修正**：dead_run 检测拆分"usage=0 渠道死"与"usage>0 合法无编辑"，
   后者计入有效样本（score=保底分）；C7 判定按 run_id 去重后重算。
3. **抽查 pool-v2**：确认历史结论是否被搜盘污染（见 §四）。
4. **中期**：docker 沙箱（已升级为结论可信性前提）——容器内只挂 fixture，
   solution/tests 判分时才挂，skills 注入臂只挂对应文档。
5. **此后**才轮到 v3.3 反直觉约定改写 + n=5 确认批。

> 注：按 10-03 晚 ASSIGNMENT_ALIGNMENT 的纠偏，pool-v3/C7 已降级为加分项；
> 但 §四的泄题通道影响主线历史结论的可信性，建议至少完成第 1、3 条。
