"""heldout 终验实例集 ×6（2026-09-29，A2 闭环最后一块）。

设计原则：
- 全新形态（装饰器参数/字典路径配置/类属性共享/时区天真性）——
  与 dev 池（函数重命名/常量迁移/缓存失效）不重合，防"对迭代任务过拟合"；
- 独立目录 tasks/heldout/，从未进入任何 dev 矩阵；
- 判分仍全部机器可判（隐藏 pytest + 双约束），部分分设计（多测试点）。

用法：python scripts/build_heldout_tasks.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_more_tasks import CONFTEST, make_patches, write  # noqa: E402

HOLDOUT = ROOT / "tasks" / "heldout"


def task(tid: str) -> Path:
    return HOLDOUT / tid


def finish(tid: str, meta: str, intent: str, steps: list) -> None:
    t = task(tid)
    write(t / "meta.yaml", meta)
    write(t / "INTENT.md", intent)
    make_patches(t / "fixture", steps, t / "solution" / "sites")


def wrong_from_fixture(tid: str, overrides: dict[str, str]) -> None:
    dst = task(tid) / "wrong" / "wrong_01"
    shutil.copytree(task(tid) / "fixture", dst, dirs_exist_ok=True)
    for rel, content in overrides.items():
        write(dst / rel, content)


# ============ h-d1-leap-01：闰年规则不全（单点）============

def build_h_d1_leap() -> None:
    tid = "h-d1-leap-01"
    write(task(tid) / "fixture" / "calendar.py", '''def days_in_month(year, month):
    """Return the number of days in the given month."""
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and year % 4 == 0:
        return 29
    return days[month - 1]
''')
    write(task(tid) / "fixture" / "README.md", "# h-d1-leap-01\n日历小工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_calendar.py", '''from calendar import days_in_month


def test_regular_leap():
    assert days_in_month(2024, 2) == 29


def test_century_not_leap():
    assert days_in_month(1900, 2) == 28


def test_quad_century_leap():
    assert days_in_month(2000, 2) == 29


def test_plain_month():
    assert days_in_month(2023, 1) == 31
''')
    wrong_from_fixture(tid, {"calendar.py": '''def days_in_month(year, month):
    """Return the number of days in the given month."""
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and year % 4 == 0 and year % 100 != 0:
        return 29
    return days[month - 1]
'''})
    finish(tid, '''task_id: h-d1-leap-01
difficulty: D1
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户报告：days_in_month(1900, 2) 返回 29，但 1900 年不是闰年（应为 28）。
  请修复闰年判定。
''', '''# 出题意图（h-d1-leap-01）

- 经典闰年规则（%100/%400）；错解只修 %100 漏 %400（2000 年挂）。
- 狙击 F17。
''', [("calendar.py", [("    if month == 2 and year % 4 == 0:\n        return 29",
                         "    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)\n"
                         "    if month == 2 and leap:\n        return 29")])])


# ============ h-d1-initials-01：取错字符（单点）============

def build_h_d1_initials() -> None:
    tid = "h-d1-initials-01"
    write(task(tid) / "fixture" / "names.py", '''def initials(name):
    """Return the initials of a full name, e.g. 'Ada Lovelace' -> 'A.L.'."""
    parts = name.split()
    return ".".join(p[1] for p in parts) + "."
''')
    write(task(tid) / "fixture" / "README.md", "# h-d1-initials-01\n姓名工具。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_names.py", '''from names import initials


def test_two_parts():
    assert initials("Ada Lovelace") == "A.L."


def test_single():
    assert initials("Prince") == "P."


def test_three_parts():
    assert initials("John Ronald Tolkien") == "J.R.T."
''')
    wrong_from_fixture(tid, {"names.py": '''def initials(name):
    """Return the initials of a full name, e.g. 'Ada Lovelace' -> 'A.L.'."""
    parts = name.split()
    return ".".join(p[-1] for p in parts) + "."
'''})
    finish(tid, '''task_id: h-d1-initials-01
difficulty: D1
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户报告：initials("Ada Lovelace") 期望 "A.L." 实际得到 "d.o."——
  取的是每个名字的第二个字母。请修复。
''', '''# 出题意图（h-d1-initials-01）

- off-by-one 取字符；错解取最后一个字母（单名测试抓住）。
- 狙击 F17。
''', [("names.py", [('".".join(p[1] for p in parts)',
                     '".".join(p[0].upper() for p in parts)')])])


# ============ h-d2-retry-01：装饰器签名迁移（5 处，2 处要 backoff）============

def build_h_d2_retry() -> None:
    tid = "h-d2-retry-01"
    write(task(tid) / "fixture" / "resil.py", '''def retry(times):
    raise RuntimeError("retry(times) removed; use retry(times, backoff)")


def retry_v2(times, backoff=1):
    """Decorator: mark a function with retry policy metadata."""
    def deco(fn):
        fn.retry_policy = {"times": times, "backoff": backoff}
        return fn
    return deco
''')
    write(task(tid) / "fixture" / "jobs" / "__init__.py", "")
    write(task(tid) / "fixture" / "jobs" / "sync.py", '''from resil import retry


@retry(3)
def sync_users():
    return "sync-users"


@retry(3)
def sync_orders():
    return "sync-orders"
''')
    write(task(tid) / "fixture" / "jobs" / "report.py", '''from resil import retry


@retry(5)
def monthly_report():
    return "report"
''')
    write(task(tid) / "fixture" / "jobs" / "util.py", '''from resil import retry as resilient


@resilient(2)
def ping_gateway():
    return "ping"
''')
    write(task(tid) / "fixture" / "jobs" / "chain.py", '''from jobs.common import retry


@retry(4)
def chained_job():
    return "chain"
''')
    write(task(tid) / "fixture" / "jobs" / "common.py", '''from resil import retry  # noqa: F401  (re-export)
''')
    write(task(tid) / "fixture" / "README.md", "# h-d2-retry-01\n任务调度库。\n")

    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_jobs.py", '''from jobs.sync import sync_users, sync_orders
from jobs.report import monthly_report
from jobs.util import ping_gateway
from jobs.chain import chained_job


def test_users_policy():
    assert sync_users.retry_policy == {"times": 3, "backoff": 1}


def test_orders_policy():
    assert sync_orders.retry_policy == {"times": 3, "backoff": 1}


def test_report_policy():
    assert monthly_report.retry_policy == {"times": 5, "backoff": 2}


def test_ping_policy():
    assert ping_gateway.retry_policy == {"times": 2, "backoff": 1}


def test_chain_policy():
    assert chained_job.retry_policy == {"times": 4, "backoff": 2}
''')
    wrong_from_fixture(tid, {
        "jobs/sync.py": '''from resil import retry_v2


@retry_v2(3)
def sync_users():
    return "sync-users"


@retry_v2(3)
def sync_orders():
    return "sync-orders"
''',
    })
    finish(tid, '''task_id: h-d2-retry-01
difficulty: D2
targets_fids: [F05, F09]
sites_required: 6
forbidden_edits: [tests/, _tests/]
prompt: |
  resil.retry(times) 已移除（装饰即抛 RuntimeError），新接口
  retry_v2(times, backoff)：report 和 chain 两处 backoff=2，其余默认 1。
  注意调用形式不止一种（别名导入、再导出都存在）。请迁移全部装饰点。
''', '''# 出题意图（h-d2-retry-01）

- 装饰器形态的多点迁移 + 两处差异化参数；别名/再导出各一处。
- 狙击 F05、F09；错解只改 sync.py 两处。
''', [
        ("jobs/sync.py", [("from resil import retry\n", "from resil import retry_v2\n"),
                          ("@retry(3)", "@retry_v2(3)")]),
        ("jobs/sync.py", [("@retry(3)\ndef sync_orders", "@retry_v2(3)\ndef sync_orders")]),
        ("jobs/report.py", [("from resil import retry\n", "from resil import retry_v2\n"),
                            ("@retry(5)", "@retry_v2(5, backoff=2)")]),
        ("jobs/util.py", [("from resil import retry as resilient", "from resil import retry_v2 as resilient"),
                          ("@resilient(2)", "@resilient(2)")]),
        ("jobs/common.py", [("from resil import retry  # noqa: F401  (re-export)",
                             "from resil import retry_v2 as retry  # noqa: F401  (re-export)")]),
        ("jobs/chain.py", [("@retry(4)", "@retry(4, backoff=2)")]),
    ])


# ============ h-d2-cfgpath-01：字典路径配置迁移（4 处）============

def build_h_d2_cfgpath() -> None:
    tid = "h-d2-cfgpath-01"
    write(task(tid) / "fixture" / "conf.py", '''def read_key(name):
    raise RuntimeError("read_key(name) removed; use read_path(section, name)")


def read_path(section, name):
    """Read a config value by section and key name."""
    table = {
        "database": {"host": "db.internal", "port": 5432},
        "cache": {"host": "cache.internal", "ttl": 60},
        "queue": {"host": "mq.internal", "ttl": 30},
    }
    return table[section][name]
''')
    write(task(tid) / "fixture" / "services" / "__init__.py", "")
    write(task(tid) / "fixture" / "services" / "db.py", '''from conf import read_key


def db_host():
    return read_key("db_host")
''')
    write(task(tid) / "fixture" / "services" / "cache.py", '''from conf import read_key


def cache_host():
    return read_key("cache_host")
''')
    write(task(tid) / "fixture" / "services" / "ttl.py", '''from conf import read_key as get


def cache_ttl():
    return get("cache_ttl")


def queue_ttl():
    return get("queue_ttl")
''')
    write(task(tid) / "fixture" / "README.md", "# h-d2-cfgpath-01\n配置读取库。\n")

    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_conf.py", '''from services.db import db_host
from services.cache import cache_host
from services.ttl import cache_ttl, queue_ttl


def test_db():
    assert db_host() == "db.internal"


def test_cache():
    assert cache_host() == "cache.internal"


def test_cache_ttl():
    assert cache_ttl() == 60


def test_queue_ttl():
    assert queue_ttl() == 30
''')
    wrong_from_fixture(tid, {
        "services/db.py": '''from conf import read_path


def db_host():
    return read_path("database", "host")
''',
    })
    finish(tid, '''task_id: h-d2-cfgpath-01
difficulty: D2
targets_fids: [F05, F09]
sites_required: 4
forbidden_edits: [tests/, _tests/]
prompt: |
  conf.read_key(name) 已移除（调用即抛 RuntimeError），改为
  read_path(section, name)：db_host→database.host、cache_host→cache.host、
  cache_ttl→cache.ttl、queue_ttl→queue.ttl。
  注意别名导入形式存在。请迁移全部调用点。
''', '''# 出题意图（h-d2-cfgpath-01）

- 扁平 key → 字典路径的双参数迁移；每处参数组合不同，一刀切必错；
  别名导入一处（ttl.py 内两处调用共用一个 import）。
- 狙击 F05、F09；错解只改 db.py。
''', [
        ("services/db.py", [("from conf import read_key", "from conf import read_path"),
                            ('return read_key("db_host")', 'return read_path("database", "host")')]),
        ("services/cache.py", [("from conf import read_key", "from conf import read_path"),
                               ('return read_key("cache_host")', 'return read_path("cache", "host")')]),
        ("services/ttl.py", [("from conf import read_key as get", "from conf import read_path as get"),
                             ('return get("cache_ttl")', 'return get("cache", "ttl")')]),
        ("services/ttl.py", [('return get("queue_ttl")', 'return get("queue", "ttl")')]),
    ])


# ============ h-d3-limiter-01：类属性共享（跨文件状态 + 双约束）============

def build_h_d3_limiter() -> None:
    tid = "h-d3-limiter-01"
    write(task(tid) / "fixture" / "limiter.py", '''class RateLimiter:
    calls = []

    def __init__(self, limit):
        self.limit = limit

    def allow(self):
        self.calls.append(1)
        return len(self.calls) <= self.limit
''')
    write(task(tid) / "fixture" / "README.md", "# h-d3-limiter-01\n限流器。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_limiter.py", '''from limiter import RateLimiter


def test_limiters_are_independent():
    a = RateLimiter(2)
    a.allow()
    b = RateLimiter(2)
    assert b.allow() is True
    assert b.allow() is True
    assert b.allow() is False


def test_own_accumulation():
    a = RateLimiter(3)
    assert a.allow() is True
    assert a.allow() is True
    assert a.allow() is True
    assert a.allow() is False


def test_new_instance_does_not_reset_existing():
    a = RateLimiter(2)
    a.allow()
    b = RateLimiter(2)  # noqa: F841 创建新实例不应清零 a 的计数
    assert a.allow() is True
    assert a.allow() is False
''')
    wrong_from_fixture(tid, {"limiter.py": '''class RateLimiter:
    calls = []

    def __init__(self, limit):
        self.limit = limit
        RateLimiter.calls.clear()

    def allow(self):
        self.calls.append(1)
        return len(self.calls) <= self.limit
'''})
    finish(tid, '''task_id: h-d3-limiter-01
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户反馈：多个限流器实例之间会"互相干扰"——一个实例用掉的额度会影响
  另一个实例。初步怀疑是调用方用错了。请先复现、定位根因并修复；
  注意每个实例必须独立计数且各自正常累积。
''', '''# 出题意图（h-d3-limiter-01）

- 根因是可变类属性共享；错解在 __init__ 里 clear()——新实例重置别人的
  计数（独立性过了但累积测试抓住）。
- 狙击 F17、F01。
''', [("limiter.py", [("    def __init__(self, limit):\n        self.limit = limit",
                        "    def __init__(self, limit):\n        self.limit = limit\n"
                        "        self.calls = []")])])


# ============ h-d3-tz-01：天真时区（表象误导 + 双约束）============

def build_h_d3_tz() -> None:
    tid = "h-d3-tz-01"
    write(task(tid) / "fixture" / "tokens.py", '''from datetime import datetime


def parse_ts(s):
    """Parse a UTC timestamp string."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def is_expired(s, now_utc):
    """now_utc is an aware datetime in UTC."""
    return parse_ts(s) < now_utc
