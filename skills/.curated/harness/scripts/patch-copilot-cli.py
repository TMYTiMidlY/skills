#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Patch Copilot CLI app.js —— 一把梭补几个「stock 无配置可改」的行为，全部只改
pkg cache 里运行时真正跑的 app.js（见 harness/references/copilot-patch.md）。

设计目标：**跑成功就不用手改**。每个 patch 相互独立、各带幂等 marker、锚点用稳定
字面量 + 反向引用捕获混淆名、命中数必须唯一才落、写后 node --check 失败即整档回滚。
**任何一个 patch 锚点在新版本失效，只会单独 skip 并打印原因**，不影响其余、也不破坏
文件；这时再对照 copilot-patch.md 的「改什么 + 稳定字面量」重新逆向那一个 patch。

抗腐坏设计（为什么这版比上一版能撑更久）：
  1. 特性探针（probe）区分「锚点腐坏」(SKIP，需人工逆向) 与「上游把该特性整个搬走了」
     (N/A，不是腐坏、--strict 不该因此报警)。
  2. 每个 patch 允许多套形态（form A/B/...），按新→旧依次尝试，老版本目录自然回落。
  3. **不硬编 effort 阶梯**：顺序取自 bundle 里的 `<alias>.reasoningEffortLevels()`
     （native 返回、升序、[0] 是 none），上游新增更高档位自动跟上。
  4. 锚点优先用**属性名 / native 函数名**（`switchTo({modelId,reasoningEffort,contextTier`、
     `modelsIsTieredTokenPrices`、`effortLevel`/`contextTier`）而非整段表达式形状。
  5. 能降级就不放弃：clearpoint 找不到模型对象时退化成「保留上次设置」而不是 SKIP。

覆盖（对 1.0.78-2 实测命中；旧版本形态不同会各自回落 form A 或 skip/n-a）：
  retry-maxretries  默认重试配置对象 maxRetries 5→10（GOAWAY/瞬断更耐抗）
  effort-default    每个模型的「默认 effort」→ 它当前**有权使用**的最高档
                    （picker (default) 顶格；typed /model 回落也顶格）
  tiers-clearpoint  context tier 落盘半：typed `/model <id>` 落盘点别把 effortLevel/contextTier
                    抹成空（下次启动不掉档、settings 不被抹）
  tiers-live        context tier 运行时半：TUI 应用模型那一步，tier 为空时按模型能力补
                    long_context，让**本会话**切模型后即时长上下文
  tiers-picker      context tier picker 半：无参 `/model` 选择器里，非当前模型的 tier 默认值
                    从硬编 "default" 改成 long_context（否则 picker 传显式 "default"、
                    把 tiers-live 的守卫短路掉，列表里显示的窗口也是小的那个）
  tiers-startup     context tier 启动半：settings 里没有 contextTier 时，交互启动兜底
                    long_context（否则「没配过 / 被抹过」的新会话直接掉回小窗口）
  webfetch-fakeip   web_fetch SSRF 守卫放行 fake-ip 段 198.18/19（mihomo fake-ip 下可用）
                    ⚠️ 1.0.74 起该守卫已整体下沉到 native (.node)，app.js 无锚点可打 → 报 N/A

用法：  patch-copilot-cli.py            # dry-run，只报告命中/skip，不写
        patch-copilot-cli.py --apply   # 落盘（自动备份 + node --check + 失败回滚）
        patch-copilot-cli.py --revert  # 从备份恢复所有版本目录的 app.js
        （任意模式可加 --latest-only：只处理每个平台版本号最高的那份，即 loader 实际会跑的那份，
          不碰旧版本目录。想精确「只改在跑的这版」时用它。）
        （加 --strict：处理完若有 patch SKIP / node --check 失败，进程退非零——给 systemd
          copilot-auto-patch 服务判「补丁失效、需人工逆向」用；常与 --apply --latest-only 合用。
          N/A（上游移除该特性）不算失败。）
