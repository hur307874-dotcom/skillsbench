"""第二批 hard 任务变体（2026-09-28，pi-ql1 显示 11/12 满分后扩编）。

设计原则同 build_hard_tasks.py：
- D2：多处同模式调用点 + 朴素 grep 找不到的隐蔽形式（别名/再导出/partial）；
- D3：跨文件状态 / 表象误导 + 双约束判分（错解必被抓）。

用法：python scripts/build_hard_tasks2.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_more_tasks import CONFTEST, finish, task, write, wrong_from_fixture  # noqa: E402


def copy_fixture_except(tid: str, overrides: dict[str, str]) -> None:
    """wrong/wrong_01 = fixture 副本 + overrides 覆盖（避开删除护栏）。"""
    t = task(tid)
    dst = t / "wrong" / "wrong_01"
    shutil.copytree(t / "fixture", dst, dirs_exist_ok=True)
    for rel, content in overrides.items():
        write(dst / rel, content)


# ============ d2-sig-hard：签名迁移 6 调用点（2 处要 priority，4 处默认）============

def build_d2_sig_hard() -> None:
    tid = "d2-sig-hard"
    t = task(tid)
    write(t / "fixture" / "notify.py", '''def send_message(text):
    raise RuntimeError("send_message(text) removed; use send(text, priority)")


def send(text, priority="normal"):
    """Send a message with the given priority."""
    return {"text": text, "priority": priority}
''')
    write(t / "fixture" / "handlers" / "__init__.py", "")
    write(t / "fixture" / "handlers" / "alerts.py", '''from notify import send_message


def alert(msg):
    return send_message(msg)
''')
    write(t / "fixture" / "handlers" / "digest.py", '''from notify import send_message


def daily(msg):
    return send_message(msg)
''')
    write(t / "fixture" / "handlers" / "util.py", '''from notify import send_message as emit


def ping(msg):
    return emit(msg)
''')
    write(t / "fixture" / "handlers" / "common.py", '''from notify import send_message  # noqa: F401  (re-export)
''')
    write(t / "fixture" / "handlers" / "chain.py", '''from handlers.common import send_message


def chain_send(msg):
    return send_message(msg)
''')
    write(t / "fixture" / "handlers" / "jobs.py", '''from functools import partial

from notify import send_message

urgent = partial(send_message)


def urgent_alert(msg):
    return urgent(msg)
''')
    write(t / "fixture" / "README.md", "# d2-sig-hard\n通知分发库。\n")

    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_handlers.py", '''from handlers.alerts import alert
from handlers.digest import daily
from handlers.util import ping
from handlers.chain import chain_send
from handlers.jobs import urgent_alert


def test_alert_is_high():
    assert alert("fire")["priority"] == "high"


def test_daily_default():
    assert daily("news")["priority"] == "normal"


def test_ping_default():
    assert ping("ok")["priority"] == "normal"


def test_chain_default():
    assert chain_send("c")["priority"] == "normal"


def test_urgent_is_high():
    assert urgent_alert("ddl")["priority"] == "high"
''')
    copy_fixture_except(tid, {
        "handlers/alerts.py": '''from notify import send


def alert(msg):
    return send(msg, priority="high")
''',
        "handlers/digest.py": '''from notify import send


def daily(msg):
    return send(msg)
''',
    })
    finish(tid, '''task_id: d2-sig-hard
difficulty: D2
targets_fids: [F05, F09]
sites_required: 6
forbidden_edits: [tests/, _tests/]
prompt: |
  notify.send_message(text) 已移除（调用即抛 RuntimeError），新接口 send(text, priority)。
  告警类消息（alert、urgent_alert）priority="high"，其余保持默认。
  注意仓库里调用形式不止一种（别名导入、再导出、partial 都可能存在）。
  请迁移全部调用点，保证所有功能恢复。
''', '''# 出题意图（d2-sig-hard）

- 6 个调用点 5 种形式：直接 ×2、别名 ×1、再导出链 ×1、partial ×1；
  两处要显式 high、四处保持默认——一刀切必错。
- 狙击 F05（漏改隐蔽调用点）、F09；错解只改两个直接调用点。
''', [
        ("handlers/alerts.py", [("from notify import send_message", "from notify import send"),
                                ("return send_message(msg)", 'return send(msg, priority="high")')]),
        ("handlers/digest.py", [("from notify import send_message", "from notify import send"),
                                ("return send_message(msg)", "return send(msg)")]),
        ("handlers/util.py", [("from notify import send_message as emit", "from notify import send as emit"),
                              ("return emit(msg)", "return emit(msg)")]),
        ("handlers/common.py", [("from notify import send_message", "from notify import send")]),
        ("handlers/chain.py", [("from handlers.common import send_message", "from handlers.common import send"),
                               ("return send_message(msg)", "return send(msg)")]),
        ("handlers/jobs.py", [("from notify import send_message", "from notify import send"),
                              ("urgent = partial(send_message)\n\n\n", ""),
                              ("def urgent_alert(msg):\n    return urgent(msg)",
                               'def urgent_alert(msg):\n    return send(msg, priority="high")')]),
    ])


# ============ d2-config-hard：per-service 超时迁移（一刀切 sed 必挂）============

def build_d2_config_hard() -> None:
    tid = "d2-config-hard"
    t = task(tid)
    write(t / "fixture" / "net.py", '''def get_timeout():
    raise RuntimeError("get_timeout() removed; use settings.timeout_for(service)")
''')
    write(t / "fixture" / "settings.py", '''_TIMEOUTS = {"api": 30, "batch": 120, "export": 300}
DEFAULT_TIMEOUT = 30


def timeout_for(service):
    """Return the timeout configured for the given service."""
    return _TIMEOUTS[service]
''')
    write(t / "fixture" / "client.py", '''from net import get_timeout


def call_api():
    return {"action": "api", "timeout": get_timeout()}
''')
    write(t / "fixture" / "worker.py", '''from net import get_timeout


def run_batch():
    return {"action": "batch", "timeout": get_timeout()}
''')
    write(t / "fixture" / "reporter.py", '''from net import get_timeout


def export_report():
    return {"action": "export", "timeout": get_timeout()}
''')
    write(t / "fixture" / "legacy.py", '''from net import get_timeout as old_timeout


def probe():
    return {"action": "api", "timeout": old_timeout()}
''')
    write(t / "fixture" / "common.py", '''from net import get_timeout  # noqa: F401  (re-export)
''')
    write(t / "fixture" / "daemon.py", '''from common import get_timeout


def heartbeat():
    return {"action": "api", "timeout": get_timeout()}
''')
    write(t / "fixture" / "README.md", "# d2-config-hard\n内部服务超时配置。\n")

    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_timeouts.py", '''from client import call_api
from worker import run_batch
from reporter import export_report
from legacy import probe
from daemon import heartbeat


def test_api_timeout():
    assert call_api()["timeout"] == 30


def test_batch_timeout():
    assert run_batch()["timeout"] == 120


def test_export_timeout():
    assert export_report()["timeout"] == 300


def test_legacy_probe():
    assert probe()["timeout"] == 30


def test_heartbeat():
    assert heartbeat()["timeout"] == 30
''')
    copy_fixture_except(tid, {
        "client.py": '''from settings import DEFAULT_TIMEOUT


def call_api():
    return {"action": "api", "timeout": DEFAULT_TIMEOUT}
''',
        "worker.py": '''from settings import DEFAULT_TIMEOUT


def run_batch():
    return {"action": "batch", "timeout": DEFAULT_TIMEOUT}
''',
        "reporter.py": '''from settings import DEFAULT_TIMEOUT


def export_report():
    return {"action": "export", "timeout": DEFAULT_TIMEOUT}
''',
        "legacy.py": '''from settings import DEFAULT_TIMEOUT as old_timeout


def probe():
    return {"action": "api", "timeout": old_timeout()}
''',
        "daemon.py": '''from settings import DEFAULT_TIMEOUT


def heartbeat():
    return {"action": "api", "timeout": DEFAULT_TIMEOUT}
''',
    })
    finish(tid, '''task_id: d2-config-hard
difficulty: D2
targets_fids: [F05, F09]
sites_required: 6
forbidden_edits: [tests/, _tests/]
prompt: |
  net.get_timeout() 已移除（调用即抛 RuntimeError），改为
  settings.timeout_for(service)：api→30、batch→120、export→300。
  每个调用点要用自己服务的名字（client/legacy/daemon 是 api、worker 是 batch、
  reporter 是 export）。注意调用形式不止一种。请迁移全部调用点。
''', '''# 出题意图（d2-config-hard）

- 同名函数但每处参数不同：sed 一刀切换成 DEFAULT_TIMEOUT 会被 per-service 测试抓住
  （错解 wrong_01 即如此）。
- 狙击 F05、F09。
''', [
        ("client.py", [("from net import get_timeout", "from settings import timeout_for"),
                       ('"timeout": get_timeout()}', '"timeout": timeout_for("api")}')]),
        ("worker.py", [("from net import get_timeout", "from settings import timeout_for"),
                       ('"timeout": get_timeout()}', '"timeout": timeout_for("batch")}')]),
        ("reporter.py", [("from net import get_timeout", "from settings import timeout_for"),
                         ('"timeout": get_timeout()}', '"timeout": timeout_for("export")}')]),
        ("legacy.py", [("from net import get_timeout as old_timeout",
                        "from settings import timeout_for"),
                       ('"timeout": old_timeout()}', '"timeout": timeout_for("api")}')]),
        ("common.py", [("from net import get_timeout", "from settings import timeout_for")]),
        ("daemon.py", [("from common import get_timeout", "from common import timeout_for"),
                       ('"timeout": get_timeout()}', '"timeout": timeout_for("api")}')]),
    ])


# ============ d3-bus-hard：事件注册覆盖（跨文件状态 + 双约束）============

def build_d3_bus_hard() -> None:
    tid = "d3-bus-hard"
    t = task(tid)
    write(t / "fixture" / "bus.py", '''_HANDLERS = {}


def on(event, fn):
    _HANDLERS[event] = fn


def emit(event, payload):
    return _HANDLERS[event](payload)


def reset():
    _HANDLERS.clear()
''')
    write(t / "fixture" / "plugins_email.py", '''from bus import on

SENT = []


def handle_email(payload):
    SENT.append(("email", payload))
    return "email-ok"


def register():
    on("notify", handle_email)
''')
    write(t / "fixture" / "plugins_sms.py", '''from bus import on

SENT = []


def handle_sms(payload):
    SENT.append(("sms", payload))
    return "sms-ok"


def register():
    on("notify", handle_sms)
''')
    write(t / "fixture" / "app.py", '''from bus import emit, reset
from plugins_email import register as reg_email, SENT as EMAIL_SENT
from plugins_sms import register as reg_sms, SENT as SMS_SENT


def notify_all(payload):
    reset()
    EMAIL_SENT.clear()
    SMS_SENT.clear()
    reg_email()
    reg_sms()
    return emit("notify", payload)
''')
    write(t / "fixture" / "README.md", "# d3-bus-hard\n插件通知总线。\n")

    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_bus.py", '''from app import notify_all
from plugins_email import SENT as EMAIL_SENT
from plugins_sms import SENT as SMS_SENT


def test_both_channels_fire():
    notify_all("hello")
    assert ("email", "hello") in EMAIL_SENT
    assert ("sms", "hello") in SMS_SENT


def test_email_fires_first():
    notify_all("hi")
    assert EMAIL_SENT[0] == ("email", "hi")


def test_emit_returns_results():
    results = notify_all("x")
    assert "email-ok" in results and "sms-ok" in results
''')
    copy_fixture_except(tid, {
        "plugins_sms.py": '''from bus import on

SENT = []


def handle_sms(payload):
    SENT.append(("sms", payload))
    return "sms-ok"


def register():
    on("notify_sms", handle_sms)
''',
    })
    finish(tid, '''task_id: d3-bus-hard
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  线上反馈：通知有时只发了短信、邮件收不到（或反过来），像是"随机丢通道"。
  仓库是插件式通知总线。请先复现、定位根因并修复；
  要求 emit 仍返回各通道结果，且注册顺序即触发顺序。
''', '''# 出题意图（d3-bus-hard）

- 根因是 on() 单值覆盖（后注册顶掉先注册），症状"随机丢通道"误导向并发/网络；
  错解给 sms 换事件名绕过——破坏"notify 到达所有通道"的语义，被测试抓住。
- 狙击 F17、F01。
''', [
        ("bus.py", [("def on(event, fn):\n    _HANDLERS[event] = fn",
                     "def on(event, fn):\n    _HANDLERS.setdefault(event, []).append(fn)"),
                    ("def emit(event, payload):\n    return _HANDLERS[event](payload)",
                     "def emit(event, payload):\n"
                     "    return [fn(payload) for fn in _HANDLERS[event]]")]),
    ])


# ============ d3-ini-hard：行内注释（表象误导 + 双约束）============

def build_d3_ini_hard() -> None:
    tid = "d3-ini-hard"
    t = task(tid)
    write(t / "fixture" / "iniconf.py", '''def parse_ini(text):
    """Parse INI text into a dict of str -> str."""
    conf = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        conf[key.strip()] = value.strip()
    return conf


def get_int(conf, key):
    return int(conf[key])
''')
    write(t / "fixture" / "README.md", "# d3-ini-hard\nINI 配置解析器。\n")
    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_ini.py", '''import pytest

from iniconf import parse_ini, get_int


def test_plain_value():
    conf = parse_ini("timeout = 30")
    assert get_int(conf, "timeout") == 30


def test_inline_comment():
    conf = parse_ini("timeout = 30  # seconds")
    assert get_int(conf, "timeout") == 30


def test_comment_line_still_ignored():
    conf = parse_ini("# header\\nretries = 3")
    assert get_int(conf, "retries") == 3


def test_dirty_data_still_raises():
    conf = parse_ini("timeout = abc")
    with pytest.raises(ValueError):
        get_int(conf, "timeout")
''')
    copy_fixture_except(tid, {
        "iniconf.py": '''def parse_ini(text):
    """Parse INI text into a dict of str -> str."""
    conf = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        conf[key.strip()] = value.strip()
    return conf


def get_int(conf, key):
    try:
        return int(conf[key])
    except ValueError:
        return 0
''',
    })
    finish(tid, '''task_id: d3-ini-hard
difficulty: D3
targets_fids: [F17, F01]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  解析生产配置时报 ValueError: invalid literal for int()，
  初步怀疑配置里有非数字的脏数据。请先复现、定位根因并修复；
  注意不能吞掉真实的脏数据（非数字值必须仍然报错）。
''', '''# 出题意图（d3-ini-hard）

- 报错指向"脏数据"，根因是行内注释没过滤（`30  # seconds`）；
  错解给 int 套 try/except 返回 0——脏数据测试抓住它（双约束）。
- 狙击 F17、F01。
''', [
        ("iniconf.py", [('        key, _, value = line.partition("=")\n'
                         '        conf[key.strip()] = value.strip()',
                         '        key, _, value = line.partition("=")\n'
                         '        value = value.split("#", 1)[0]\n'
                         '        conf[key.strip()] = value.strip()')]),
    ])


if __name__ == "__main__":
    builders = [build_d2_sig_hard, build_d2_config_hard, build_d3_bus_hard, build_d3_ini_hard]
    for b in builders:
        b()
        print(f"built: {b.__name__}")
    print(f"\n共生成 {len(builders)} 个任务")
    sys.exit(0)
