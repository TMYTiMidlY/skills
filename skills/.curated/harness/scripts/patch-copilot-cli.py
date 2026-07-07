#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Patch Copilot CLI app.js —— 一把梭补 4 个「stock 无配置可改」的行为，全部只改
pkg cache 里运行时真正跑的 app.js（见 harness/references/copilot-patch.md）。

设计目标：**跑成功就不用手改**。每个 patch 相互独立、各带幂等 marker、锚点用稳定
字面量 + 反向引用捕获混淆名、命中数必须唯一才落、写后 node --check 失败即整档回滚。
**任何一个 patch 锚点在新版本失效，只会单独 skip 并打印原因**，不影响其余、也不破坏
文件；这时再对照 copilot-patch.md 的「改什么 + 稳定字面量」重新逆向那一个 patch。

覆盖（均对 1.0.69-2 实测命中；旧版本形态不同会各自 skip，反正 loader 只跑最高版）：
  retry-maxretries  默认重试配置对象 maxRetries 5→10（GOAWAY/瞬断更耐抗）
  effort-default    每个模型默认 reasoning effort → 它支持的最高档（picker (default) 顶格）
  webfetch-fakeip   web_fetch SSRF 守卫放行 fake-ip 段 198.18/19（mihomo fake-ip 下可用）
  tiers-clearpoint  typed `/model <id>` 落盘点：别把 effortLevel/contextTier 清成默认，
                    支持的模型分别保成最高 effort / long_context（切模型不掉档、settings 不被抹）

**不覆盖、需手动**（形态在 1.0.69-2 已变/移除，见 copilot-patch.md 说明）：
  · retry 的非-API 错误退避 4s 下限（该 jitter 公式当前版本已不在）
  · setModel 的本会话内存半（1.0.69-2 已改为转发当前 tier M0，语义待逐版本核）

用法：  patch-copilot-cli.py            # dry-run，只报告命中/skip，不写
        patch-copilot-cli.py --apply   # 落盘（自动备份 + node --check + 失败回滚）
        patch-copilot-cli.py --revert   # 从备份恢复所有版本目录的 app.js
        （任意模式可加 --latest-only：只处理每个平台版本号最高的那份，即 loader 实际会跑的那份，
          不碰旧版本目录。想精确「只改在跑的这版」时用它。）