auto-update 后新版本目录是干净的，重跑一次即可（幂等）。
"""
import os, re, sys, glob, shutil, subprocess

APPLY  = "--apply"  in sys.argv
REVERT = "--revert" in sys.argv
LATEST_ONLY = "--latest-only" in sys.argv
STRICT = "--strict" in sys.argv
BACKUP_SUFFIX = ".tmy-patch.bak"

# 找不到 native 的 effort 阶梯时的兜底（升序，与 h.reasoningEffortLevels() 同序）
FALLBACK_EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]

# ------- 版本目录发现（对齐 CLI 自己的 pkg cache 查找顺序） -------
def pkg_roots():
    override = os.environ.get("TMY_PATCH_PKG_ROOT")
    if override:
        return [override] if os.path.isdir(override) else []
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
    """SemVer 优先级排序键：正式版 > 它的预发布版（`1.0.69` > `1.0.69-2`），数字预发布
    标识按数值比。sorted()[-1] == 最高版本，与 CLI loader 选版一致。
    ⚠️ 不能简单抠所有数字组元组：那样 `1.0.69-2`→(1,0,69,2) 会被判得比 `1.0.69`→(1,0,69)
    高，正好和 loader 相反（踩过：正式版落地后 --latest-only 补错目录、漏了真正在跑的那份）。"""
    rel, _, pre = v.strip().partition("-")
    rel_key = tuple(int(x) for x in re.findall(r"\d+", rel))
    if not pre:                       # 无预发布段：同一正式版里排最高
        return (rel_key, 1, ())
    # 数字标识按数值、优先级低于字母数字标识；字段多者优先级高（元组比较天然满足）
    pre_key = tuple((0, int(i), "") if i.isdigit() else (1, 0, i) for i in pre.split("."))
    return (rel_key, 0, pre_key)

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

# ============================ 共用探测 ============================
def module_alias(src):
    """探测 native 模块别名（形如 `h` in h.modelsIsTieredTokenPrices）。跨版本可能改名。"""
    m = re.search(r'([\w$]+)\.modelsIsTieredTokenPrices', src)
    return m.group(1) if m else None

def effort_ladder(src):
    """返回 (levels_expr, none_ident)：
    levels_expr —— bundle 里那个「升序 effort 阶梯数组」的标识符（native 直出，
                   上游加档位自动跟上）；探不到就退化成硬编字面量数组。
    none_ident  —— 代表 "none" 的标识符（阶梯 [0]）；探不到用字符串字面量。
    锚点：`<AX>=<alias>.reasoningEffortLevels(),<Y6>=<AX>[0]`（native 函数名跨版本稳定）。"""
    m = re.search(r'([\w$]+)=[\w$]+\.reasoningEffortLevels\(\),([\w$]+)=\1\[0\]', src)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'([\w$]+)=[\w$]+\.reasoningEffortLevels\(\)', src)
    if m:
        return m.group(1), '"none"'
    return "[" + ",".join('"%s"' % e for e in FALLBACK_EFFORT_ORDER) + "]", '"none"'

def js_best_effort(list_expr, levels_expr, none_ident):
    """生成一段 JS IIFE：从 `list_expr`（该模型可用的 effort 数组）里按 `levels_expr`
    的顺序挑最高档；挑不出或只剩 none 时返回 undefined。"""
    return ("(()=>{try{let _l=%s;if(!Array.isArray(_l)||!_l.length)return;"
            "let _b,_i=-1;for(let _x of _l){let _k=%s.indexOf(_x);if(_k>_i)_i=_k,_b=_x}"
            "return _b!==%s?_b:void 0}catch{return}})()" % (list_expr, levels_expr, none_ident))

def js_long_context(model_expr, alias):
    """生成一段 JS IIFE：模型对象支持分层定价且带 long_context 档才返回 "long_context"。"""
    return ('(()=>{try{let _m=%s;return _m&&_m.billing&&_m.billing.token_prices&&'
            '%s.modelsIsTieredTokenPrices(JSON.stringify(_m.billing.token_prices))&&'
            '"long_context"in _m.billing.token_prices?"long_context":void 0}catch{return}})()'
            % (model_expr, alias))

def enclosing_span(src, pos, back=4000):
    """从 pos 往前找最近的 `function`/`=>{` 边界，给"就近搜索"划个粗略上界。"""
    return max(0, pos - back)

# ============================ 各 patch ============================
# 每个函数：接受 src，返回 (new_src|None, note, status)
#   status: "apply" 改了 / "already" 早就打过 / "skip" 锚点腐坏(要人工) / "na" 上游已移除该特性

def p_retry(src):
    """默认重试配置对象 maxRetries 5→10。锚点是那个默认对象字面量（组合唯一，
    其它 {maxRetries:2}/{maxRetries:0} 是 MCP registry policy 专用，天然不误伤）。"""
    mk = "tmy-retry"
    if mk in src:
        return None, "", "already"
    anc = re.compile(r'(\{maxRetries:)5(,defaultRetryDelaySeconds:\d+,backoffFactor:\d+)')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        if "defaultRetryDelaySeconds" not in src:
            return None, "defaultRetryDelaySeconds 不在 bundle（重试配置已换形态/下沉）", "na"
        return None, f"anchor count={len(ms)} (want 1)", "skip"
    m = ms[0]
    new = m.group(1) + f"10/*{mk}*/" + m.group(2)
    return src[:m.start()] + new + src[m.end():], "maxRetries 5->10", "apply"


def p_effort(src):
    """每个模型的「默认 reasoning effort」→ 它当前有权使用的最高档。

    form B（1.0.78+）：默认档解析函数尾部是
        return!<c>||<c>.length===0||<c>.includes(<l>)?<l>:<c>.find(<d>=><d>!==<NONE>)??<NONE>}
      其中 <c> 是该模型的 entitled effort 数组（native 已按套餐过滤）。直接从 <c> 里
      按 native 阶梯挑最高档即可——比 form A 更准（form A 只看静态表 supportedReasoningEfforts）。
    form A（~1.0.77 及更早）：
        async function <fn>(t,e,n,r){return <ly>("sweagent-capi",t,e,r).clientOptions?.defaultReasoningEffort??"medium"}
    """
    mk = "tmy-max-effort"
    if mk in src:
        return None, "", "already"
    levels, none_id = effort_ladder(src)

    # ---- form B：entitled 列表尾部 ----
    ancB = re.compile(r'return!([\w$]+)\|\|\1\.length===0\|\|\1\.includes\(([\w$]+)\)\?\2:'
                      r'\1\.find\(([\w$]+)=>\3!==([\w$]+)\)\?\?\4\}')
    ms = list(ancB.finditer(src))
    if len(ms) == 1:
        m = ms[0]
        c, l, d, none_v = m.groups()
        best = js_best_effort(c, levels, none_v)
        new = (f'return {best}??(!{c}||{c}.length===0||{c}.includes({l})?{l}:'
               f'{c}.find({d}=>{d}!=={none_v})??{none_v})/*{mk}*/}}')
        return src[:m.start()] + new + src[m.end():], \
               f"default effort -> highest entitled (list={c}, ladder={levels})", "apply"

    # ---- form A：静态表 defaultReasoningEffort ?? "medium" ----
    ancA = re.compile(r'async function ([\w$]+)\(([\w$]+),([\w$]+),([\w$]+),([\w$]+)\)\{'
                      r'return ([\w$]+)\("sweagent-capi",\2,\3,\5\)'
                      r'\.clientOptions\?\.defaultReasoningEffort\?\?"medium"\}')
    msA = list(ancA.finditer(src))
    if len(msA) == 1:
        fn, t, e, n, r, ly = msA[0].groups()
        best = js_best_effort("_c&&_c.supportedReasoningEfforts", levels, none_id)
        new = (f'async function {fn}({t},{e},{n},{r}){{/*{mk}*/'
               f'let _c={ly}("sweagent-capi",{t},{e},{r});'
               f'return {best}??(_c.clientOptions?.defaultReasoningEffort??"medium")}}')
        return src[:msA[0].start()] + new + src[msA[0].end():], \
               f"default effort -> highest supported ({fn}, form A)", "apply"

    if "defaultReasoningEffort" not in src and "reasoningEffortLevels" not in src:
        return None, "bundle 里已无 reasoning effort 解析层（整体下沉 native？）", "na"
    return None, f"form B count={len(ms)}, form A count={len(msA)} (want 1) — 默认档解析形态已变", "skip"


def p_tiers(src):
    """落盘半：typed `/model <id>` 写 settings 前那句
       `<y>.effortLevel=void 0,<y>.contextTier=void 0` 会把持久默认抹掉
       （下次启动就掉档，且改 settings.json 也扛不住）。改成**自赋值**（no-op）：
       `<y>.effortLevel=<y>.effortLevel,<y>.contextTier=<y>.contextTier`
       —— 上游那两处清空点前面都是 `<y>={...<已加载的 settings>}`，自赋值即"保留上次设置"。

    为什么不像旧版那样"按模型能力算出该写什么"：
      · effort 侧：旧版守卫读 `<模型对象>.supportedReasoningEfforts`，但该字段**只在
        bundle 内置静态表上**，API 模型列表对象没有 → 恒为 undefined、等于没打。
        正确的兜底在 effort-default（改默认档解析本身），这里不该重复。
      · context 侧：给不支持 long_context 的模型留着该 tier 会被**安静忽略**（实测
        `--model gpt-5-mini --context long_context` 正常返回），所以不必算、不必清。
    收益：锚点只剩两个属性名，不再依赖"就近找得到模型对象"，抗版本腐坏强得多。"""
    mk = "tmy-tiers-b"
    if mk in src:
        return None, "", "already"
    anc = re.compile(r'([\w$]+)\.effortLevel=void 0,\1\.contextTier=void 0')
    ms = list(anc.finditer(src))
    if not ms:
        if "effortLevel" not in src or "contextTier" not in src:
            return None, "bundle 已无 effortLevel/contextTier 设置键", "na"
        return None, "找不到 effortLevel/contextTier 清空点（上游或已不清 —— 复核后可删本 patch）", "skip"
    # 从后往前替换，避免前面的改动挪动后面的 offset
    for m in reversed(ms):
        y = m.group(1)
        new = f'{y}.effortLevel={y}.effortLevel,{y}.contextTier={y}.contextTier/*{mk}*/'
        src = src[:m.start()] + new + src[m.end():]
    return src, f"typed /model 不再抹掉持久档位 x{len(ms)}", "apply"


def p_tiers_live(src):
    """运行时半：TUI 真正应用模型那一步把 tier 传进 `session.model.switchTo({...})`。
    上游在 typed `/model` 路径把 tier 传成 undefined → 本会话 live 窗口掉回默认档
    （settings 已是 long_context 也没用，要重开会话才生效）。这里在**应用函数内部**补：
    tier 为空时按模型能力补 long_context；显式选了 `default` 的（picker 路径）不动。

    锚点全部走**属性名**（`.model.switchTo({modelId:…,reasoningEffort:…,contextTier:…`）
    和就近的模型列表解构（`<vs>=<st>?.type==="success"?<st>.list:void 0`），不依赖
    外层函数签名——比上一版盯 `setModel:async(…)` 的形状耐版本得多。"""
    mk = "tmy-tiers-live"
    if mk in src:
        return None, "", "already"
    alias = module_alias(src)
    if not alias:
        return None, "no modelsIsTieredTokenPrices (pre-long_context 版本)", "na"
    anc = re.compile(r'let ([\w$]+)=([\w$]+)\?\.type==="success"\?\2\.list:void 0,'
                     r'([\w$]+)=\(await ([\w$]+)\.model\.switchTo\(\{modelId:([\w$]+),'
                     r'reasoningEffort:([\w$]+),contextTier:([\w$]+),')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        if ".model.switchTo({modelId:" not in src:
            return None, "bundle 里已无 model.switchTo({modelId:…}) 调用形态", "na"
        return None, f"switchTo apply-site anchor count={len(ms)} (want 1)", "skip"
    m = ms[0]
    vs, st, gc, sess, mid, eff, tier = m.groups()

    # 就近往前找 `,<bi>=<tier>;`（UI/记账都用 <bi>，改它一处就全对齐）
    back_from = enclosing_span(src, m.start(), 2500)
    back = src[back_from:m.start()]
    bm = list(re.finditer(r',([\w$]+)=' + re.escape(tier) + r';', back))
    guard = js_long_context(f'({st}?.type==="success"?{st}.list:[]).find(_x=>_x&&_x.id==={mid})',
                            alias)
    if bm:
        bi = bm[-1].group(1)
        # 先改后面（switchTo 那处），再改前面，避免 offset 位移
        src = (src[:m.start()] + m.group(0).replace(f"contextTier:{tier},", f"contextTier:{bi},")
               + src[m.end():])
        b = bm[-1]
        abs_s, abs_e = back_from + b.start(), back_from + b.end()
        src = src[:abs_s] + f',{bi}=({tier}??{guard})/*{mk}*/;' + src[abs_e:]
        return src, f"live tier guard (state={bi}, model={mid}, alias={alias})", "apply"
    # 找不到 UI 状态变量：至少把传给 switchTo 的那一位补上
    src = (src[:m.start()] + m.group(0).replace(f"contextTier:{tier},",
                                                f"contextTier:({tier}??{guard})/*{mk}*/,")
           + src[m.end():])
    return src, f"live tier guard (switchTo arg only, model={mid}, alias={alias})", "apply"


def p_webfetch(src):
    """web_fetch 的 SSRF 守卫放行 fake-ip 段 198.18/19（mihomo fake-ip 下 web_fetch 可用）。
    ⚠️ 1.0.74 起该守卫连同整个 URL 解析已下沉到 native（`h.toolWebFetchRegisterCallbacks`），
    app.js 里再没有 `hookResolveAndValidateUrl` / `networkIsBlockedIp` 可打 → 报 N/A。
    要改只能动 prebuilds/*/cli-native.node，不在本脚本范围。"""
    mk = "tmy-webfetch-fakeip"
    if mk in src:
        return None, "", "already"
    anc = re.compile(r'async function ([\w$]+)\(([\w$]+),([\w$]+)=\{\}\)\{'
                     r'return\(await ([\w$]+)\.hookResolveAndValidateUrl\('
                     r'\2,\3\.allowLocalhost===!0,\3\.urlLabel\)\)'
                     r'\.map\(\(\{address:([\w$]+),family:([\w$]+)\}\)=>\(\{address:\5,family:\6\}\)\)\}')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        if "hookResolveAndValidateUrl" not in src and "networkIsBlockedIp" not in src:
            return None, "SSRF 守卫已下沉 native（app.js 无锚点，需改 .node 才能放行）", "na"
        return None, f"anchor count={len(ms)} (want 1)", "skip"
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
    return src[:ms[0].start()] + new + src[ms[0].end():], f"fake-ip 198.18/19 放行 ({fn})", "apply"


def p_tiers_picker(src):
    """picker 半：无参 `/model` 打开的模型选择器里，每个模型条目的 context tier 默认值。

    上游写成 `<je>=<Hn>?<fe>[<m>.id]??(<m>.id===<cur>?<C>??"default":"default"):void 0`：
    只有**当前**模型沿用现有 tier，切到任何**其它**模型一律硬编 `"default"`。这个值
    既决定列表里显示的上下文大小，也作为**显式** tier 传给应用函数 —— 于是
    `tiers-live` 的 `??` 守卫会被短路（`"default"` 不是 nullish），picker 路径拿不到长上下文。
    （typed `/model <id>` 路径传的是 undefined，守卫生效、能拿到 1M；两条路径行为不一致就是这么来的。）

    改法：把该赋值 RHS 里的 `"default"` 字面量换成 `"long_context"`。
    安全性：`<Hn>` 来自「构造 tier 选项」的函数，它在模型**没有** long_context 档时返回
    undefined；所以 `<Hn>` 为真 ⟺ 该模型确实有 long_context 档，换了不会造出非法档位。
    保留语义：`<fe>[<m>.id]`（用户在 picker 里明确选过的档）仍然优先，不覆盖显式选择。

    锚点走列表项上的**属性名** `contextTier:…,contextTiers:…?.map(`（API 契约、跨版本稳），
    再就近回溯到那句赋值，不依赖外层组件签名。"""
    mk = "tmy-tiers-picker"
    if mk in src:
        return None, "", "already"
    anc = re.compile(r'contextTier:([\w$]+),contextTiers:([\w$]+)\?\.map\(')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        if "contextTiers:" not in src:
            return None, "bundle 里已无 contextTiers 列表项（picker 形态已变/无分层档）", "na"
        return None, f"picker 列表项锚点 count={len(ms)} (want 1)", "skip"
    je, hn = ms[0].groups()
    back_from = max(0, ms[0].start() - 2000)
    back = src[back_from:ms[0].start()]
    am = list(re.finditer(re.escape(je) + r'=' + re.escape(hn) + r'\?(.{0,220}?):void 0[,;]', back))
    if not am:
        return None, f"找不到 {je}={hn}?…:void 0 的默认 tier 赋值", "skip"
    a = am[-1]
    rhs = a.group(1)
    if '"default"' not in rhs:
        return None, f"默认 tier 赋值里没有 \"default\" 字面量（上游或已改默认）: {rhs[:80]}", "skip"
    new_rhs = rhs.replace('"default"', '"long_context"')
    abs_s = back_from + a.start(1)
    abs_e = back_from + a.end(1)
    src = src[:abs_s] + new_rhs + f'/*{mk}*/' + src[abs_e:]
    return src, f"picker 默认 tier -> long_context (je={je}, opts={hn})", "apply"


