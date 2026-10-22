"""按模型×臂汇总全部 runs.jsonl（一次性报表）。"""
import json
import glob
from collections import defaultdict
from pathlib import Path

MODEL = {'real-q1': 'claude-opus', 'b1-pilot': 'claude-haiku', 'quick-n3': 'deepseek-flash',
         'gradient-glm': 'glm-5.x', 'gradient-n3': 'glm-5.1/5.3', 'ablation-glm52': 'glm-5.2',
         'v2-accept': 'deepseek-flash', 'v3-accept': 'deepseek-flash',
         'heldout-final': 'deepseek-flash', 'forged-v13': 'deepseek-flash',
         'pilot-forged-2': 'deepseek-flash', 'forged-v13-p2p': 'deepseek-flash',
         'forged-glm52': 'glm-5.2', 'pilot-multi-1': 'deepseek-flash',
         'pilot-multi2': 'deepseek-flash', 'pool-v20-main': 'deepseek-flash',
         'v1-core5': 'deepseek-flash', 'v3-core5': 'deepseek-flash'}

by = defaultdict(lambda: defaultdict(lambda: {'n': 0, 'dead': 0, 'p': 0, 's': [], 't': []}))
for f in glob.glob('results/*/runs.jsonl'):
    batch = Path(f).parent.name
    model = MODEL.get(batch)
    if not model:
        continue
    for l in open(f, encoding='utf-8'):
        r = json.loads(l)
        b = by[model][r['arm']]
        b['n'] += 1
        if r.get('dead'):
            b['dead'] += 1
        elif 'error' not in r:
            b['s'].append(r['score'])
            b['t'].append(r['num_turns'])
            if r['score'] == 1.0:
                b['p'] += 1

total = 0
for m in ['claude-opus', 'claude-haiku', 'deepseek-flash', 'glm-5.2', 'glm-5.1/5.3', 'glm-5.x']:
    if m not in by:
        continue
    print(f'=== {m}')
    for a in sorted(by[m]):
        b = by[m][a]
        v = len(b['s'])
        avg = sum(b['s']) / v if v else 0
        avgt = sum(b['t']) / v if v else 0
        total += b['n']
        print(f"  {a:12s} n={b['n']:3d} 死跑{b['dead']:2d} 满分{b['p']:3d} "
              f"均分{avg:.2f} 均轮{avgt:.1f}")
print(f'\n计入总 run：{total}')
