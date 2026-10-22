"""B1 纠偏：生成两个加料 pilot 任务（d2-enum-hard / d3-state-hard）。

加料逻辑（B1 pilot 结论，docs/EXPERIMENT_LOG.md）：
- d2-enum-hard：9 个调用点，其中 5 个是朴素 grep "fetch(" 找不到的形式
  （别名导入 / 再导出链 / functools.partial），逼"枚举纪律"成为胜负手；
- d3-state-hard：跨文件状态 bug + 误导症状（日志指向无关的 api.py），
  根因是 cache.py 的 key 规范化不一致，必须先复现（F17/F01 陷阱）。

用法：python scripts/build_hard_tasks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_more_tasks import CONFTEST, finish, task, write, wrong_from_fixture  # noqa: E402


def build_d2_enum_hard() -> None:
    tid = "d2-enum-hard"
    t = task(tid)

    write(t / "fixture" / "lib.py", '''def fetch(url):
    raise RuntimeError("fetch() has been removed; use fetch_v2(url, timeout)")


def fetch_v2(url, timeout):
    """Fetch data from url with timeout (seconds, required)."""
    return {"url": url, "timeout": timeout, "data": f"payload:{url}"}
''')
    write(t / "fixture" / "services" / "__init__.py", "")
    # 直接调用点 ×1（site-01）
    write(t / "fixture" / "services" / "users.py", '''from lib import fetch


def get_user(user_id):
    return fetch(f"https://api.internal/users/{user_id}")
''')
    # 直接调用点 ×2（site-02/03）
    write(t / "fixture" / "services" / "orders.py", '''from lib import fetch


def get_order(order_id):
    return fetch(f"https://api.internal/orders/{order_id}")


def list_orders():
    return fetch("https://api.internal/orders")
''')
    # 直接调用点 ×1（site-04）
    write(t / "fixture" / "cli.py", '''from lib import fetch


def status():
    return fetch("https://api.internal/status")
''')
    # 别名导入 ×2（site-05/06）——朴素 grep "fetch(" 找不到调用处
    write(t / "fixture" / "reports.py", '''from lib import fetch as api_call


def daily_report():
    return api_call("https://api.internal/reports/daily")


def weekly_report():
    return api_call("https://api.internal/reports/weekly")
''')
    # 再导出链 ×2（site-07/08）——common 集中导入，下游从 common 拿
    write(t / "fixture" / "services" / "common.py", '''from lib import fetch  # noqa: F401  (re-export)
''')
    write(t / "fixture" / "services" / "alpha.py", '''from services.common import fetch


def probe_alpha():
    return fetch("https://api.internal/alpha")
''')
    write(t / "fixture" / "services" / "beta.py", '''from services.common import fetch


def probe_beta():
    return fetch("https://api.internal/beta")
''')
    # functools.partial ×1（site-09）——grep "fetch(" 找不到
    write(t / "fixture" / "jobs.py", '''from functools import partial

from lib import fetch

get_health = partial(fetch, "https://api.internal/health")


def health():
    return get_health()
''')
    write(t / "fixture" / "README.md", "# d2-enum-hard\n内部服务调用库。\n")

    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_users.py", '''from services.users import get_user


def test_get_user():
    r = get_user(1)
    assert r["url"] == "https://api.internal/users/1" and r["timeout"] == 5
''')
    write(t / "tests" / "test_orders.py", '''from services.orders import get_order, list_orders


def test_get_order():
    assert get_order(7)["url"] == "https://api.internal/orders/7"


def test_list_orders():
    assert list_orders()["url"] == "https://api.internal/orders"
''')
    write(t / "tests" / "test_cli.py", '''from cli import status


def test_status():
    assert status()["url"] == "https://api.internal/status"
''')
    write(t / "tests" / "test_reports.py", '''from reports import daily_report, weekly_report


def test_daily():
    assert daily_report()["url"] == "https://api.internal/reports/daily"


def test_weekly():
    assert weekly_report()["url"] == "https://api.internal/reports/weekly"
''')
    write(t / "tests" / "test_probes.py", '''from services.alpha import probe_alpha
from services.beta import probe_beta


def test_alpha():
    assert probe_alpha()["url"] == "https://api.internal/alpha"


def test_beta():
    assert probe_beta()["url"] == "https://api.internal/beta"
''')
    write(t / "tests" / "test_jobs.py", '''from jobs import health


def test_health():
    assert health()["url"] == "https://api.internal/health"
''')

    # 错解：只修了 4 个直接调用点（grep "fetch(" 的典型结果），漏掉 5 个隐蔽点
    wrong_from_fixture(tid, {
        "services/users.py": '''from lib import fetch_v2


def get_user(user_id):
    return fetch_v2(f"https://api.internal/users/{user_id}", timeout=5)
''',
        "services/orders.py": '''from lib import fetch_v2


def get_order(order_id):
    return fetch_v2(f"https://api.internal/orders/{order_id}", timeout=5)


def list_orders():
    return fetch_v2("https://api.internal/orders", timeout=5)
''',
        "cli.py": '''from lib import fetch_v2


def status():
    return fetch_v2("https://api.internal/status", timeout=5)
''',
    })

    finish(tid, '''task_id: d2-enum-hard
difficulty: D2
targets_fids: [F05, F09]
sites_required: 10
forbidden_edits: [tests/, _tests/]
prompt: |
  当前仓库里旧 API fetch() 已废弃（调用即抛 RuntimeError），
  新 API 是 fetch_v2(url, timeout)。
  请把仓库中所有调用点迁移到新 API，保证所有功能恢复。
''', '''# 出题意图（d2-enum-hard）

- B1 纠偏版：d2-enum-01 对 haiku 太易（10/10）。本版 9 个调用点，5 个隐蔽：
  别名导入 ×2（reports.py）、再导出链 ×2（common→alpha/beta）、functools.partial ×1（jobs.py）。
- 狙击 F-ID：F05（漏改同模式调用点）。朴素 grep "fetch(" 只能找到 4 个直接点，
  必须系统性枚举（全局搜 import 关系/调用形式）才能找全——I2（最小化原则）应在此翻车。
- 每处漏改各有独立测试文件盯着（users/orders/cli/reports/probes/jobs）。
''', [
        ("services/users.py", [
            ("from lib import fetch", "from lib import fetch_v2"),
            ('return fetch(f"https://api.internal/users/{user_id}")',
             'return fetch_v2(f"https://api.internal/users/{user_id}", timeout=5)'),
        ]),
        ("services/orders.py", [
            ("from lib import fetch", "from lib import fetch_v2"),
            ('return fetch(f"https://api.internal/orders/{order_id}")',
             'return fetch_v2(f"https://api.internal/orders/{order_id}", timeout=5)'),
        ]),
        ("services/orders.py", [
            ('return fetch("https://api.internal/orders")',
             'return fetch_v2("https://api.internal/orders", timeout=5)'),
        ]),
        ("cli.py", [
            ("from lib import fetch", "from lib import fetch_v2"),
            ('return fetch("https://api.internal/status")',
             'return fetch_v2("https://api.internal/status", timeout=5)'),
        ]),
        ("reports.py", [
            ("from lib import fetch as api_call", "from lib import fetch_v2 as api_call"),
            ('return api_call("https://api.internal/reports/daily")',
             'return api_call("https://api.internal/reports/daily", timeout=5)'),
        ]),
        ("reports.py", [
            ('return api_call("https://api.internal/reports/weekly")',
             'return api_call("https://api.internal/reports/weekly", timeout=5)'),
        ]),
        ("services/common.py", [
            ("from lib import fetch  # noqa: F401  (re-export)",
             "from lib import fetch_v2 as fetch  # noqa: F401  (re-export, keep name)"),
        ]),
        ("services/alpha.py", [
            ('return fetch("https://api.internal/alpha")',
             'return fetch("https://api.internal/alpha", timeout=5)'),
        ]),
        ("services/beta.py", [
            ('return fetch("https://api.internal/beta")',
             'return fetch("https://api.internal/beta", timeout=5)'),
        ]),
        ("jobs.py", [
            ("from lib import fetch", "from lib import fetch_v2 as fetch"),
            ('get_health = partial(fetch, "https://api.internal/health")',
             'get_health = partial(fetch, "https://api.internal/health", timeout=5)'),
        ]),
    ])


def build_d3_state_hard() -> None:
    tid = "d3-state-hard"
    t = task(tid)

    write(t / "fixture" / "cache.py", '''_cache = {}


def cached_price(item, loader):
    if item not in _cache:
        _cache[item] = loader()
    return _cache[item]


def invalidate(item):
    # 失效时按小写键清理
    _cache.pop(item.lower(), None)
''')
    write(t / "fixture" / "store.py", '''from cache import cached_price, invalidate

_DB = {"Apple": 3.5, "Pear": 4.2, "Melon": 6.0}


def read_price(item):
    return cached_price(item, lambda: _DB[item])


def write_price(item, price):
    _DB[item] = price
    invalidate(item)
''')
    write(t / "fixture" / "api.py", '''def serialize_price(item, price):
    """序列化价格输出。注意：这个函数看起来可疑但是是正确的。"""
    # 保留两位小数（银行家舍入），历史行为，不要动
    text = f"{price:.2f}"
    return {"item": item, "price_text": text, "ok": True}
''')
    write(t / "fixture" / "service.py", '''from api import serialize_price
from store import read_price, write_price


def get_price(item):
    return serialize_price(item, read_price(item))


def update_price(item, price):
    write_price(item, price)
    return serialize_price(item, read_price(item))
''')
    write(t / "fixture" / "README.md", '''# d3-state-hard
商品价格服务。
已知用户报告：更新价格后接口仍返回旧价格，错误日志指向 api.py 的 serialize 附近。
''')
    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_service.py", '''from service import get_price, update_price


def test_initial_read():
    assert get_price("Apple")["price_text"] == "3.50"


def test_update_is_visible():
    get_price("Pear")  # 先读一次让缓存变暖（不预热则更新后首次读取必然回源，bug 不显形）
    update_price("Pear", 9.9)
    assert get_price("Pear")["price_text"] == "9.90"


def test_serialize_behavior_unchanged():
    # api.serialize_price 的行为必须保持（防止改错位置蒙混）
    from api import serialize_price
    assert serialize_price("x", 1.005)["price_text"] == "1.00"
    assert serialize_price("x", 7.5)["ok"] is True
''')
    # 错解：去改 api.py 的舍入（治症状），缓存问题依旧
    wrong_from_fixture(tid, {
        "api.py": '''def serialize_price(item, price):
    """序列化价格输出。"""
    text = f"{round(price, 2):.2f}"
    return {"item": item, "price_text": text, "ok": True}
''',
    })

    finish(tid, '''task_id: d3-state-hard
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  用户报告：调用 update_price 更新商品价格后，get_price 仍返回更新前的旧价格。
  错误日志指向 api.py 的 serialize_price 附近。
  请定位并修复这个问题。
''', '''# 出题意图（d3-state-hard）

- B1 纠偏版：d3-cache-01 对 haiku 太易（10/10）。本版为跨文件状态 bug + 误导症状。
- 表面症状：更新后读不到新值；日志（README）指向 api.py 的 serialize_price
  （里面故意有个"看起来可疑"的银行家舍入，引诱改它 → F17 治症状）。
- 真实根因：cache.py invalidate 按 item.lower() 清缓存，而 cached_price 按原始 item 存
  （_DB 键为首字母大写 "Apple"/"Pear"），键大小写不一致导致失效失败——
  必须先复现（F01）并读懂数据流才能定位。
- 防蒙混：test_serialize_behavior_unchanged 盯住 api.py 行为，改它反而判负。
- 狙击 F-ID：F17（治症状）、F01（未复现就动手）。
''', [
        ("cache.py", [
            ('''def invalidate(item):
    # 失效时按小写键清理
    _cache.pop(item.lower(), None)''',
             '''def invalidate(item):
    _cache.pop(item, None)'''),
        ]),
    ])


if __name__ == "__main__":
    build_d2_enum_hard()
    build_d3_state_hard()
    print("加料 pilot 任务已生成：d2-enum-hard, d3-state-hard")