def p_tiers_startup(src):
    """启动半：把「内置默认 context tier」从 default 改成 long_context。

    启动时 tier 的优先级链是 `--context 开关 ?? settings.contextTier ?? 内置默认`，
    bundle 里就是一句 `<Br>=<opts>.context??<settings>.contextTier`——**链尾什么都没有**，
    两者都没有时得到 undefined、落回小窗口。所以「settings 里没写过 contextTier」
    或「被别的路径抹掉过」的新会话都会掉档（实测：有该键 1000k、没有 264k）。

    改法：在这条链尾接 `??"long_context"`，即只改「内置默认」这一档，
    开关和 settings 的显式值仍然优先（`??` 短路），不动用户的显式选择。

    安全性：给不支持 long_context 的模型带上该档会被**安静忽略**（实测），不报错、不掉档。

    ⚠️ 别打错地方：另有两处也在读 `contextTier`——一处只喂 UI 状态、一处是 resume /
    远程会话的「从盘重灌」（条件是 `盘上有值` 才生效）。改那两处对**全新会话无效**（踩过）。
    认这条链的判据是它同时出现 `<opts>.context`（命令行开关）和 `.contextTier`（settings 键）。"""
    mk = "tmy-tiers-startup"
    if mk in src:
        return None, "", "already"
    anc = re.compile(r'([\w$]+)=([\w$]+)\.context\?\?([\w$]+)\.contextTier(?!\w)')
    ms = list(anc.finditer(src))
    if len(ms) != 1:
        if "contextTier" not in src:
            return None, "bundle 里已无 contextTier 设置键", "na"
        return None, f"启动 tier 优先级链锚点 count={len(ms)} (want 1)", "skip"
    m = ms[0]
    var, opts, st = m.groups()
    new = f'{var}={opts}.context??{st}.contextTier??"long_context"/*{mk}*/'
    return src[:m.start()] + new + src[m.end():], \
           f"内置默认 tier -> long_context ({var}={opts}.context??{st}.contextTier)", "apply"


