"""一次性补丁：forge_multi 跨文件化 + 追加 M3/M4/M5。"""
from pathlib import Path

p = Path("scripts/forge_tasks.py")
t = p.read_text(encoding="utf-8")

# 1) 锚点校验多文件
t = t.replace(
    '''    src = pkg_root_old / target_file
    text = src.read_text(encoding="utf-8")
    for s in sites:
        for o, n in s["repls"]:
            assert o in text, f"[{tid}] 锚点未找到：{o[:60]}"''',
    '''    for s in sites:
        sf = pkg_root_old / s.get("file", target_file)
        stext = sf.read_text(encoding="utf-8")
        for o, n in s["repls"]:
            assert o in stext, f"[{tid}] 锚点未找到（{s.get('file', target_file)}）：{o[:60]}"''')

# 2) fixture 注入多文件
t = t.replace(
    '''    fixture_file = tdir / "fixture" / target_file
    ftext = fixture_file.read_text(encoding="utf-8")
    for s in sites:
        for o, n in s["repls"]:
            ftext = ftext.replace(o, n, 1)
    fixture_file.write_text(ftext, encoding="utf-8")''',
    '''    for s in sites:
        ff = tdir / "fixture" / s.get("file", target_file)
        ftext = ff.read_text(encoding="utf-8")
        for o, n in s["repls"]:
            ftext = ftext.replace(o, n, 1)
        ff.write_text(ftext, encoding="utf-8")''')

# 3) 逐组补丁多文件
t = t.replace(
    '''    orig_lines = fixture_file.read_text(encoding="utf-8").splitlines()
    for i, s in enumerate(sites):
        fixed = fixture_file.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            fixed = fixed.replace(n, o, 1)
        d = list(difflib.unified_diff(orig_lines, fixed.splitlines(), lineterm="", n=0,
                                      fromfile=f"a/{target_file}",
                                      tofile=f"b/{target_file}"))''',
    '''    for i, s in enumerate(sites):
        ff = tdir / "fixture" / s.get("file", target_file)
        orig_lines = ff.read_text(encoding="utf-8").splitlines()
        fixed = ff.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            fixed = fixed.replace(n, o, 1)
        d = list(difflib.unified_diff(orig_lines, fixed.splitlines(), lineterm="", n=0,
                                      fromfile=f"a/{s.get('file', target_file)}",
                                      tofile=f"b/{s.get('file', target_file)}"))''')

# 4) 全撤销多文件
t = t.replace(
    '''    patched = tdir / ".verify-patched"
    shutil.copytree(tdir / "fixture", patched)
    pf = patched / target_file
    ptext = pf.read_text(encoding="utf-8")
    for s in sites:
        for o, n in reversed(s["repls"]):
            ptext = ptext.replace(n, o, 1)
    pf.write_text(ptext, encoding="utf-8")''',
    '''    patched = tdir / ".verify-patched"
    shutil.copytree(tdir / "fixture", patched)
    for s in sites:
        pf = patched / s.get("file", target_file)
        ptext = pf.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            ptext = ptext.replace(n, o, 1)
        pf.write_text(ptext, encoding="utf-8")''')

# 5) 逐组验证多文件
t = t.replace(
    '''        partial = tdir / f".verify-partial-{i}"
        shutil.copytree(tdir / "fixture", partial)
        pp = partial / target_file
        ptxt = pp.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            ptxt = ptxt.replace(n, o, 1)
        pp.write_text(ptxt, encoding="utf-8")''',
    '''        partial = tdir / f".verify-partial-{i}"
        shutil.copytree(tdir / "fixture", partial)
        pp = partial / s.get("file", target_file)
        ptxt = pp.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            ptxt = ptxt.replace(n, o, 1)
        pp.write_text(ptxt, encoding="utf-8")''')

# 6) wrong_01 多文件
t = t.replace(
    '''    wf = wdir / target_file
    wtext = wf.read_text(encoding="utf-8")
    for o, n in reversed(sites[ws]["repls"]):
        wtext = wtext.replace(n, o, 1)
    wf.write_text(wtext, encoding="utf-8")''',
    '''    wf = wdir / sites[ws].get("file", target_file)
    wtext = wf.read_text(encoding="utf-8")
    for o, n in reversed(sites[ws]["repls"]):
        wtext = wtext.replace(n, o, 1)
    wf.write_text(wtext, encoding="utf-8")''')

