#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Patch Copilot CLI app.js so typed `/model <id>` KEEPS the long_context tier
instead of resetting to default (and no longer wipes settings.contextTier).

Why: in the interactive TUI the `--context` startup flag is ignored and the tier
is (re)hydrated from settings.json `contextTier`; a typed `/model <id>` then clears
`contextTier` (settings + this-session) back to default. See harness/copilot-cli.md
"上下文档位 (context tier)". This patch is the "/model survives" half; the "startup
= long_context" half is just settings.json `contextTier: long_context`.

Marker `tmy-lc-default`, per-file backup `app.js.pre-longcontext.bak`. Scaffolding
(scan version dirs / backup / node --check / re-apply after auto-update) mirrors
patch-copilot-cli-retry.sh. Idempotent; requires BOTH patches to apply or the file
is reverted; skips bundles without the native `modelsIsTieredTokenPrices` feature
(pre-1.0.68 — injecting the guard there crashes at runtime, node --check can't see it).

PATCH#1 (persistence, typed `/model <id>` settings-write): the SITE-2 clear
  `...X.model=n===u?void 0:n,X.effortLevel=void 0,X.contextTier=void 0...` — replace
  the trailing `.contextTier=void 0` with a tier-support-guarded ternary using the
  model object `s = r.find(a=>a.id===n)` already in scope. (SITE 1, `/model auto`,
  is intentionally left alone: "auto" has no single model / no long_context tier.)
PATCH#2 (this-session, me.setModel): the 3-arg `RG(<id>,void 0,{...})` call resets
  the tier (its 4th positional param defaults). Append a 4th arg computed from the
  model list. (The picker path already passes a 4th arg `RG(...,{...},tier)`, which
  is how we know param#4 is the tier — that call is left untouched.)

Usage:  patch-copilot-cli-longcontext.py [--apply]   (default: dry-run)
"""
import os, re, sys, glob, shutil, subprocess

MARKER = "tmy-lc-default"
BACKUP_SUFFIX = ".pre-longcontext.bak"
APPLY = "--apply" in sys.argv

# tier-support guard (mirrors native H7n); `v` is the module alias already in scope
# at both patch sites (they call v.modelResolver*). Unsupported models -> void 0.
def guard(mv: str) -> str:
    return (f'{mv}&&{mv}.billing&&{mv}.billing.token_prices'
            f'&&v.modelsIsTieredTokenPrices(JSON.stringify({mv}.billing.token_prices))'
            f'&&"long_context"in {mv}.billing.token_prices&&{mv}.billing.token_prices.long_context')

ANCHOR1 = re.compile(r'([\w$]+)\.model=([\w$]+)===([\w$]+)\?void 0:\2,'
                     r'\1\.effortLevel=void 0,\1\.contextTier=void 0')
ANCHOR2 = re.compile(r'setModel:async\(([\w$]+),([\w$]+)\)=>\{'
                     r'let ([\w$]+)=([\w$]+)\?\.type==="success"\?\4\.list:void 0;')

def find_node() -> str:
    n = shutil.which("node")
    if n:
        return n
    pats = [
        "~/.local/share/fnm/node-versions/*/installation/bin/node",
        "~/.nvm/versions/node/*/bin/node",
        "~/.volta/tools/image/node/*/bin/node",
        "/usr/local/bin/node", "/usr/bin/node",
    ]
    cands = []
    for p in pats:
        cands += glob.glob(os.path.expanduser(p))
    cands.sort()
    return cands[-1] if cands else ""

def patch1(src):
    ms = list(ANCHOR1.finditer(src))
    if len(ms) != 1:
        return None, f"PATCH#1 anchor count={len(ms)} (want 1)"
    m = ms[0]; state, mid = m.group(1), m.group(2)
    pre = src[max(0, m.start() - 900):m.start()]
    fm = list(re.finditer(r'([\w$]+)=[\w$]+\.find\([\w$]+=>[\w$]+\.id===' + re.escape(mid) + r'\)', pre))
    if not fm:
        return None, "PATCH#1 model-object .find(id===<mid>) not found before anchor"
    mv = fm[-1].group(1)
    old = m.group(0)
    assert old.endswith(".contextTier=void 0")
    new = old[:-len("void 0")] + f'({guard(mv)}?"long_context":void 0)/*{MARKER}*/'
    return src[:m.start()] + new + src[m.end():], f"PATCH#1 ok (state={state}, id={mid}, model={mv})"

def patch2(src):
    ms = list(ANCHOR2.finditer(src))
    if len(ms) != 1:
        return None, f"PATCH#2 setModel anchor count={len(ms)} (want 1)"
    m = ms[0]; mid, lst = m.group(1), m.group(3)
    # function-name-agnostic: the reset call is <fn>(<id>,void 0,{...contextTier...})
    # with the tier (4th positional) omitted. The minified fn name varies across
    # versions (RG in 1.0.69-*, u$ in 1.0.68). The picker's 4-arg call
    # <fn>(a,b,{...},tier) is excluded because we require exactly (<id>,void 0,{...}).
    rg = re.compile(r'([\w$]+)\(' + re.escape(mid) + r',void 0,(\{[^{}]*contextTier[^{}]*\})\)')
    rm = rg.search(src, m.end())
    if not rm:
        return None, f"PATCH#2 <fn>({mid},void 0,{{...contextTier...}}) call not found"
    fn = rm.group(1)
    inject = (f',(()=>{{let _m=({lst}||[]).find(x=>x&&x.id==={mid});'
              f'return {guard("_m")}?"long_context":void 0}})()/*{MARKER}*/')
    new = rm.group(0)[:-1] + inject + ')'
    return src[:rm.start()] + new + src[rm.end():], f"PATCH#2 ok (fn={fn}, id={mid}, list={lst})"

def process(path, node):
    src = open(path, encoding="utf-8").read()
    if MARKER in src:
        return "already-patched"
    if "modelsIsTieredTokenPrices" not in src:
        return "skip: no long_context feature (pre-1.0.68)"
    s1, msg1 = patch1(src)
    if s1 is None:
        return f"skip: {msg1}"
    s2, msg2 = patch2(s1)
    if s2 is None:
        return f"skip: {msg2}"
    print(f"    {msg1}")
    print(f"    {msg2}")
    if not APPLY:
        return "DRY-RUN would patch"
    shutil.copy2(path, path + BACKUP_SUFFIX)
    open(path, "w", encoding="utf-8").write(s2)
    if node:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(path + BACKUP_SUFFIX, path)
            return f"FAILED node --check, reverted: {r.stderr[:200]}"
        return "PATCHED + node --check ok"
    return "PATCHED (node not found; --check SKIPPED — verify manually)"

def main():
    roots, seen = [], set()
    for r in [(os.environ.get("COPILOT_CACHE_HOME", "") + "/pkg") if os.environ.get("COPILOT_CACHE_HOME") else "",
              os.path.expanduser(os.environ.get("XDG_CACHE_HOME", "~/.cache") + "/copilot/pkg"),
              os.path.expanduser("~/Library/Caches/copilot/pkg"),
              (os.environ.get("COPILOT_HOME", "") + "/pkg") if os.environ.get("COPILOT_HOME") else "",
              os.path.expanduser("~/.copilot/pkg")]:
        if r and os.path.isdir(r) and r not in seen:
            seen.add(r); roots.append(r)
    files = set()
    for root in roots:
        files.update(glob.glob(root + "/*/*/app.js"))
        files.update(glob.glob(root + "/*/app.js"))
    files = sorted(files)
    node = find_node()
    print(f"mode={'APPLY' if APPLY else 'DRY-RUN'}  node={node or '(none)'}  found {len(files)} app.js")
    for f in files:
        print(f"\n== {f}")
        print("  ->", process(f, node))
    if not APPLY:
        print("\n(dry-run; re-run with --apply to write)")

if __name__ == "__main__":
    main()
