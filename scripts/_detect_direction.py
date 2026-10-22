"""mined 任务方向检测与归一（2026-10-09）。

实测发现挖掘产物方向不一致（文档约定 fixture=带 bug 旧版+gold=bugfix，
实际部分任务 fixture 已是修复态、patch 是注入 bug 的方向）。
对每题测两个方向：
  A: fixture 挂 → patch 后过        → 合格（现状即正确）
  B: fixture 过 → patch 后挂        → 需归一：fixture'=fixture+patch（bug 态），gold'=reverse patch
  C: 其他（patch 不适用/两边都挂/两边都过）→ 废弃候选
输出方向表，归一动作仅打印不执行（先审）。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PY = sys.executable
BS = chr(92)


def counts(cwd, tests):
    r = subprocess.run([PY, '-m', 'pytest', str(tests), '-q', '--no-header'],
                       cwd=cwd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=300)
    out = r.stdout + r.stderr
    f = re.search(r'(\d+) failed', out)
    p = re.search(r'(\d+) passed', out)
    return (int(f.group(1)) if f else 0), (int(p.group(1)) if p else 0)


def detect(d: Path) -> str:
    d = d.resolve()
    patch_file = next((d / 'solution' / 'sites').glob('*.patch'))
    ptxt = patch_file.read_text(encoding='utf-8').replace('more_itertools' + BS, 'more_itertools/')
    with tempfile.TemporaryDirectory() as tmp:
        fx = Path(tmp) / 'fx'
        shutil.copytree(d / 'fixture', fx)
        ff, fp = counts(fx, d / 'tests')
        (fx / '_g.patch').write_text(ptxt, encoding='utf-8', newline='\n')
        ap = subprocess.run(['git', 'apply', '_g.patch'], cwd=fx,
                            capture_output=True, text=True)
        if ap.returncode != 0:
            return f'C: fixture {ff}F/{fp}P，patch 不适用（{ap.stderr[:40]}）'
        gf, gp = counts(fx, d / 'tests')
        if ff > 0 and gf == 0 and gp > 0:
            return f'A: 合格（fixture {ff}F → gold 后 {gp}P）'
        if ff == 0 and gp < fp:
            return f'B: 方向反（fixture {fp}P → patch 后 {gf}F/{gp}P）→ 需归一'
        return f'C: fixture {ff}F/{fp}P → patch 后 {gf}F/{gp}P（两边不成对）'


def main():
    pool = Path('tasks/pool-v2-mined')
    dirs = sorted(x for x in pool.iterdir() if x.is_dir())
    sample = [dirs[i] for i in range(0, len(dirs), max(1, len(dirs) // 10))][:10]
    from collections import Counter
    c = Counter()
    for d in sample:
        v = detect(d)
        c[v[0]] += 1
        print(f'{d.name[15:44]:<30} {v}')
    print('方向分布:', dict(c))


if __name__ == '__main__':
    main()
