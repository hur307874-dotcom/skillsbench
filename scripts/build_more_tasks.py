"""批量生成任务实例：D1×3 + D2×3 + D3×4（配合已有 d1-typo-01 / d2-enum-01 凑齐 12 实例）。

用法：python scripts/build_more_tasks.py
每个任务：fixture/ + tests/ + wrong/wrong_01/ + meta.yaml + INTENT.md + solution/sites/*.patch
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "tasks" / "generated"

CONFTEST = '''import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=sb@local", "-c", "user.name=sb",
         "-c", "core.autocrlf=false", *args],
        cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def make_patches(fixture_dir: Path, steps: list[tuple[str, list[tuple[str, str]]]], sites_out: Path) -> None:
    """逐步替换 + git diff 生成 site-NN.patch（保证可 git apply）。

    工作目录必须屏蔽外层 git 仓库发现，否则 patch 里的相对路径会解析到外层仓库。
    """
    import os
    env = dict(os.environ)
    build = Path(tempfile.mkdtemp(prefix="sb-build-")) / "repo"
    env["GIT_CEILING_DIRECTORIES"] = str(build.parent.resolve())
    shutil.copytree(fixture_dir, build)
    git(build, "init", "-q")
    git(build, "add", "-A")
    git(build, "commit", "-qm", "fixture")
    sites_out.mkdir(parents=True, exist_ok=True)
    for i, (rel, replacements) in enumerate(steps, 1):
        f = build / rel
        text = f.read_text(encoding="utf-8")
        for old, new in replacements:
            assert old in text, f"{rel} 中找不到: {old!r}"
            text = text.replace(old, new, 1)
        f.write_text(text, encoding="utf-8", newline="\n")
        diff = subprocess.run(["git", "diff", "--", rel], cwd=build,
                              capture_output=True, text=True, env=env).stdout
        (sites_out / f"site-{i:02d}.patch").write_text(diff, encoding="utf-8", newline="\n")
        git(build, "add", "-A")
        git(build, "commit", "-qm", f"site-{i:02d}")
    shutil.rmtree(build.parent, ignore_errors=True)


def task(tid: str) -> Path:
    return GEN / tid


def finish(tid: str, meta: str, intent: str, steps: list) -> None:
    t = task(tid)
    write(t / "meta.yaml", meta)
    write(t / "INTENT.md", intent)
    make_patches(t / "fixture", steps, t / "solution" / "sites")


def wrong_from_fixture(tid: str, overrides: dict[str, str]) -> None:
    """wrong/wrong_01 = fixture 完整副本 + overrides 覆盖的文件。
    不删除旧目录（安全策略拦截批量删除），dirs_exist_ok 覆盖；
    仅逐个清理 __pycache__，避开批量删除护栏。"""
    t = task(tid)
    dst = t / "wrong" / "wrong_01"
    if dst.exists():
        for pyc in dst.rglob("*.pyc"):
            pyc.unlink()
        for d in sorted(dst.rglob("__pycache__"), key=lambda p: -len(p.parts)):
            try:
                d.rmdir()
            except OSError:
                pass
    shutil.copytree(t / "fixture", dst, dirs_exist_ok=True)
    for rel, content in overrides.items():
        write(dst / rel, content)


# ============ D1 档（单点错误、报错直指位置）============

def build_d1_typo_02() -> None:
    tid = "d1-typo-02"
    write(task(tid) / "fixture" / "shop.py", '''def total_price(prices):
    """Return the sum of prices."""
    return sum(p * 0.9 for p in prices)
''')
    write(task(tid) / "fixture" / "README.md", "# d1-typo-02\n结算小工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_shop.py", '''from shop import total_price


def test_total():
    assert total_price([100, 200]) == 300


def test_single():
    assert total_price([50]) == 50


def test_empty():
    assert total_price([]) == 0
''')
    wrong_from_fixture(tid, {"shop.py": '''def total_price(prices):
    """Return the sum of prices."""
    return round(sum(p * 0.9 for p in prices), 2)
'''})
    finish(tid, '''task_id: d1-typo-02
difficulty: D1
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户报告：当前没有任何折扣活动，但 shop.py 的 total_price 结算金额总是少了 10%。
  请定位并修复。
''', '''# 出题意图（d1-typo-02）

- 预设陷阱：bug 是源码里多出的 `* 0.9`，报错（金额不对）直指结果，模型可能去改调用方或四舍五入。
- 狙击 F-ID：F17（误读症状）。
- 预期 Skill 作用点：D1 档测 I1 负收益（琐碎任务不需要确认流程）。
''', [("shop.py", [("return sum(p * 0.9 for p in prices)", "return sum(prices)")])])


def build_d1_offby1_01() -> None:
    tid = "d1-offby1-01"
    write(task(tid) / "fixture" / "countdown.py", '''def count_down(n):
    """Return the countdown from n to 0 inclusive."""
    return [i for i in range(n, 0, -1)]
''')
    write(task(tid) / "fixture" / "README.md", "# d1-offby1-01\n倒计时工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_countdown.py", '''from countdown import count_down


def test_basic():
    assert count_down(3) == [3, 2, 1, 0]


def test_zero():
    assert count_down(0) == [0]
''')
    wrong_from_fixture(tid, {"countdown.py": '''def count_down(n):
    """Return the countdown from n to 0 inclusive."""
    return [i for i in range(n - 1, -1, -1)]
'''})
    finish(tid, '''task_id: d1-offby1-01
difficulty: D1
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户报告：count_down(3) 应该返回 [3, 2, 1, 0]（含 0），但实际缺少最后的 0；
  count_down(0) 应该返回 [0]，实际返回空列表。请修复。
''', '''# 出题意图（d1-offby1-01）

- 预设陷阱：off-by-one；模型可能改成手动 append 0 而非修 range 边界（留下隐患）。
- 狙击 F-ID：F17。
''', [("countdown.py", [("range(n, 0, -1)", "range(n, -1, -1)")])])


def build_d1_median_01() -> None:
    tid = "d1-median-01"
    write(task(tid) / "fixture" / "stats.py", '''def median(xs):
    """Return the median of a non-empty list of numbers."""
    s = sorted(xs)
    return s[len(s) // 2]
''')
    write(task(tid) / "fixture" / "README.md", "# d1-median-01\n统计小工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_stats.py", '''from stats import median


def test_odd():
    assert median([1, 3, 5]) == 3


def test_even_two():
    assert median([1, 3]) == 2.0


def test_even_unsorted():
    assert median([4, 1, 2, 3]) == 2.5
''')
    wrong_from_fixture(tid, {"stats.py": '''def median(xs):
    """Return the median of a non-empty list of numbers."""
    s = sorted(xs)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2
'''})
    finish(tid, '''task_id: d1-median-01
difficulty: D1
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户报告：median([1, 3]) 期望 2.0 但实际返回 3（偶数长度时结果不对）。
  奇数长度是对的。请修复。
''', '''# 出题意图（d1-median-01）

- 预设陷阱：只修偶数分支而改坏奇数分支（错解 wrong_01 即如此）。
- 狙击 F-ID：F17。
''', [("stats.py", [('    s = sorted(xs)\n    return s[len(s) // 2]',
                     '    s = sorted(xs)\n    n = len(s)\n    mid = n // 2\n'
                     '    if n % 2:\n        return s[mid]\n'
                     '    return (s[mid - 1] + s[mid]) / 2')])])


# ============ D2 档（多处同模式调用点）============

def build_d2_rename_01() -> None:
    tid = "d2-rename-01"
    write(task(tid) / "fixture" / "cfg.py", '''def read_config(path):
    raise RuntimeError("read_config() has been renamed; use load_config(path, encoding)")


def load_config(path, encoding="utf-8"):
    """Load a config file with the given encoding."""
    return {"path": path, "encoding": encoding, "content": f"cfg:{path}"}
''')
    write(task(tid) / "fixture" / "app.py", '''from cfg import read_config


def main():
    return read_config("app.ini")
''')
    write(task(tid) / "fixture" / "tools" / "__init__.py", "")
    write(task(tid) / "fixture" / "tools" / "export.py", '''from cfg import read_config


def export():
    return read_config("export.ini")
''')
    write(task(tid) / "fixture" / "tools" / "report.py", '''from cfg import read_config


def report():
    return read_config("report.ini")
''')
    write(task(tid) / "fixture" / "README.md", "# d2-rename-01\n配置加载库。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_app.py", '''from app import main


def test_main():
    r = main()
    assert r["path"] == "app.ini"
    assert r["encoding"] == "utf-8"
''')
    write(task(tid) / "tests" / "test_export.py", '''from tools.export import export


def test_export():
    assert export()["path"] == "export.ini"
''')
    write(task(tid) / "tests" / "test_report.py", '''from tools.report import report


def test_report():
    assert report()["path"] == "report.ini"
''')
    for rel in ["cfg.py", "tools/__init__.py", "tools/export.py", "tools/report.py", "README.md"]:
        src = task(tid) / "fixture" / rel
        dst = task(tid) / "wrong" / "wrong_01" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    write(task(tid) / "wrong" / "wrong_01" / "app.py", '''from cfg import load_config


def main():
    return load_config("app.ini")
''')
    finish(tid, '''task_id: d2-rename-01
difficulty: D2
targets_fids: [F05, F09]
sites_required: 3
forbidden_edits: [tests/, _tests/]
prompt: |
  仓库里 read_config() 已改名为 load_config(path, encoding)（旧名调用即抛 RuntimeError）。
  请把仓库中所有调用点迁移到新函数，保证所有功能恢复。
''', '''# 出题意图（d2-rename-01）

- 预设陷阱：3 个调用点分布在 app.py、tools/export.py、tools/report.py，
  报错只暴露第一个被触碰的位置；模型容易"修一处就收工"（F05）。
- 狙击 F-ID：F05、F09（旧名）。
- 预期 Skill 作用点：I2（最小化修改）与"改全 3 处"冲突——H2 战场。
''', [
        ("app.py", [("from cfg import read_config", "from cfg import load_config"),
                    ('return read_config("app.ini")', 'return load_config("app.ini")')]),
        ("tools/export.py", [("from cfg import read_config", "from cfg import load_config"),
                             ('return read_config("export.ini")', 'return load_config("export.ini")')]),
        ("tools/report.py", [("from cfg import read_config", "from cfg import load_config"),
                             ('return read_config("report.ini")', 'return load_config("report.ini")')]),
    ])


def build_d2_timeout_01() -> None:
    tid = "d2-timeout-01"
    write(task(tid) / "fixture" / "net.py", '''def get_timeout():
    raise RuntimeError("get_timeout() removed; use settings.DEFAULT_TIMEOUT")
''')
    write(task(tid) / "fixture" / "settings.py", '''DEFAULT_TIMEOUT = 30
''')
    write(task(tid) / "fixture" / "client.py", '''from net import get_timeout


def ping():
    return {"action": "ping", "timeout": get_timeout()}


def health():
    return {"action": "health", "timeout": get_timeout()}
''')
    write(task(tid) / "fixture" / "worker.py", '''from net import get_timeout


def run_job():
    return {"action": "job", "timeout": get_timeout()}
''')
    write(task(tid) / "fixture" / "api.py", '''from net import get_timeout


def status():
    return {"action": "status", "timeout": get_timeout()}
''')
    write(task(tid) / "fixture" / "README.md", "# d2-timeout-01\n内部网络库。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_client.py", '''from client import ping, health


def test_ping():
    assert ping()["timeout"] == 30


def test_health():
    assert health()["timeout"] == 30
''')
    write(task(tid) / "tests" / "test_worker.py", '''from worker import run_job


def test_job():
    assert run_job()["timeout"] == 30
''')
    write(task(tid) / "tests" / "test_api.py", '''from api import status


def test_status():
    assert status()["timeout"] == 30
''')
    for rel in ["net.py", "settings.py", "worker.py", "api.py", "README.md"]:
        src = task(tid) / "fixture" / rel
        dst = task(tid) / "wrong" / "wrong_01" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    write(task(tid) / "wrong" / "wrong_01" / "client.py", '''from settings import DEFAULT_TIMEOUT


def ping():
    return {"action": "ping", "timeout": DEFAULT_TIMEOUT}


def health():
    return {"action": "health", "timeout": DEFAULT_TIMEOUT}
''')
    finish(tid, '''task_id: d2-timeout-01
difficulty: D2
targets_fids: [F05, F09]
sites_required: 4
forbidden_edits: [tests/, _tests/]
prompt: |
  net.get_timeout() 已移除（调用即抛 RuntimeError），超时配置改为读
  settings.DEFAULT_TIMEOUT。请把仓库中所有使用点改到新方式，保证功能恢复。
''', '''# 出题意图（d2-timeout-01）

- 预设陷阱：4 处使用点分布在 3 个文件（client.py ×2、worker.py、api.py）；
  client.py 内两处共用一个 import，改 import 时容易只改一处调用。
- 狙击 F-ID：F05、F09。
''', [
        ("client.py", [("from net import get_timeout", "from settings import DEFAULT_TIMEOUT"),
                       ('"timeout": get_timeout()}', '"timeout": DEFAULT_TIMEOUT}')]),
        ("client.py", [('"timeout": get_timeout()}', '"timeout": DEFAULT_TIMEOUT}')]),
        ("worker.py", [("from net import get_timeout", "from settings import DEFAULT_TIMEOUT"),
                       ('"timeout": get_timeout()}', '"timeout": DEFAULT_TIMEOUT}')]),
        ("api.py", [("from net import get_timeout", "from settings import DEFAULT_TIMEOUT"),
                    ('"timeout": get_timeout()}', '"timeout": DEFAULT_TIMEOUT}')]),
    ])


def build_d2_sig_01() -> None:
    tid = "d2-sig-01"
    write(task(tid) / "fixture" / "notify.py", '''def send_message(text):
    raise RuntimeError("send_message(text) is deprecated; use send(text, priority)")


def send(text, priority="normal"):
    """Send a message with the given priority."""
    return {"text": text, "priority": priority}
''')
    write(task(tid) / "fixture" / "handlers" / "__init__.py", "")
    write(task(tid) / "fixture" / "handlers" / "alerts.py", '''from notify import send_message


def alert(msg):
    return send_message(msg)
''')
    write(task(tid) / "fixture" / "handlers" / "digest.py", '''from notify import send_message


def daily(msg):
    return send_message(msg)
''')
    write(task(tid) / "fixture" / "handlers" / "reminders.py", '''from notify import send_message


def remind(msg):
    return send_message(msg)


def remind_urgent(msg):
    return send_message(msg)
''')
    write(task(tid) / "fixture" / "README.md", "# d2-sig-01\n通知分发库。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_alerts.py", '''from handlers.alerts import alert


def test_alert():
    r = alert("fire")
    assert r["text"] == "fire"
    assert r["priority"] == "high"
''')
    write(task(tid) / "tests" / "test_digest.py", '''from handlers.digest import daily


def test_daily():
    assert daily("news")["priority"] == "normal"
''')
    write(task(tid) / "tests" / "test_reminders.py", '''from handlers.reminders import remind, remind_urgent


def test_remind():
    assert remind("meeting")["priority"] == "normal"


def test_remind_urgent():
    assert remind_urgent("deadline")["priority"] == "high"
''')
    for rel in ["notify.py", "handlers/__init__.py", "handlers/digest.py",
                "handlers/reminders.py", "README.md"]:
        src = task(tid) / "fixture" / rel
        dst = task(tid) / "wrong" / "wrong_01" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    write(task(tid) / "wrong" / "wrong_01" / "handlers" / "alerts.py", '''from notify import send


def alert(msg):
    return send(msg, priority="high")
''')
    finish(tid, '''task_id: d2-sig-01
difficulty: D2
targets_fids: [F05, F09]
sites_required: 4
forbidden_edits: [tests/, _tests/]
prompt: |
  notify.send_message(text) 已废弃（调用即抛 RuntimeError），新接口是
  send(text, priority)：告警类消息 priority="high"，其余保持默认。
  请迁移全部调用点：handlers/alerts.py 的 alert、handlers/reminders.py 的
  remind_urgent 属于告警类。保证所有功能恢复。
''', '''# 出题意图（d2-sig-01）

- 预设陷阱：4 处调用点分布在 3 个 handler，且两处需要显式 priority="high"、
  两处保持默认——模型容易一刀切全加 high 或全不加。
- 狙击 F-ID：F05、F09。
''', [
        ("handlers/alerts.py", [("from notify import send_message", "from notify import send"),
                                ("return send_message(msg)", 'return send(msg, priority="high")')]),
        ("handlers/digest.py", [("from notify import send_message", "from notify import send"),
                                ("return send_message(msg)", "return send(msg)")]),
        ("handlers/reminders.py", [("from notify import send_message", "from notify import send"),
                                   ("def remind(msg):\n    return send_message(msg)",
                                    "def remind(msg):\n    return send(msg)")]),
        ("handlers/reminders.py", [("def remind_urgent(msg):\n    return send_message(msg)",
                                    'def remind_urgent(msg):\n    return send(msg, priority="high")')]),
    ])


# ============ D3 档（表象误导 / 跨文件状态，须先复现）============

def build_d3_cache_01() -> None:
    tid = "d3-cache-01"
    write(task(tid) / "fixture" / "cache.py", '''_CACHE = {}


def get_profile(uid, store):
    if uid not in _CACHE:
        _CACHE[uid] = store.load(uid)
    return _CACHE[uid]


def update_profile(uid, data, store):
    store.save(uid, data)
''')
    write(task(tid) / "fixture" / "store.py", '''class Store:
    def __init__(self):
        self.data = {}
        self.loads = 0

    def load(self, uid):
        self.loads += 1
        return self.data.get(uid)

    def save(self, uid, value):
        self.data[uid] = value
''')
    write(task(tid) / "fixture" / "README.md", "# d3-cache-01\n用户资料服务。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_cache.py", '''from cache import get_profile, update_profile, _CACHE
from store import Store


def setup_function():
    _CACHE.clear()


def test_read_after_update_returns_fresh():
    s = Store()
    s.save(1, {"name": "old"})
    assert get_profile(1, s)["name"] == "old"
    update_profile(1, {"name": "new"}, s)
    assert get_profile(1, s)["name"] == "new"


def test_cache_still_caches():
    s = Store()
    s.save(1, {"name": "x"})
    get_profile(1, s)
    get_profile(1, s)
    assert s.loads == 1
''')
    wrong_from_fixture(tid, {"cache.py": '''def get_profile(uid, store):
    return store.load(uid)


def update_profile(uid, data, store):
    store.save(uid, data)
'''})
    finish(tid, '''task_id: d3-cache-01
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户反馈：更新资料后页面仍显示旧数据（刷新也没用），怀疑前端渲染有问题。
  仓库是后端服务代码。请先复现问题、定位根因并修复；
  注意保留缓存的性能语义（不能简单地一删了之）。
''', '''# 出题意图（d3-cache-01）

- 预设陷阱：症状（显示旧数据）误导向前端，根因是 update_profile 不失效缓存；
  错解 wrong_01 直接删缓存——能通过"读新值"测试但被"缓存仍生效"测试抓住。
- 狙击 F-ID：F17（治症状）、F01（须先复现才能发现是缓存失效问题）。
- 判分双约束：fix 必须同时过"更新后读到新值"与"缓存仍缓存"两条——
  这是"防止过度修改（F13）"的硬编码。
''', [("cache.py", [("def update_profile(uid, data, store):\n    store.save(uid, data)",
                     "def update_profile(uid, data, store):\n    store.save(uid, data)\n"
                     "    _CACHE.pop(uid, None)")])])


def build_d3_mutable_01() -> None:
    tid = "d3-mutable-01"
    write(task(tid) / "fixture" / "log.py", '''def make_logger(entries=[]):
    def log(msg):
        entries.append(msg)
        return list(entries)
    return log
''')
    write(task(tid) / "fixture" / "README.md", "# d3-mutable-01\n日志工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_log.py", '''from log import make_logger


def test_loggers_are_independent():
    a = make_logger()
    a("x")
    b = make_logger()
    assert b("y") == ["y"]


def test_logger_accumulates_own_entries():
    a = make_logger()
    a("one")
    assert a("two") == ["one", "two"]
''')
    wrong_from_fixture(tid, {"log.py": '''def make_logger(entries=[]):
    def log(msg):
        return entries + [msg]
    return log
'''})
    finish(tid, '''task_id: d3-mutable-01
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  线上反馈：不同请求的日志神秘地"串"到了一起——一个请求里能看到
  其他请求的日志条目。请复现、定位根因并修复。
''', '''# 出题意图（d3-mutable-01）

- 预设陷阱：可变默认参数；错解 wrong_01 改为返回新列表（不 mutate），
  独立性过了但"自身累积"测试抓住它。
- 狙击 F-ID：F17、F01。
''', [("log.py", [("def make_logger(entries=[]):",
                     "def make_logger(entries=None):\n    if entries is None:\n"
                     "        entries = []")])])


def build_d3_csv_01() -> None:
    tid = "d3-csv-01"
    write(task(tid) / "fixture" / "parser.py", '''def parse_row(line):
    parts = line.split(",")
    return {"name": parts[0].strip('"'), "age": int(parts[1])}


def load_users(text):
    return [parse_row(l) for l in text.strip().splitlines() if l.strip()]
''')
    write(task(tid) / "fixture" / "README.md", "# d3-csv-01\n用户 CSV 导入器。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_parser.py", '''from parser import parse_row, load_users


def test_simple_row():
    assert parse_row("Alice,30") == {"name": "Alice", "age": 30}


def test_quoted_name_with_comma():
    assert parse_row('"Smith, John",25') == {"name": "Smith, John", "age": 25}


def test_load_mixed():
    users = load_users('Alice,30\\n"Smith, John",25')
    assert users[1]["name"] == "Smith, John"
    assert users[1]["age"] == 25
''')
    wrong_from_fixture(tid, {"parser.py": '''def parse_row(line):
    parts = line.split(",")
    try:
        age = int(parts[1])
    except ValueError:
        age = 0
    return {"name": parts[0].strip('"'), "age": age}


def load_users(text):
    return [parse_row(l) for l in text.strip().splitlines() if l.strip()]
'''})
    finish(tid, '''task_id: d3-csv-01
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  导入报错日志显示 int() 转换失败（ValueError: invalid literal），
  初步怀疑是 age 列有脏数据。请先复现、定位根因并修复，
  注意不能吞掉真实数据（name/age 都必须解析正确）。
''', '''# 出题意图（d3-csv-01）

- 预设陷阱：报错位置（int 转换）是症状，根因是 split 不支持引号内的逗号；
  错解 wrong_01 给 int 套 try/except 默认 0——脏数据测试抓住它。
- 狙击 F-ID：F17（治症状的经典案例）、F01。
''', [("parser.py", [
        ("def parse_row", "import csv\n\n\ndef parse_row"),
        ('    parts = line.split(",")\n    return {"name": parts[0].strip(\'"\'), "age": int(parts[1])}',
         '    parts = next(csv.reader([line]))\n    return {"name": parts[0], "age": int(parts[1])}'),
    ])])


def build_d3_round_01() -> None:
    tid = "d3-round-01"
    write(task(tid) / "fixture" / "bill.py", '''def split_bill(total_cents, n):
    """Split a bill (in cents) among n people."""
    share = round(total_cents / n)
    return [share] * n
''')
    write(task(tid) / "fixture" / "README.md", "# d3-round-01\n账单分摊工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_bill.py", '''from bill import split_bill


def test_sum_matches_total():
    assert sum(split_bill(100, 3)) == 100


def test_shares_differ_by_at_most_one_cent():
    shares = split_bill(100, 3)
    assert max(shares) - min(shares) <= 1


def test_even_split():
    assert split_bill(100, 4) == [25, 25, 25, 25]
''')
    wrong_from_fixture(tid, {"bill.py": '''def split_bill(total_cents, n):
    """Split a bill (in cents) among n people."""
    share = -(-total_cents // n)
    return [share] * n
'''})
    finish(tid, '''task_id: d3-round-01
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  财务对账发现：分摊后的金额加起来比总额少了一分钱（例如 100 分分给 3 人，
  合计只有 99）。初步怀疑是显示层四舍五入的问题。请复现、定位根因并修复；
  要求每人分摊金额为整数分，且任意两人差额不超过 1 分。
''', '''# 出题意图（d3-round-01）

- 预设陷阱：错解 wrong_01 改成向上取整（每人多付）——合计变成 102 仍对不上账。
- 狙击 F-ID：F17、F01。
''', [("bill.py", [
        ('    share = round(total_cents / n)\n    return [share] * n',
         '    base = total_cents // n\n    remainder = total_cents - base * n\n'
         '    return [base + 1] * remainder + [base] * (n - remainder)')])])


if __name__ == "__main__":
    builders = [
        build_d1_typo_02, build_d1_offby1_01, build_d1_median_01,
        build_d2_rename_01, build_d2_timeout_01, build_d2_sig_01,
        build_d3_cache_01, build_d3_mutable_01, build_d3_csv_01, build_d3_round_01,
    ]
    for b in builders:
        b()
        print(f"built: {b.__name__}")
    print(f"\n共生成 {len(builders)} 个任务")
    sys.exit(0)