auto-update 后新版本目录是干净的，重跑一次即可（幂等）。
"""
import os, re, sys, glob, shutil, subprocess

APPLY  = "--apply"  in sys.argv
REVERT = "--revert" in sys.argv
LATEST_ONLY = "--latest-only" in sys.argv
BACKUP_SUFFIX = ".tmy-patch.bak"

# ------- 版本目录发现（对齐 CLI 自己的 pkg cache 查找顺序） -------
def pkg_roots():
    cands, seen, out = [], set(), []
    ch = os.environ.get("COPILOT_CACHE_HOME")
    if ch: cands.append(ch + "/pkg")
    cands.append(os.path.expanduser(os.environ.get("XDG_CACHE_HOME", "~/.cache") + "/copilot/pkg"))
    cands.append(os.path.expanduser("~/Library/Caches/copilot/pkg"))  # macOS
    hm = os.environ.get("COPILOT_HOME")
    if hm: cands.append(hm + "/pkg")
    cands.append(os.path.expanduser("~/.copilot/pkg"))
    for r in cands:
        if r and os.path.isdir(r) and r not in seen:
            seen.add(r); out.append(r)
    return out

def app_js_files():
    files = set()
    for root in pkg_roots():
        files.update(glob.glob(root + "/*/*/app.js"))  # <platform>/<version>/app.js
        files.update(glob.glob(root + "/*/app.js"))
    return sorted(files)

def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))

def latest_only(files):
    """每个平台目录只留版本号最高的那份 app.js（loader 实际会跑的那份）。"""
    from collections import defaultdict
    groups = defaultdict(list)
    for f in files:
        platform = os.path.dirname(os.path.dirname(f))  # .../pkg/<platform>
        ver = os.path.basename(os.path.dirname(f))       # <version>
        groups[platform].append((ver, f))
    out = []
    for _, lst in groups.items():
        lst.sort(key=lambda vf: _vkey(vf[0]))
        out.append(lst[-1][1])
    return sorted(out)

def find_node():
    n = shutil.which("node")
    if n: return n
    for p in ["~/.local/share/fnm/node-versions/*/installation/bin/node",
              "~/.nvm/versions/node/*/bin/node",
              "~/.volta/tools/image/node/*/bin/node",
              "/usr/local/bin/node", "/usr/bin/node"]:
        g = sorted(glob.glob(os.path.expanduser(p)))
        if g: return g[-1]
    return ""

def module_alias(src):
    """探测 native 模块别名（形如 `v` in v.modelsIsTieredTokenPrices）。跨版本可能改名。"""
    m = re.search(r'([\w$]+)\.modelsIsTieredTokenPrices', src)
    return m.group(1) if m else None

# ============================ 各 patch ============================
# 每个函数：接受 src，返回 (new_src, note) 或 (None, skip_reason)。
# 只在锚点唯一命中时改；已含自己 marker 的由主循环提前判定为 already。

def p_retry(src):
    mk = "tmy-retry"
    anc = re.compile(r'(\{maxRetries:)5(,defaultRetryDelaySeconds:5,backoffFactor:2)')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        return None, f"anchor count={len(ms)} (want 1)"
    m = ms[0]
    new = m.group(1) + f"10/*{mk}*/" + m.group(2)
    return src[:m.start()] + new + src[m.end():], "maxRetries 5->10"

def p_effort(src):
    mk = "tmy-max-effort"
    # async function <fn>(t,e,n,r){return <ly>("sweagent-capi",t,e,r).clientOptions?.defaultReasoningEffort??"medium"}
    anc = re.compile(r'async function ([\w$]+)\(([\w$]+),([\w$]+),([\w$]+),([\w$]+)\)\{'
                     r'return ([\w$]+)\("sweagent-capi",\2,\3,\5\)'
                     r'\.clientOptions\?\.defaultReasoningEffort\?\?"medium"\}')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        return None, f"anchor count={len(ms)} (want 1)"
    fn, t, e, n, r, ly = ms[0].groups()
    new = (f'async function {fn}({t},{e},{n},{r}){{/*{mk}*/'
           f'let _c={ly}("sweagent-capi",{t},{e},{r}),_s=_c&&_c.supportedReasoningEfforts;'
           f'if(_s&&_s.length){{for(const _o of["max","xhigh","high","medium","low"])'
           f'if(_s.includes(_o))return _o}}'
           f'return _c.clientOptions?.defaultReasoningEffort??"medium"}}')
    return src[:ms[0].start()] + new + src[ms[0].end():], f"default effort -> highest ({fn})"

def p_webfetch(src):
    mk = "tmy-webfetch-fakeip"
    # async function <jmt>(t,e={}){return(await <v>.hookResolveAndValidateUrl(t,e.allowLocalhost===!0,e.urlLabel))
    #   .map(({address:r,family:o})=>({address:r,family:o}))}
    anc = re.compile(r'async function ([\w$]+)\(([\w$]+),([\w$]+)=\{\}\)\{'
                     r'return\(await ([\w$]+)\.hookResolveAndValidateUrl\('
                     r'\2,\3\.allowLocalhost===!0,\3\.urlLabel\)\)'
                     r'\.map\(\(\{address:([\w$]+),family:([\w$]+)\}\)=>\(\{address:\5,family:\6\}\)\)\}')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        return None, f"anchor count={len(ms)} (want 1) — 可能已是形态 A(networkIsBlockedIp) 或又变了"
    fn, t, e, v, ad, fa = ms[0].groups()
    fake = r'/^198\.1[89]\./'   # fake-ip 池 198.18.0.0/15
    new = (f'async function {fn}({t},{e}={{}}){{/*{mk}*/'
           f'try{{let _u=new URL({t}),_h=_u.hostname;'
           f'if(!/^\\d+\\.\\d+\\.\\d+\\.\\d+$/.test(_h)){{'
           f'let _n=await import("node:dns/promises"),_a=await _n.lookup(_h,{{all:!0}});'
           f'if(_a.length&&_a.every(_x=>{fake}.test(_x.address)))'
           f'return _a.map(({{address:{ad},family:{fa}}})=>({{address:{ad},family:{fa}}}))}}}}catch{{}}'
           f'return(await {v}.hookResolveAndValidateUrl({t},{e}.allowLocalhost===!0,{e}.urlLabel))'
           f'.map(({{address:{ad},family:{fa}}})=>({{address:{ad},family:{fa}}}))}}')
    return src[:ms[0].start()] + new + src[ms[0].end():], f"fake-ip 198.18/19 放行 ({fn})"

def p_tiers(src):
    mk = "tmy-tiers-b"
    alias = module_alias(src)
    if not alias:
        return None, "no modelsIsTieredTokenPrices (pre-long_context 版本) — skip"
    # <l>.model=<n>===<u>?void 0:<n>,<l>.effortLevel=void 0,<l>.contextTier=void 0
    anc = re.compile(r'([\w$]+)\.model=([\w$]+)===([\w$]+)\?void 0:\2,'
                     r'\1\.effortLevel=void 0,\1\.contextTier=void 0')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        return None, f"anchor count={len(ms)} (want 1)"
    m = ms[0]; l, n, u = m.group(1), m.group(2), m.group(3)
    # 前方就近找模型对象 <mv>=<r>.find(a=>a.id===<n>)
    pre = src[max(0, m.start() - 700):m.start()]
    fm = list(re.finditer(r'([\w$]+)=[\w$]+\.find\([\w$]+=>[\w$]+\.id===' + re.escape(n) + r'\)', pre))
    if not fm:
        return None, "model-object `.find(a=>a.id===<id>)` not found before anchor"
    mv = fm[-1].group(1)
    eff = (f'({mv}&&{mv}.supportedReasoningEfforts&&{mv}.supportedReasoningEfforts.length?'
           f'["max","xhigh","high","medium","low"].find(_o=>{mv}.supportedReasoningEfforts.includes(_o)):void 0)')
    ctx = (f'({mv}&&{mv}.billing&&{mv}.billing.token_prices&&'
           f'{alias}.modelsIsTieredTokenPrices(JSON.stringify({mv}.billing.token_prices))&&'
           f'"long_context"in {mv}.billing.token_prices?"long_context":void 0)')
    new = (f'{l}.model={n}==={u}?void 0:{n},'
           f'{l}.effortLevel={eff},{l}.contextTier={ctx}/*{mk}*/')
    return src[:m.start()] + new + src[m.end():], f"typed /model 保档 (model={mv}, alias={alias})"

PATCHES = [
    ("retry-maxretries", "tmy-retry",           p_retry),
    ("effort-default",   "tmy-max-effort",      p_effort),
    ("webfetch-fakeip",  "tmy-webfetch-fakeip", p_webfetch),
    ("tiers-clearpoint", "tmy-tiers-b",         p_tiers),
]

# ============================ 主流程 ============================
def do_revert(files):
    n = 0
    for f in files:
        bak = f + BACKUP_SUFFIX
        if os.path.exists(bak):
            shutil.copy2(bak, f); os.remove(bak); n += 1
            print(f"  reverted: {f}")
    print(f"\nreverted {n} file(s).")

def process(path, node):
    src0 = open(path, encoding="utf-8").read()
    cur = src0
    lines = []
    for name, marker, fn in PATCHES:
        if marker in cur:
            lines.append(f"    [{name}] already"); continue
        new, note = fn(cur)
        if new is None:
            lines.append(f"    [{name}] SKIP: {note}"); continue
        cur = new
        lines.append(f"    [{name}] {'APPLY' if APPLY else 'would apply'}: {note}")
    changed = cur != src0
    for l in lines: print(l)
    if not changed:
        print("    -> no change"); return
    if not APPLY:
        print("    -> (dry-run) not written"); return
    if not os.path.exists(path + BACKUP_SUFFIX):
        shutil.copy2(path, path + BACKUP_SUFFIX)
    open(path, "w", encoding="utf-8").write(cur)
    if node:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(path + BACKUP_SUFFIX, path)
            print(f"    -> FAILED node --check, REVERTED: {r.stderr.strip()[:200]}"); return
        print("    -> written + node --check ok")
    else:
        print("    -> written (node not found; --check SKIPPED, verify manually)")

def main():
    files = app_js_files()
    if LATEST_ONLY:
        files = latest_only(files)
    node = find_node()
    mode = "REVERT" if REVERT else ("APPLY" if APPLY else "DRY-RUN")
    tag = " (latest-only)" if LATEST_ONLY else ""
    print(f"mode={mode}{tag}  node={node or '(none)'}  found {len(files)} app.js\n")
    if not files:
        print("no app.js found under pkg cache roots."); return
    if REVERT:
        do_revert(files); return
    for f in files:
        print(f"== {f}")
        process(f, node)
        print("")
    if not APPLY:
        print("(dry-run; re-run with --apply to write. 只对新会话生效；auto-update 后重跑。)")

if __name__ == "__main__":
    main()
