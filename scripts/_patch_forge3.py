"""一次性补丁：forge_tasks.py 的 main() 换成声明式 spec 加载器（引擎/配方分离）。"""
import re
from pathlib import Path

p = Path("scripts/forge_tasks.py")
t = p.read_text(encoding="utf-8")

# 1) 加 yaml 导入
if "import yaml" not in t:
    t = t.replace("import re\nimport shutil", "import re\nimport shutil\nimport yaml", 1)

# 2) 用通用 run_spec + CLI 替换整个 main()
NEW_MAIN = '''
def run_spec(spec_path: Path, out_base: Path) -> int:
    """声明式配方驱动：spec yaml 定义任务，引擎零配方内容（换任务域=换 yaml）。"""
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    pkg_root = find_pkg_root(download_sdist(spec["package"], spec["version"]))
    made = 0
    for task in spec["tasks"]:
        pairs = [(o, n) for o, n in task.get("repls", [])]
        if task["type"] == "single":
            old = pairs if len(pairs) > 1 else pairs[0][0]
            new = None if len(pairs) > 1 else pairs[0][1]
            wrong = task.get("wrong_repls")
            if wrong:
                wrong = [(o, n) for o, n in wrong]
            else:
                wrong = task.get("wrong_line")
            made += forge_one(task["tid"], pkg_root, out_base, task["file"],
                              old, new, task["f2p_fn"], task["difficulty"],
                              task["fid"], task["prompt"].strip(),
                              task.get("intent", "").strip(), wrong_line=wrong)
        else:
            sites = []
            for s in task["sites"]:
                sd = {"repls": [(o, n) for o, n in s["repls"]],
                      "f2p_fn": s["f2p_fn"], "note": s.get("note", "")}
                if "file" in s:
                    sd["file"] = s["file"]
                sites.append(sd)
            made += forge_multi(task["tid"], pkg_root, out_base, task["file"],
                                sites, task["difficulty"], task["fid"],
                                task["prompt"].strip(),
                                task.get("intent", "").strip(),
                                extra_f2p=task.get("extra_f2p"),
                                wrong_site=task.get("wrong_site"))
    print(f"\\n共注入 {made} 个任务（spec={spec_path.name}）→ {out_base}")
    return 0


def main() -> int:
    """用法：python scripts/forge_tasks.py <spec.yaml> [--out DIR]

    引擎通用（无任何任务域/Skill 硬编码）；配方见 tasks/pool-v2/forge_specs/。
    换任务域：新写 spec yaml 即可；换被评 Skill：与 forge 完全无关（臂注入侧）。
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="forge 配方 yaml（如 tasks/pool-v2/forge_specs/more-itertools-10.8.0.yaml）")
    ap.add_argument("--out", default="tasks/pool-v2/forged")
    args = ap.parse_args()
    return run_spec(Path(args.spec), ROOT / args.out)


if __name__ == "__main__":
    sys.exit(main())
'''

# 找到 def main() 起点，截断到文件尾并替换
idx = t.index("def main() -> int:")
t = t[:idx] + NEW_MAIN.lstrip("\n")
p.write_text(t, encoding="utf-8")
print("patched: main() 已换成 spec 加载器")
