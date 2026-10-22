"""抽取 kimi 大会话的用户消息与关键结论（一次性分析工具）。"""
import json
import os
import sys
from pathlib import Path

home = Path(os.path.expanduser('~/.workbuddy'))
# 找最大的 jsonl
cands = sorted(home.glob('projects/*/*.jsonl'),
               key=lambda f: f.stat().st_size, reverse=True)[:3]
for f in cands:
    print(f'{f.stat().st_size/1e6:5.1f}MB  {f}')
target = cands[0]
print(f'\n===== 分析：{target.name} =====\n')

users, asst_tail = [], []
n = 0
for line in target.open(encoding='utf-8'):
    try:
        o = json.loads(line)
    except Exception:
        continue
    n += 1
    msg = o.get('message') or {}
    role = o.get('role') or msg.get('role')
    content = o.get('content') if o.get('content') is not None else msg.get('content')
    text = ''
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = ' '.join(c.get('text', '') for c in content if isinstance(c, dict))
    text = text.strip()
    if not text:
        continue
    if role == 'user':
        # 去掉 system-reminder 噪声
        clean = text
        if '<user_query>' in clean:
            clean = clean.split('<user_query>')[-1].split('</user_query>')[0]
        elif '<system-reminder' in clean:
            continue
        clean = clean.strip()
        if clean:
            users.append(clean)
    elif role == 'assistant' and (len(users) > 0):
        asst_tail.append(text[:400])

print(f'总条目 {n}，用户消息 {len(users)} 条\n')
print('===== 用户诉求时间线 =====')
for i, u in enumerate(users, 1):
    print(f'\n[{i}] {u[:500]}')
