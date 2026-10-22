"""一次性补丁：forge_one 泛化为多锚点替换。"""
from pathlib import Path

p = Path("scripts/forge_tasks.py")
t = p.read_text(encoding="utf-8")

t = t.replace(
    '''    src = pkg_root_old / target_file
    text = src.read_text(encoding="utf-8")
    assert old_line in text, f"算子锚点未找到：{old_line[:60]}"''',
    '''    src = pkg_root_old / target_file
    text = src.read_text(encoding="utf-8")
    repls = old_line if isinstance(old_line, list) else [(old_line, new_line)]
    for o, n in repls:
        assert o in text, f"算子锚点未找到：{o[:60]}"''')

t = t.replace(
    '''    fixture_file = tdir / "fixture" / target_file
    ftext = fixture_file.read_text(encoding="utf-8").replace(old_line, new_line, 1)
    fixture_file.write_text(ftext, encoding="utf-8")''',
    '''    fixture_file = tdir / "fixture" / target_file
    ftext = fixture_file.read_text(encoding="utf-8")
    for o, n in repls:
        ftext = ftext.replace(o, n, 1)
    fixture_file.write_text(ftext, encoding="utf-8")''')

t = t.replace(
    '''    orig_text = fixture_file.read_text(encoding="utf-8")
    fixed_text = orig_text.replace(new_line, old_line, 1)''',
    '''    orig_text = fixture_file.read_text(encoding="utf-8")
    fixed_text = orig_text
    for o, n in reversed(repls):
        fixed_text = fixed_text.replace(n, o, 1)''')

t = t.replace(
    '''    pf = patched / target_file
    pf.write_text(pf.read_text(encoding="utf-8").replace(new_line, old_line, 1),
                  encoding="utf-8")''',
    '''    pf = patched / target_file
    ptext = pf.read_text(encoding="utf-8")
    for o, n in reversed(repls):
        ptext = ptext.replace(n, o, 1)
    pf.write_text(ptext, encoding="utf-8")''')

t = t.replace(
    '''    if wrong_line:
        wdir = tdir / "wrong" / "wrong_01"
        shutil.copytree(tdir / "fixture", wdir, dirs_exist_ok=True)
        wf = wdir / target_file
        wf.write_text(wf.read_text(encoding="utf-8").replace(new_line, wrong_line, 1),
                      encoding="utf-8")''',
    '''    if wrong_line:
        wrepls = wrong_line if isinstance(wrong_line, list) else [(repls[-1][1], wrong_line)]
        wdir = tdir / "wrong" / "wrong_01"
        shutil.copytree(tdir / "fixture", wdir, dirs_exist_ok=True)
        wf = wdir / target_file
        wtext = wf.read_text(encoding="utf-8")
        for o, w in wrepls:
            wtext = wtext.replace(o, w, 1)
        wf.write_text(wtext, encoding="utf-8")''')

p.write_text(t, encoding="utf-8")
print("patched")