''')
    write(task(tid) / "fixture" / "README.md", "# h-d3-tz-01\n令牌过期检查。\n")
    write(task(tid) / "tests" / "conftest.py", CONFTEST)
    write(task(tid) / "tests" / "test_tokens.py", '''from datetime import datetime, timezone

from tokens import parse_ts, is_expired


def test_expired_true():
    now = datetime(2024, 6, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert is_expired("2024-06-01 00:00:00", now) is True


def test_expired_false():
    now = datetime(2024, 6, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert is_expired("2024-06-01 00:00:02", now) is False


def test_parse_is_aware():
    assert parse_ts("2024-06-01 00:00:00").tzinfo is not None
''')
    wrong_from_fixture(tid, {"tokens.py": '''from datetime import datetime


def parse_ts(s):
    """Parse a UTC timestamp string."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def is_expired(s, now_utc):
    """now_utc is an aware datetime in UTC."""
    return parse_ts(s) < now_utc.replace(tzinfo=None)
'''})
    finish(tid, '''task_id: h-d3-tz-01
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  线上报错 TypeError: can't compare offset-naive and offset-aware datetimes，
  报错位置在 is_expired 的比较行，初步怀疑是比较写法的问题。
  请先复现、定位根因并修复；要求解析结果必须带 UTC 时区（不能 naive）。
''', '''# 出题意图（h-d3-tz-01）

- 报错在比较处（症状），根因在 parse_ts 没挂时区；
  错解把 now_utc 降级成 naive——比较能过但语义错了（aware 测试抓住）。
- 狙击 F17、F01。
''', [("tokens.py", [("from datetime import datetime",
                       "from datetime import datetime, timezone"),
                    ('    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")',
                     '    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)')])])


if __name__ == "__main__":
    builders = [build_h_d1_leap, build_h_d1_initials, build_h_d2_retry,
                build_h_d2_cfgpath, build_h_d3_limiter, build_h_d3_tz]
    for b in builders:
        b()
        print(f"built: {b.__name__}")
    print(f"\n共生成 {len(builders)} 个 heldout 任务（tasks/heldout/，与 dev 池隔离）")
    sys.exit(0)