PATCHES = [
    ("retry-maxretries", p_retry),
    ("effort-default",   p_effort),
    ("tiers-clearpoint", p_tiers),
    ("tiers-live",       p_tiers_live),
    ("tiers-picker",     p_tiers_picker),
    ("tiers-startup",    p_tiers_startup),
    ("webfetch-fakeip",  p_webfetch),
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
    lines, ok = [], True
    for name, fn in PATCHES:
        new, note, status = fn(cur)
        if status == "already":
            lines.append(f"    [{name}] already"); continue
        if status == "na":
            lines.append(f"    [{name}] N/A: {note}"); continue
        if status == "skip" or new is None:
            lines.append(f"    [{name}] SKIP: {note}"); ok = False; continue
        cur = new
        lines.append(f"    [{name}] {'APPLY' if APPLY else 'would apply'}: {note}")
    for l in lines: print(l)
    if cur == src0:
        print("    -> no change"); return ok
    if not APPLY:
        print("    -> (dry-run) not written"); return ok
    if not os.path.exists(path + BACKUP_SUFFIX):
        shutil.copy2(path, path + BACKUP_SUFFIX)
    open(path, "w", encoding="utf-8").write(cur)
    if node:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(path + BACKUP_SUFFIX, path)
            print(f"    -> FAILED node --check, REVERTED: {r.stderr.strip()[:200]}"); return False
        print("    -> written + node --check ok")
    else:
        print("    -> written (node not found; --check SKIPPED, verify manually)")
    return ok

def main():
    files = app_js_files()
    if LATEST_ONLY:
        files = latest_only(files)
    node = find_node()
    mode = "REVERT" if REVERT else ("APPLY" if APPLY else "DRY-RUN")
    tag = " (latest-only)" if LATEST_ONLY else ""
    tag += " (strict)" if STRICT else ""
    print(f"mode={mode}{tag}  node={node or '(none)'}  found {len(files)} app.js\n")
    if not files:
        print("no app.js found under pkg cache roots.")
        if STRICT: sys.exit(1)
        return
    if REVERT:
        do_revert(files); return
    all_ok = True
    for f in files:
        print(f"== {f}")
        if not process(f, node): all_ok = False
        print("")
    if not APPLY:
        print("(dry-run; re-run with --apply to write. 只对新会话生效；auto-update 后重跑。)")
    if STRICT and not all_ok:
        print("STRICT: 有 patch SKIP 或 node --check 失败（见上）—— 锚点腐坏，需手动逆向。"
              "（N/A 是上游移除该特性，不计入失败。）")
        sys.exit(1)

if __name__ == "__main__":
    main()
