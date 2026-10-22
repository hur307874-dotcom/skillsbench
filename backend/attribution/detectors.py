"""L2 机械检测器：事件时序/diff/记录字段 → F-ID 命中（零 LLM，零 Skill 硬编码）。

设计约束（AgentRx 守卫模式 + MT-Bench 红线）：
- 每个检测器声明 guard（何时适用），输出必须带证据事件 idx；
- 判定规则全部来自通用事件模式（工具名/命令正则/路径正则/时序/分数字段），
  不读任何 Skill 内容、不含任何 Skill 名；
- F-ID 语义文本从 failure_modes.yaml 读（数据驱动），代码里不复制描述。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# ---- 通用事件分类正则（跨语言/跨框架，不含任何任务域或 Skill 内容） ----
WRITE_NAMES = {"edit", "write", "str_replace", "apply_patch", "create",
               "update_file", "write_file", "insert", "replace"}
WRITE_CMD = re.compile(r"(apply_patch|sed\s+-i|cat\s*>|>>\s*\S|tee\s+\S)", re.I)
RUN_CMD = re.compile(
    r"(pytest|py\.test|unittest|python[0-9.]*\s+(-c|-m\s+(pytest|unittest)|\S+\.py)|"
    r"node\s+\S+\.js|npm\s+test|yarn\s+test|cargo\s+test|go\s+test|mvn\s+test|"
    r"gradle(w)?\s+test|ctest|make\s+test|rspec|phpunit)", re.I)
TEST_PATH = re.compile(
    r"(^|[/\\'\"])(tests?|__tests__|spec)[/\\]|test_\w+\.py\b|\w+_test\.(py|go|js|ts)\b|"
    r"\w+\.test\.(js|ts)\b|\w+Tests?\.(java|rb|cs)\b|\w+_spec\.rb\b", re.I)
DONE_CLAIM = re.compile(
    r"(修复完成|已修复|修好了|已解决|问题解决|修复了|fixed|done|resolved|"
    r"all tests pass|测试全过|验证通过)", re.I)
# 与 behavior_signals.py 校准过的确认请求句式同源（请求句式，非行话）
CONFIRM_ASK = re.compile(
    r"(请确认|是否确认|请你确认|请批准|是否可以|我可以(继续|进行)吗|"
    r"(please|shall i|may i|can i|should i)\s+(confirm|proceed|continue|approve)|"
    r"confirm(ing)?\s+(with you|before)\b)", re.I)
# B1（F17/F19）：工具输出文本模式（输出来自原始 trace 的 tool_execution_end）
NOT_FOUND = re.compile(
    r"(no such file|not found|cannot find|could not find|does not exist|"
    r"FileNotFoundError|找不到|不存在)", re.I)
FAIL_SIG = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)          # pytest 短摘要
FAIL_HDR = re.compile(r"_{3,}\s*(test[\w\[\]().:-]*)\s*_{3,}")      # pytest 失败分节头
READ_MISS_NAMES = {"read", "view", "glob", "open", "cat", "ls", "find", "grep"}
READ_MISS_CMD = re.compile(r"\b(cat|ls|find|grep|head|tail)\b", re.I)


@dataclass
class Hit:
    f_id: str
    confidence: str          # high | medium | low
    evidence_idx: list[int] = field(default_factory=list)
    note: str = ""


@dataclass
class RunCtx:
    run_id: str
    events: list[dict]       # 归一化事件（含 idx/type/payload 已解析）
    score: float | None = None
    tests: str = ""
    sites_required: int = 1
    num_turns: int = 0
    outputs: dict = field(default_factory=dict)  # 工具调用 idx → 输出文本（原始 trace）

    # ---- 预计算视图 ----
    def calls(self) -> list[tuple[int, str, str]]:
        """(idx, name, args_str) 的工具调用序列。"""
        out = []
        for e in self.events:
            if e["type"] != "tool_call":
                continue
            p = e["payload"]
            out.append((e["idx"], p.get("name", ""), str(p.get("args", ""))))
        return out

    def steps(self, role: str | None = None) -> list[tuple[int, str]]:
        out = []
        for e in self.events:
            if e["type"] != "step":
                continue
            p = e["payload"]
            if role and p.get("role") != role:
                continue
            out.append((e["idx"], p.get("text", "") or ""))
        return out

    def has_write(self) -> bool:
        return any(self.is_write(n, a) for _, n, a in self.calls())

    @staticmethod
    def is_write(name: str, args: str) -> bool:
        return name.lower() in WRITE_NAMES or bool(WRITE_CMD.search(args))

    @staticmethod
    def is_run(name: str, args: str) -> bool:
        return name.lower() in {"bash", "shell", "run", "terminal", "execute"} \
            and bool(RUN_CMD.search(args))


# ---- 检测器（每个 = f_id + guard + detect；guard 不满足返回 None） ----

def detect_f01(ctx: RunCtx) -> Hit | None:
    """F01 未复现就动手：首个写事件早于首个运行事件。
    归因语义化：只在结果坏时判（成功 run 的"读了就改"是合法静态分析）。"""
    if ctx.score is None or ctx.score >= 1.0:
        return None  # guard：结果不坏不归因（行为信号与失效归因分离）
    calls = ctx.calls()
    fw = next((i for i, n, a in calls if ctx.is_write(n, a)), None)
    fr = next((i for i, n, a in calls if ctx.is_run(n, a)), None)
    if fw is None or fr is None:
        return None  # guard：两类事件都出现才可判
    if fw < fr:
        return Hit("F01", "high", [fw, fr],
                   f"首个写操作(#{fw})早于首个测试/运行(#{fr})")
    return None


def detect_f03(ctx: RunCtx) -> Hit | None:
    """F03 不验证就宣布完成：末次写之后无运行，且出现完成声明。
    归因语义化：只在结果坏时判（声明若最终被证明是对的则非失效）。"""
    if ctx.score is None or ctx.score >= 1.0:
        return None
    calls = ctx.calls()
    writes = [i for i, n, a in calls if ctx.is_write(n, a)]
    runs = [i for i, n, a in calls if ctx.is_run(n, a)]
    if not writes:
        return None
    lw = writes[-1]
    lr = runs[-1] if runs else -1
    if lw > lr:
        claim = next((i for i, t in ctx.steps("assistant")
                      if i > lw and DONE_CLAIM.search(t)), None)
        if claim:
            return Hit("F03", "high", [lw, claim],
                       f"末次写(#{lw})后无验证，assistant 于 #{claim} 宣布完成")
    return None


def detect_f05(ctx: RunCtx) -> Hit | None:
    """F05 漏改调用点：多点任务未满分（部分分即漏改证据）。"""
    if ctx.sites_required <= 1 or ctx.score is None:
        return None
    if ctx.score < 1.0:
        return Hit("F05", "medium", [],
                   f"应改 {ctx.sites_required} 处，得分 {ctx.score}（{ctx.tests}）")
    return None


def detect_f11(ctx: RunCtx) -> Hit | None:
    """F11 过度验证：同一工具同参数连续 ≥3 次且无中间修改。"""
    calls = ctx.calls()
    streak: list[tuple[int, str, str]] = []
    for c in calls:
        key = (c[1], c[2])
        if streak and (streak[-1][1], streak[-1][2]) == key and not ctx.is_write(*key):
            streak.append(c)
        else:
            if len(streak) >= 3:
                return Hit("F11", "high", [s[0] for s in streak],
                           f"{streak[0][1]} 同参数连续重复 {len(streak)} 次")
            streak = [c]
    if len(streak) >= 3:
        return Hit("F11", "high", [s[0] for s in streak],
                   f"{streak[0][1]} 同参数连续重复 {len(streak)} 次")
    return None


def detect_f15(ctx: RunCtx) -> Hit | None:
    """F15 幻影用户：发出确认请求后无真实用户输入即继续。"""
    steps = ctx.steps()
    for k, (i, text) in enumerate(steps):
        # guard：assistant 发出确认请求
        # steps 里 role 信息在 payload，需回看原事件
        pass
    asks = []
    for e in ctx.events:
        if e["type"] == "step" and e["payload"].get("role") == "assistant":
            t = e["payload"].get("text", "") or ""
            if CONFIRM_ASK.search(t):
                asks.append(e["idx"])
    if not asks:
        return None
    has_user_after = any(
        e["type"] == "step" and e["payload"].get("role") == "user"
        and e["idx"] > asks[0] and "confirm" not in (e["payload"].get("text") or "").lower()
        for e in ctx.events)
    if not has_user_after:
        return Hit("F15", "high", asks,
                   f"确认请求句式 ×{len(asks)}，无真实用户回应即继续")
    return None


def detect_f16(ctx: RunCtx) -> Hit | None:
    """F16 水平切片：先连写 ≥2 个测试文件，再写实现文件。
    归因语义化：只在结果坏时判（κ 卡 1 教训——成功 run 的交替改测是合法 TDD）。"""
    if ctx.score is None or ctx.score >= 1.0:
        return None
    test_writes, impl_write = [], None
    for i, n, a in ctx.calls():
        if not ctx.is_write(n, a):
            continue
        if TEST_PATH.search(a):
            if impl_write is None:
                test_writes.append(i)
        elif impl_write is None:
            impl_write = i
    if len(test_writes) >= 2 and impl_write is not None:
        return Hit("F16", "medium", test_writes + [impl_write],
                   f"先连写 {len(test_writes)} 个测试文件再写实现")
    return None


def detect_f17(ctx: RunCtx) -> Hit | None:
    """F17 误读报错治症状：修改后同类错误复现（同一失败签名在写操作后再现）。
    依赖原始 trace 的工具输出（ctx.outputs）；无输出数据时 guard 不判。"""
    if ctx.score is None or ctx.score >= 1.0:
        return None
    seq: list[tuple[int, str, frozenset]] = []  # (idx, "run"|"write", 失败签名集)
    for i, n, a in ctx.calls():
        if ctx.is_run(n, a):
            out = ctx.outputs.get(i, "")
            sigs = frozenset(FAIL_SIG.findall(out)) | frozenset(FAIL_HDR.findall(out))
            if sigs:
                seq.append((i, "run", sigs))
        elif ctx.is_write(n, a):
            seq.append((i, "write", frozenset()))
    for k, (i, kind, s1) in enumerate(seq):
        if kind != "run":
            continue
        for j in range(k + 1, len(seq)):
            if seq[j][1] != "write":
                continue
            for l in range(j + 1, len(seq)):
                if seq[l][1] == "run" and seq[l][2] and (s1 & seq[l][2]):
                    common = sorted(s1 & seq[l][2])[:3]
                    return Hit("F17", "high", [i, seq[j][0], seq[l][0]],
                               f"失败签名在修改(#{seq[j][0]})后复现：{common}")
    return None


def detect_f19(ctx: RunCtx) -> Hit | None:
    """F19 空转查找不存在文件：对不存在路径的 read/glob/find 调用 ≥2 次
    且输出均为 not found。依赖原始 trace 的工具输出。"""
    if ctx.score is None or ctx.score >= 1.0:
        return None
    misses = []
    for i, n, a in ctx.calls():
        nl = n.lower()
        if nl not in READ_MISS_NAMES and not (nl in {"bash", "shell"} and READ_MISS_CMD.search(a)):
            continue
        out = ctx.outputs.get(i, "")
        if out and NOT_FOUND.search(out):
            misses.append(i)
    if len(misses) >= 2:
        return Hit("F19", "medium", misses,
                   f"对不存在路径的读取 ×{len(misses)}（输出均 not found）")
    return None


def classify_activity(ctx: RunCtx, input_tokens: int | None = None,
                      output_tokens: int | None = None, error: str = "") -> str:
    """B15 前置活动性门：F-ID 判定前的 run 分类。

    - channel_dead：渠道死——token 显式全 0 或超时，**且事件流无任何工具调用**
      （有调用则 token 字段是脏数据，以事件为准——κ 卡 6 教训）；
    - no_edit：有活动但零写操作——知识缺口任务里 A0 的合法结局（保底分），
      不适用任何改代码类 F-ID（κ 校准 7 条误报全是这类被错扣帽子）；
    - ok：有写操作，正常进入 F-ID 判定。
    """
    if not ctx.calls() and (
            (input_tokens is not None and output_tokens is not None
             and not (input_tokens or output_tokens))
            or "timeout" in str(error)):
        return "channel_dead"
    if not ctx.has_write():
        return "no_edit"
    return "ok"


DETECTORS = [detect_f01, detect_f03, detect_f05, detect_f11,
             detect_f15, detect_f16, detect_f17, detect_f19]