# 7) 追加 M3/M4/M5
M = '''
    # 复合 3：take 差一 + tail 起点差一（同族函数的成对边界错）
    made += forge_multi(
        "forged-multi-taketail", pkg_root, out_base,
        "more_itertools/recipes.py",
        sites=[
            {"repls": [("    return list(islice(iterable, n))",
                        "    return list(islice(iterable, n + 1))")],
             "f2p_fn": "take", "note": "OFF-BY-ONE take 多取一个"},
            {"repls": [("        return islice(iterable, max(0, size - n), None)",
                        "        return islice(iterable, max(0, size - n + 1), None)")],
             "f2p_fn": "tail", "note": "OFF-BY-ONE tail 少给头元素"},
        ],
        difficulty="D2", fid="F05, F17",
        prompt="用户报告 more_itertools 的两个函数都有问题：take(3, range(10)) "
        "返回 4 个元素；list(tail(3, 'ABCDEFG')) 只返回 ['F','G']（少了 'E'）。"
        "请把两处都修好。",
        intent="\\n- 同族成对边界错：wrong_01 只修 take（tail 漏修，测试抓）。\\n")
    # 复合 4：跨文件双 bug（recipes.py 翻转 + more.py 步长默认值）
    made += forge_multi(
        "forged-multi-crossfile", pkg_root, out_base,
        "more_itertools/recipes.py",
        sites=[
            {"repls": [("        for second in iterator:\\n            return False",
                        "        for second in iterator:\\n            return True")],
             "f2p_fn": "all_equal", "note": "BOUNDARY-FLIP（recipes.py）"},
            {"repls": [("    step = s.step or 1",
                        "    step = s.step or 2")],
             "file": "more_itertools/more.py",
             "f2p_fn": "islice_extended", "note": "默认步长 1→2（more.py）"},
        ],
        difficulty="D3", fid="F05, F17",
        prompt="线上报告两处异常，疑似分属不同模块：all_equal('aaab') 返回 True；"
        "islice_extended 对象做切片时结果每隔一个元素就少一个（如 x[0:6] 只拿到 "
        "3 个）。仓库是 more_itertools，请全部定位并修好。",
        intent="\\n- 跨文件双 bug：考跨模块排查；wrong_01 只修 all_equal。\\n")
    # 复合 5：三 bug 升级（sieve 双 bug + take 差一）
    made += forge_multi(
        "forged-multi-triple", pkg_root, out_base,
        "more_itertools/recipes.py",
        sites=[
            {"repls": [("        data[p * p : n : p + p] = bytes(len(range(p * p, n, p + p)))",
                        "        pass  # BUG-A")],
             "f2p_fn": "sieve", "note": "CACHE-DROP"},
            {"repls": [("    for p in iter_index(data, 1, start, stop=isqrt(n) + 1):",
                        "    for p in iter_index(data, 1, start, stop=isqrt(n)):")],
             "f2p_fn": "sieve", "note": "BOUNDARY isqrt 收缩"},
            {"repls": [("    return list(islice(iterable, n))",
                        "    return list(islice(iterable, n + 1))")],
             "f2p_fn": "take", "note": "OFF-BY-ONE take"},
        ],
        difficulty="D3", fid="F05, F17",
        prompt="用户反馈三处异常：sieve(30) 混入合数、sieve(26) 包含 25、"
        "take(3, range(10)) 返回 4 个元素。请系统性排查并全部修好。",
        extra_f2p="""class TargetedSieveTests(TestCase):
    def test_square_of_prime_excluded(self):
        self.assertNotIn(25, list(mi.sieve(26)))
        self.assertNotIn(49, list(mi.sieve(50)))
""",
        intent="\\n- 三 bug 升级：wrong_01 只修 sieve 标记（另两组漏修）。\\n")
    print(f"\\n共注入 {made} 个 forged 任务 → {out_base}")
    return 0'''

t = t.replace('''    print(f"\\n共注入 {made} 个 forged 任务 → {out_base}")
    return 0''', M, 1)

p.write_text(t, encoding="utf-8")
print("patched")
