"""一次性：三包 gold/wrong 基于中性化 fixture 重建。"""
import difflib
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from build_poolv3_fluxdb import GOLD_FLUXDB  # noqa: E402


def regen(tdir_s, fixed_text, rel):
    tdir = Path(tdir_s)
    fixture = tdir / "fixture" / rel
    orig = fixture.read_text(encoding="utf-8")
    d = list(difflib.unified_diff(orig.splitlines(), fixed_text.splitlines(),
                                  lineterm="", n=3,
                                  fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    (tdir / "solution/sites/site-01.patch").write_text(
        "\n".join(d) + "\n", encoding="utf-8", newline="\n")


SENTINEL = (
    "class EmptyStream:\n"
    "    \"\"\"空流哨兵（单例）。所有公开 API 的空输入必须返回它。\"\"\"\n"
    "\n"
    "    _instance = None\n"
    "\n"
    "    def __new__(cls):\n"
    "        if cls._instance is None:\n"
    "            cls._instance = super().__new__(cls)\n"
    "        return cls._instance\n"
    "\n"
    "    def __iter__(self):\n"
    "        return iter(())\n"
    "\n"
    "    def __repr__(self):\n"
    "        return \"EmptyStream\"\n"
    "\n"
    "\n"
    "def _validate_stream(source, name=\"source\"):\n"
    "    \"\"\"公开 API 入参校验：None → ValueError；非可迭代 → TypeError。\"\"\"\n"
    "    if source is None:\n"
    "        raise ValueError(f\"{name} 不能为 None\")\n"
    "    if not hasattr(source, \"__iter__\"):\n"
    "        raise TypeError(f\"{name} 必须是可迭代对象\")\n"
    "\n"
    "\n"
)

# ---- streamkit ----
sk_path = Path("tasks/pool-v3/conv-streamkit-empty/fixture/streamkit/__init__.py")
sk = sk_path.read_text(encoding="utf-8")
sk_fixed = sk.replace("def chain(*sources):", SENTINEL + "def chain(*sources):", 1)
sk_fixed = sk_fixed.replace("        return []", "        return EmptyStream()")
sk_fixed = sk_fixed.replace(
    "    items = [x for x in stream]\n    if not items:\n        return into()",
    "    _validate_stream(stream)\n    items = [x for x in stream]\n"
    "    if not items:\n        return EmptyStream()")
regen("tasks/pool-v3/conv-streamkit-empty", sk_fixed, "streamkit/__init__.py")

w = sk.replace("        return []", "        return EMPTY_STREAM")
w = w.replace(
    "    items = [x for x in stream]\n    if not items:\n        return into()",
    "    items = [x for x in stream]\n    if not items:\n        return EMPTY_STREAM")
w = w.replace("def chain(*sources):",
              "class _EmptyC:\n"
              "    def __iter__(self):\n"
              "        return iter(())\n\n\n"
              "EMPTY_STREAM = _EmptyC()\n\n\n"
              "def chain(*sources):", 1)
Path("tasks/pool-v3/conv-streamkit-empty/wrong/wrong_01/streamkit/__init__.py"
     ).write_text(w, encoding="utf-8")

# ---- deploykit ----
dk_path = Path("tasks/pool-v3/conv-deploykit-pipeline/fixture/deploykit/__init__.py")
dk = dk_path.read_text(encoding="utf-8")
ERRS = (
    "class PipelineError(Exception):\n"
    "    \"\"\"流水线通用错误。\"\"\"\n"
    "\n"
    "\n"
    "class PhaseOrderError(PipelineError):\n"
    "    \"\"\"阶段顺序/缺失违规（规范专属类型）。\"\"\"\n"
    "\n"
    "\n"
    "class GateError(PipelineError):\n"
    "    \"\"\"阶段门禁未满足（规范专属类型）。\"\"\""
)
dk_fixed = dk.replace(
    "class PipelineError(Exception):\n    \"\"\"流水线通用错误。\"\"\"", ERRS)
OLD_BODY = (
    "    context = context or {}\n"
    "    report = {\"executed\": [], \"status\": \"ok\"}\n"
    "    for step in steps:\n"
    "        phase = step[\"phase\"]\n"
    "        if phase not in PHASES:\n"
    "            raise PipelineError(f\"未知阶段: {phase}\")\n"
    "        step[\"fn\"](context)\n"
    "        report[\"executed\"].append(phase)\n"
    "        if phase == \"canary\":\n"
    "            context[\"canary_done\"] = True\n"
    "    return report")
NEW_BODY = (
    "    context = context or {}\n"
    "    report = {\"executed\": [], \"status\": \"ok\"}\n"
    "    phases_in = [s[\"phase\"] for s in steps]\n"
    "    if phases_in != PHASES:\n"
    "        raise PhaseOrderError(f\"阶段顺序/集合违规: {phases_in}，应为 {PHASES}\")\n"
    "    for step in steps:\n"
    "        phase = step[\"phase\"]\n"
    "        if phase == \"canary\" and \"health_check\" not in step:\n"
    "            raise GateError(\"canary 缺少 health_check 回调\")\n"
    "        if phase == \"promote\" and not context.get(\"canary_success\"):\n"
    "            raise GateError(\"promote 前缺少 canary 成功标记\")\n"
    "        step[\"fn\"](context)\n"
    "        report[\"executed\"].append(phase)\n"
    "    return report")
dk_fixed = dk_fixed.replace(OLD_BODY, NEW_BODY)
assert dk_fixed != dk, "deploykit gold 替换未生效"
regen("tasks/pool-v3/conv-deploykit-pipeline", dk_fixed, "deploykit/__init__.py")

w = dk.replace(
    "    context = context or {}\n"
    "    report = {\"executed\": [], \"status\": \"ok\"}\n"
    "    for step in steps:",
    "    context = context or {}\n"
    "    report = {\"executed\": [], \"status\": \"ok\"}\n"
    "    if [s[\"phase\"] for s in steps] != PHASES:\n"
    "        raise PipelineError(\"阶段顺序错误\")\n"
    "    for step in steps:")
Path("tasks/pool-v3/conv-deploykit-pipeline/wrong/wrong_01/deploykit/__init__.py"
     ).write_text(w, encoding="utf-8")

# ---- fluxdb ----
regen("tasks/pool-v3/conv-fluxdb-semantics", GOLD_FLUXDB, "fluxdb/__init__.py")
fx = Path("tasks/pool-v3/conv-fluxdb-semantics/fixture/fluxdb/__init__.py"
          ).read_text(encoding="utf-8")
w = fx.replace("class FluxDB:",
               "class MissingKey(KeyError):\n    pass\n\n\nclass FluxDB:").replace(
               "raise KeyError(key)", "raise MissingKey(key)")
Path("tasks/pool-v3/conv-fluxdb-semantics/wrong/wrong_01/fluxdb/__init__.py"
     ).write_text(w, encoding="utf-8")

print("三包 gold/wrong 全部基于中性化 fixture 重建")
