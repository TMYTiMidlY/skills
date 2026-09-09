#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Patch Copilot CLI app.js —— 一把梭补几个「stock 无配置可改」的行为，全部只改
pkg cache 里运行时真正跑的 app.js（见 harness/references/copilot-patch.md）。

设计目标：**跑成功就不用手改**。每个 patch 相互独立、各带幂等 marker、锚点用稳定
字面量 + 反向引用捕获混淆名、命中数必须唯一才落；写前 node --check，
成功后备份并原子替换，不把未通过语法校验的内容写进运行时。
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

新版 native profile（1.0.83）：整组适配启动、主会话切换与模型选择器；
使用有权使用的档位、保留显式选择，默认模型标记跟随用户配置，不修改 native 二进制。
该组所有入口必须同时命中；缺少入口时报 SKIP，不把 native 迁移当成 N/A。

旧版 JS profile（对 1.0.78-2 实测命中；不同形态回落 form A 或 skip/n-a）：
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

**已退役**（曾覆盖、现无处可打，见 copilot-patch.md）：
  · web_fetch 放行 fake-ip 段 198.18/19 —— 1.0.74 起整套 URL 解析 + SSRF 判黑下沉到
    native（prebuilds/<platform>/runtime.node），app.js 里再无锚点，故从脚本移除。

用法：  patch-copilot-cli.py            # dry-run，只报告命中/skip，不写
        patch-copilot-cli.py --apply   # 落盘（node --check + 自动备份 + 原子替换）
        patch-copilot-cli.py --revert  # 从备份恢复 app.js；保留备份
        （任意模式可加 --latest-only：只处理每个平台版本号最高的那份，即 loader 实际会跑的那份，
          不碰旧版本目录。想精确「只改在跑的这版」时用它。）
        （加 --strict：处理完若有 patch SKIP / node --check 失败，进程退非零——给 systemd
          copilot-auto-patch 服务判「补丁失效、需人工逆向」用；常与 --apply --latest-only 合用。
          N/A（上游移除该特性）不算失败。）
