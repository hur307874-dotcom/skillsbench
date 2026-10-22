"""mined 抽样四关等效筛：fixture 必须挂 + fixture+gold 必须过（2026-10-09）。"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PY = sys.executable
SAMPLE = ['moreitertools-combination_index-1080-24', 'moreitertools-exactly_n-1080-10-174020',
          'moreitertools-groupby_transform-1080-172926', 'moreitertools-is_sorted-1080-19-173557',
          'moreitertools-locate-1080-08-174020', 'moreitertools-nth_permutation-1080-21-174020',
          'moreitertools-powerset_of_sets-1080-34-173557', 'moreitertools-replace-1080-12-174020',
          'moreitertools-substrings-1080-01-173557', 'moreitertools-unique_in_window-1080-28-174020']
BS = chr(92)  # 反斜杠


def run_pytest(cwd, tests):
    r = subprocess.run([PY, '-m', 'pytest', str(tests), '-q', '--no-header'],
                       cwd=cwd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=300)
    out = r.stdout + r.stderr
    m = re.search(r'(\d+) failed', out)
    p = re.search(r'(\d+) passed', out)
    return (int(m.group(1)) if m else 0), (int(p.group(1)) if p else 0)


def main():
    results = []
    for t in SAMPLE:
        d = (Path('tasks/pool-v2-mined') / t).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            fx = Path(tmp) / 'fx'
            shutil.copytree(d / 'fixture', fx)
            f_failed, f_passed = run_pytest(fx, d / 'tests')
            patch = next((d / 'solution' / 'sites').glob('*.patch'))
            ptxt = patch.read_text(encoding='utf-8').replace(
                'more_itertools' + BS, 'more_itertools/')
            (fx / '_gold.patch').write_text(ptxt, encoding='utf-8', newline='\n')
            ap = subprocess.run(['git', 'apply', '_gold.patch'], cwd=fx,
                                capture_output=True, text=True)
            if ap.returncode != 0:
                results.append((t, f_failed, f_passed, 'PATCH_FAIL: ' + ap.stderr[:60]))
                continue
            g_failed, g_passed = run_pytest(fx, d / 'tests')
            ok = (f_failed > 0 or f_passed < g_passed) and g_failed == 0 and g_passed > 0
            results.append((t, f_failed, f_passed,
                            ('PASS' if ok else 'FAIL') + f' gold后: {g_failed}F/{g_passed}P'))
    for t, ff, fp, v in results:
        print(f'{t[15:44]:<30} fixture: {ff}F/{fp}P  {v}')


if __name__ == '__main__':
    main()
