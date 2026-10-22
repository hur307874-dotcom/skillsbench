"""定位 kimi-k3-2 会话原文文件（一次性工具）。"""
import os
import sqlite3
from pathlib import Path

home = Path(os.path.expanduser('~/.workbuddy'))
con = sqlite3.connect(f'file:{home / "workbuddy.db"}?mode=ro', uri=True)
rows = con.execute(
    "SELECT id, cwd, title, model FROM sessions WHERE model LIKE 'kimi%' "
    "ORDER BY updated_at").fetchall()
print(f'kimi 会话 {len(rows)} 个：\n')
for sid, cwd, title, model in rows:
    cands = list((home / 'projects').glob(f'*/{sid}.jsonl'))
    f = cands[0] if cands else None
    size = f.stat().st_size / 1e6 if f else 0
    print(f'[{title[:32]}]')
    print(f'  cwd : {cwd}')
    print(f'  原文: {f if f else "未找到"}')
    print(f'  大小: {size:.1f} MB')
    if f:
        # 抽首条用户消息 + 末条 assistant 文本，证明可读
        first_user, last_asst, n = None, None, 0
        for line in f.open(encoding='utf-8'):
            try:
                o = __import__('json').loads(line)
            except Exception:
                continue
            n += 1
            msg = o.get('message') or {}
            role = o.get('role') or msg.get('role')
            content = o.get('content') or msg.get('content')
            text = ''
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = ' '.join(c.get('text', '') for c in content
                                if isinstance(c, dict))
            if role == 'user' and text.strip() and not first_user:
                first_user = text.strip()[:120]
            if role == 'assistant' and text.strip():
                last_asst = text.strip()[:120]
        print(f'  条目: {n}')
        print(f'  首问: {first_user}')
        print(f'  末答: {last_asst}\n')