auto-update 后新版本目录是干净的，重跑一次即可（幂等）。
"""
import os, re, sys, glob, shutil, subprocess, tempfile, hashlib

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
    pch = os.environ.get("COPILOT_PKG_CACHE_HOME")
    if pch: cands.append(pch + "/pkg")
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


NATIVE_MARKER = "tmy-native-defaults-v2"
NATIVE_V1_DIGEST = "9b011a4c7faabcc0856a2d5d18a7ae4225798b209bb13e397e1c7b923b00a6d1"
NATIVE_HELPER = r"""
/*tmy-native-defaults-v2*/
const __tmyNativeDefaults = (() => {
    let launch = {};
    const present = value => value !== undefined && value !== null;
    function rows(handle) {
        const projection = handle.snapshot();
        if (!Array.isArray(projection.rows))
            throw new Error("Copilot defaults patch: model picker rows changed");
        return projection;
    }
    function highest(h, row) {
        if (!row.effortLevels?.length) return undefined;
        const level = [...h.reasoningEffortLevels()].reverse()
            .find(value => row.effortLevels.includes(value));
        if (!present(level))
            throw new Error("Copilot defaults patch: unknown reasoning effort levels");
        return level;
    }
    function defaults(h, row, config) {
        const effort = row.effortLevels?.includes(config.effortLevel)
            ? config.effortLevel : highest(h, row);
        const tier = present(config.contextTier) ? config.contextTier : "long_context";
        return {
            effort,
            tier: row.contextTierSegments?.some(item => item.key === tier) ? tier : undefined
        };
    }
    function current(h, sessionId) {
        return h.modelCliSessionEnvironmentSnapshot({sessionId});
    }
    function modelRow(h, sessionId, modelId, selection = {}) {
        const handle = new h.CliModelPickerHandle({
            sessionId, targetKind: "session",
            resolvedCurrentModel: selection.selectedModel,
            resolvedCurrentReasoningEffort: selection.reasoningEffort,
            resolvedCurrentContextTier: selection.contextTier
        });
        return rows(handle).rows.find(row => row.value === modelId && row.availability === "available");
    }
    function builtinSession(h, sessionId) {
        return h.sessionByokDiscoveredModelIds(sessionId).length === 0;
    }
    function startup(h, input) {
        launch = input;
        const result = h.modelCliStartupConfiguration(input);
        if (!input.providerConfigured && !input.altProvidersEnabled &&
            !present(input.cliReasoningEffort) && !present(input.configReasoningEffort) &&
            !result.usesProviderDefinedReasoningEffort) {
            // Do not promote the native "medium" fallback into an explicit CLI option.
            delete result.initialReasoningEffort;
        }
        return result;
    }
    function picker(h, options, config = {}, scope, isRemote = false) {
        const handle = new h.CliModelPickerHandle(options);
        if (isRemote || options.targetKind !== "session" || scope === "repo" || scope === "local" ||
            !builtinSession(h, options.sessionId)) return handle;
        const effortChoices = new Set(), tierChoices = new Set();
        function project() {
            const initial = rows(handle);
            for (const row of initial.rows) {
                if (row.current || row.value === "auto" || row.availability !== "available") continue;
                const desired = defaults(h, row, config);
                if (!effortChoices.has(row.value) && present(desired.effort) && row.effort !== desired.effort)
                    handle.setReasoningEffort(row.value, desired.effort);
                if (!tierChoices.has(row.value) && present(desired.tier) && row.contextTier !== desired.tier)
                    handle.setContextTier(row.value, desired.tier);
            }
            const projection = rows(handle);
            const preferred = projection.rows.find(row => row.value === config.model && row.availability === "available");
            return {...projection, rows: projection.rows.map(row => {
                const desired = defaults(h, row, config);
                const result = {...row};
                if (preferred) result.isDefault = row.value === preferred.value;
                if (!row.current && row.availability === "available" && row.value !== "auto") {
                    // Native prefilled values are also flagged "Explicit"; track real UI choices instead.
                    result.reasoningEffortExplicit = effortChoices.has(row.value) ||
                        (present(config.effortLevel) && config.effortLevel === desired.effort);
                    result.contextTierExplicit = tierChoices.has(row.value) ||
                        (present(config.contextTier) && config.contextTier === desired.tier);
                }
                if (row.reasoningPicker && present(desired.effort)) {
                    const items = row.reasoningPicker.items.map(item => ({
                        ...item, isDefault: item.value === desired.effort
                    }));
                    const index = items.findIndex(item => item.value === (row.effort ?? desired.effort));
                    result.reasoningPicker = {
                        ...row.reasoningPicker, items,
                        initialIndex: index < 0 ? row.reasoningPicker.initialIndex : index
                    };
                }
                return result;
            })};
        }
        return {
            snapshot: project,
            setReasoningEffort(modelId, effort) {
                handle.setReasoningEffort(modelId, effort);
                effortChoices.add(modelId);
                return project();
            },
            setContextTier(modelId, tier) {
                handle.setContextTier(modelId, tier);
                tierChoices.add(modelId);
                return project();
            },
            postEnablement(modelId) {
                const result = handle.postEnablement(modelId);
                const row = project().rows.find(item => item.value === modelId && item.availability === "available");
                return row ? {...result, contextTier: row.contextTier,
                    reasoningPicker: row.reasoningPicker ?? result.reasoningPicker} : result;
            }
        };
    }
    async function initialize(h, handle, session, input) {
        const before = handle.refresh().snapshot;
        const result = await handle.initialize(input);
        const selected = result.snapshot;
        if (input.isRemote || selected.isAuto || !selected.selectedModel ||
            !builtinSession(h, session.sessionId)) return result;
        try {
            const row = modelRow(h, session.sessionId, selected.selectedModel, selected);
            if (!row) return result;
            const desired = defaults(h, row, {
                effortLevel: input.fallbackReasoningEffort, contextTier: input.fallbackContextTier
            });
            const effort = !present(input.cliReasoningEffort) && !present(before.reasoningEffort)
                ? desired.effort ?? selected.reasoningEffort : selected.reasoningEffort;
            const tier = !present(input.cliContextTier) && !present(before.contextTier)
                ? desired.tier ?? selected.contextTier : selected.contextTier;
            if (effort === selected.reasoningEffort && tier === selected.contextTier) return result;
            const changed = await session.model.switchTo({
                modelId: selected.selectedModel, reasoningEffort: effort, contextTier: tier,
                source: "startup", modelChangeScope: "session"
            });
            if (changed.status !== "applied" && changed.status !== "unchanged")
                throw new Error(`Copilot defaults patch: startup selection ${changed.status}`);
            const refreshed = handle.refresh();
            return {...result, ...refreshed, snapshot: {...result.snapshot, ...refreshed.snapshot}};
        } catch (error) {
            await session.log({level: "error", type: "model_defaults_patch",
                message: error instanceof Error ? error.message : String(error)});
            throw error;
        }
    }
    async function switchTo(h, session, input) {
        if (session.isRemote || input.repoScope || input.modelId === "auto" ||
            !["model_command", "model_picker"].includes(input.source) ||
            !builtinSession(h, session.sessionId)) return session.model.switchTo(input);
        const context = input.pickerPersistence?.settingsContext ?? {
            configDir: session.getConfigDir(), homeDirectory: h.pathOsHomeDir(), environment: process.env
        };
        const loaded = await h.userSettingsLoadWithWarning(context);
        if (loaded.warning) throw new Error(loaded.warning);
        const config = loaded.settings ?? {};
        const selected = current(h, session.sessionId);
        const row = modelRow(h, session.sessionId, input.modelId, selected);
        if (!row) return session.model.switchTo(input);
        const desired = defaults(h, row, config);
        const sameModel = input.modelId === selected.selectedModel;
        const next = {...input};
        if (!present(next.reasoningEffort))
            next.reasoningEffort = (sameModel ? selected.reasoningEffort : undefined) ?? desired.effort;
        if (!present(next.contextTier))
            next.contextTier = (sameModel ? selected.contextTier : undefined) ?? desired.tier;
        return session.model.switchTo(next);
    }
    function headless(h, input, initialEffort) {
        const result = h.modelCliHeadlessConfiguration(input);
        if (result.fatalError || input.providerConfigured || input.altProvidersEnabled ||
            input.agentModel || input.customAgentModel || input.initialAgentMode === "plan" ||
            result.effectiveModel === "auto" || !builtinSession(h, input.sessionId)) return result;
        const selected = current(h, input.sessionId);
        const row = modelRow(h, input.sessionId, result.effectiveModel ?? input.selectedModel, selected);
        if (!row) return result;
        const desired = defaults(h, row, {
            effortLevel: input.configReasoningEffort,
            contextTier: launch.cliContextTier ?? launch.configContextTier
        });
        if (!present(input.cliReasoningEffort) && !present(initialEffort) &&
            !present(input.configReasoningEffort) && present(desired.effort))
            result.reasoningEffort = desired.effort;
        if (!present(selected.contextTier) && present(desired.tier))
            result.__tmyContextTier = desired.tier;
        return result;
    }
    function headlessOptions(result) {
        return {reasoningEffort: result.reasoningEffort,
            ...(present(result.__tmyContextTier) ? {contextTier: result.__tmyContextTier} : {})};
    }
    return {startup, picker, initialize, switchTo, headless, headlessOptions};
})();
/*tmy-native-defaults-end*/
"""


def js_object_end(src, start):
    """Read the object literals at the selected call sites, ignoring quoted text/comments."""
    depth, quote, escaped, i = 0, None, False, start
    while i < len(src):
        ch = src[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end < 0:
                raise ValueError("unterminated comment in native call")
            i = end + 1
        elif src.startswith("//", i):
            end = src.find("\n", i + 2)
            if end < 0:
                raise ValueError("unterminated line comment in native call")
            i = end
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unterminated object in native call")


def native_hooks_complete(src, marker):
    hooks = ("startup", "picker", "initialize", "headless", "headlessOptions")
    return (src.count(f"/*{marker}*/") == 1 and
            "/*tmy-native-defaults-end*/" in src and
            all(src.count(f"__tmyNativeDefaults.{name}(") == 1 for name in hooks) and
            src.count("__tmyNativeDefaults.switchTo(") == 2)


def upgrade_native_v1(src):
    """Upgrade the known v1 helper without restoring stock code or losing unrelated bundle edits."""
    marker = "tmy-native-defaults-v1"
    start = src.find(f"/*{marker}*/")
    end_marker = "/*tmy-native-defaults-end*/"
    end = src.find(end_marker, start)
    if start < 0 or end < 0 or not native_hooks_complete(src, marker):
        return None, "incomplete v1 native hooks; refusing to upgrade", "skip"
    end += len(end_marker)
    if hashlib.sha256(src[start:end].encode()).hexdigest() != NATIVE_V1_DIGEST:
        return None, "v1 native helper was modified; refusing to overwrite it", "skip"
    calls = list(re.finditer(
        r'__tmyNativeDefaults\.picker\(([\w$]+),(\{[^{}]*\}),__tmySettings,([\w$]+)\),\[([^\]]*)\]', src))
    if len(calls) != 1:
        return None, f"v1 picker hook count={len(calls)} (want 1)", "skip"
    call = calls[0]
    alias, options, scope, deps = call.groups()
    sessions = re.findall(r'(?:\{|,)sessionId:([\w$]+)\.sessionId', options)
    if len(sessions) != 1 or call.start() < end:
        return None, "v1 picker session binding changed", "skip"
    session = sessions[0]
    replacement = (f"__tmyNativeDefaults.picker({alias},{options},__tmySettings,{scope},"
                   f"{session}.isRemote===!0),[{session}.isRemote,{deps}]")
    src = src[:call.start()] + replacement + src[call.end():]
    src = src[:start] + NATIVE_HELPER.strip() + src[end:]
    return src, "native defaults v1 -> v2: preserve remote picker defaults", "apply"


def p_native_defaults(src):
    """Adapt CLI-facing native boundaries as one group; never patch the shared native exports."""
    if NATIVE_MARKER in src:
        start = src.find(f"/*{NATIVE_MARKER}*/")
        end = src.find("/*tmy-native-defaults-end*/", start)
        if start >= 0 and end >= 0 and (
                src[start:end + len("/*tmy-native-defaults-end*/")] != NATIVE_HELPER.strip()):
            return None, "native helper differs from this script; revert to the backup before reapplying", "skip"
        if native_hooks_complete(src, NATIVE_MARKER):
            return None, "", "already"
        return None, "native defaults marker exists but the hook group is incomplete", "skip"
    if "tmy-native-defaults-v1" in src:
        return upgrade_native_v1(src)
    if "__tmyNativeDefaults" in src or "tmy-native-defaults-v" in src:
        return None, "unknown native defaults revision; restore the matching backup first", "skip"
    edits = []

    def one(pattern, text=src, label="anchor"):
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise ValueError(f"{label} count={len(matches)} (want 1)")
        return matches[0]

    try:
        ctor = one(r'new ([\w$]+)\.CliModelPickerHandle\((\{[^{}]*\})\),\[([^\]]*)\]',
                   label="native picker construction")
        alias, options, deps = ctor.groups()
        components = []
        back = max(0, ctor.start() - 6000)
        for candidate in re.finditer(r'([\w$]+)=\(\{', src[back:ctor.start()]):
            start = back + candidate.end() - 1
            end = js_object_end(src, start)
            props = src[start + 1:end - 1]
            if end < ctor.start() and src[end:end + 4] == ")=>{" and (
                    "configDir:" in props and "resolvedCurrentModel:" in props):
                components.append((candidate.group(1), props, start + 1))
        if len(components) != 1:
            raise ValueError(f"native picker component count={len(components)} (want 1)")
        name, props, props_start = components[0]
        scope = one(r'(?:^|,)scope:([\w$]+)', props, "picker scope").group(1)
        session = one(r'(?:\{|,)sessionId:([\w$]+)\.sessionId',
                      options, "picker session").group(1)
        edits.append((props_start, props_start, "__tmySettings:__tmySettings,"))
        edits.append((ctor.start(), ctor.end(),
                      f"__tmyNativeDefaults.picker({alias},{options},__tmySettings,{scope},"
                      f"{session}.isRemote===!0),[{session}.isRemote,"
                      f"__tmySettings?.model,__tmySettings?.effortLevel,"
                      f"__tmySettings?.contextTier,{deps}]"))

        caller = one(r'\.createElement\(' + re.escape(name) + r',\{modelListRevision:',
                     label="native picker caller")
        nearby = src[max(0, caller.start() - 6000):caller.start()]
        config = one(r'config:([\w$]+),builtInDeclaredModels:', nearby, "picker config").group(1)
        prop_start = src.index("{", caller.start())
        edits.append((prop_start + 1, prop_start + 1, f"__tmySettings:{config},"))

        for native_name, hook in (("modelCliStartupConfiguration", "startup"),
                                  ("modelCliHeadlessConfiguration", "headless")):
            call = one(re.escape(alias) + r'\.' + native_name + r'\(\{', label=native_name)
            obj_start = call.end() - 1
            obj_end = js_object_end(src, obj_start)
            if src[obj_end] != ")":
                raise ValueError(f"{native_name} argument shape changed")
            extra = ""
            if hook == "headless":
                initial = one(r'initialModel:([\w$]+)\.modelId',
                              src[obj_start:obj_end], "headless initial model").group(1)
                extra = f",{initial}.reasoningEffort"
            edits.append((call.start(), obj_end + 1,
                          f"__tmyNativeDefaults.{hook}({alias},{src[obj_start:obj_end]}{extra})"))

        init = one(r'([\w$]+)\.initialize\((\{cliModel:[^{}]*'
                   r'isRemote:([\w$]+)\.isRemote===!0\})\)', label="interactive model initialization")
        handle, args, session = init.groups()
        edits.append((init.start(), init.end(),
                      f"__tmyNativeDefaults.initialize({alias},{handle},{session},{args})"))

        switches = {"picker": [], "command": []}
        for call in re.finditer(r'([\w$]+(?:\.[\w$]+)*)\.model\.switchTo\(\{', src):
            start = call.end() - 1
            end = js_object_end(src, start)
            args = src[start:end]
            if src[end] != ")":
                continue
            if "pickerPersistence:{" in args and "compactionDecision:" in args:
                switches["picker"].append((call, end, args))
            elif call.group(1).endswith(".session.instance") and all(
                    key in args for key in ("modelChangeScope:", "compactionDecision:", "source:")):
                switches["command"].append((call, end, args))
        for kind, calls in switches.items():
            if len(calls) != 1:
                raise ValueError(f"{kind} model switch count={len(calls)} (want 1)")
            call, end, args = calls[0]
            edits.append((call.start(), end + 1,
                          f"__tmyNativeDefaults.switchTo({alias},{call.group(1)},{args})"))

        update = one(r'([\w$]+)\.reasoningEffort!==void 0&&await Promise\.resolve\('
                     r'([\w$]+)\.options\.update\(\{reasoningEffort:\1\.reasoningEffort\}\)\)',
                     label="headless effort application")
        result, session = update.groups()
        edits.append((update.start(), update.end(),
                      f"({result}.reasoningEffort!==void 0||{result}.__tmyContextTier!==void 0)"
                      f"&&await Promise.resolve({session}.options.update("
                      f"__tmyNativeDefaults.headlessOptions({result})))"))
        edits.sort()
        if any(left[1] > right[0] for left, right in zip(edits, edits[1:])):
            raise ValueError("native defaults edits overlap")
    except ValueError as error:
        return None, str(error), "skip"

    for start, end, replacement in reversed(edits):
        src = src[:start] + replacement + src[end:]
    header = src.find("\n") + 1 if src.startswith("#!") else 0
    src = src[:header] + NATIVE_HELPER + src[header:]
    return src, f"native CLI defaults: {len(edits)} coordinated edits (no binary changes)", "apply"


PATCHES = [
    ("retry-maxretries", p_retry),
    ("effort-default",   p_effort),
    ("tiers-clearpoint", p_tiers),
    ("tiers-live",       p_tiers_live),
    ("tiers-picker",     p_tiers_picker),
    ("tiers-startup",    p_tiers_startup),
]

# ============================ 主流程 ============================
def do_revert(files):
    n = 0
    for f in files:
        bak = f + BACKUP_SUFFIX
        if os.path.exists(bak):
            shutil.copy2(bak, f); n += 1
            print(f"  reverted: {f}")
    print(f"\nreverted {n} file(s); backups retained.")

def process(path, node):
    src0 = open(path, encoding="utf-8").read()
    cur = src0
    lines, ok = [], True
    native = "CliModelPickerHandle" in src0
    patches = [("native-model-defaults", p_native_defaults)] if native else PATCHES
    for name, fn in patches:
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
    if native and not ok:
        print("    -> not written: the patch group is incomplete"); return False
    if not node:
        print("    -> not written: node is required for syntax validation"); return False
    r = subprocess.run([node, "--check", "--input-type=module"], input=cur,
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"    -> not written: node --check failed: {r.stderr.strip()[:300]}"); return False
    if open(path, encoding="utf-8").read() != src0:
        print("    -> not written: app.js changed during patching"); return False
    if not os.path.exists(path + BACKUP_SUFFIX):
        shutil.copy2(path, path + BACKUP_SUFFIX)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path),
                                     prefix=".tmy-app-", delete=False) as staging:
        staging.write(cur)
        staging.flush()
        os.fsync(staging.fileno())
    try:
        shutil.copystat(path, staging.name)
        os.replace(staging.name, path)
    except OSError:
        print(f"    -> write failed; staging file retained: {staging.name}")
        raise
    print("    -> written atomically + node --check ok")
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
        print("(dry-run; re-run with --apply to write. 只对新进程生效；auto-update 后重跑。)")
    if STRICT and not all_ok:
        print("STRICT: 有 patch SKIP 或 node --check 失败（见上）—— 锚点腐坏，需手动逆向。"
              "（N/A 是上游移除该特性，不计入失败。）")
        sys.exit(1)

if __name__ == "__main__":
    main()
