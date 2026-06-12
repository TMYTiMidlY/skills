#!/usr/bin/env bash
# 把 Copilot CLI 的 transient API error 重试策略改宽松一点。
#
# 改了什么：
#   1) retryPolicy.maxRetries 默认 5 → 10
#   2) 非-API 错误（连接挂掉、HTTP/2 GOAWAY 之类）的每次重试等待时长加 4 秒下限
#      原 jitter 公式 _t = _e * (0.8 + Math.random()*0.4) 单次最低 < 1s，
#      改成 _t = Math.max(_e * (0.8 + Math.random()*0.4), 4)
#
# 效果：原来 "retried 5 times (total retry wait time: 6.00 seconds)" → 
#       约 10 次 × ≥4s = 40+ 秒后才放弃，能吃掉常见的网络抖动。
#
# 幂等：每个 patch 点带 /*tmy-retry-patch*/ marker，已 patch 的文件会跳过。
# 备份：每个 app.js 同目录留 app.js.orig.timidly-bak。
# 覆盖范围：扫描所有 Copilot CLI pkg cache 目录，把每个版本的 app.js 都 patch 掉。
#   CLI auto-update 拉新版本后需要再跑一次本脚本。

set -uo pipefail

MARKER='tmy-retry-patch'

# 收集所有可能的 pkg 根目录（与 Copilot CLI 自己的查找顺序对齐）
declare -A SEEN
add_root() {
  local d="$1"
  [[ -n "$d" && -d "$d" ]] || return 0
  SEEN["$d"]=1
}
add_root "${COPILOT_CACHE_HOME:-}/pkg"
add_root "${XDG_CACHE_HOME:-$HOME/.cache}/copilot/pkg"
case "$(uname -s)" in
  Darwin) add_root "$HOME/Library/Caches/copilot/pkg" ;;
esac
add_root "${COPILOT_HOME:-}/pkg"
add_root "$HOME/.copilot/pkg"

patched=0
skipped_done=0
skipped_layout=0
failed=0

for pkg_root in "${!SEEN[@]}"; do
  while IFS= read -r app_js; do
    [[ -f "$app_js" ]] || continue

    if grep -q "$MARKER" "$app_js" 2>/dev/null; then
      skipped_done=$((skipped_done + 1))
      continue
    fi

    # 检查两个 patch 锚点都在
    if ! grep -q 'retryPolicy:{maxRetries:e?.retryPolicy?.maxRetries??5,' "$app_js" 2>/dev/null; then
      echo "  unknown layout (skip): $app_js" >&2
      skipped_layout=$((skipped_layout + 1))
      continue
    fi

    cp -p "$app_js" "$app_js.orig.timidly-bak"

    if node -e '
      const fs = require("fs");
      const p = process.argv[1];
      let s = fs.readFileSync(p, "utf8");
      const marker = "/*tmy-retry-patch*/";

      // Patch 1: maxRetries 默认 5 → 10
      const re1 = /(retryPolicy:\{maxRetries:e\?\.retryPolicy\?\.maxRetries\?\?)5,/;
      if (!re1.test(s)) throw new Error("anchor 1 missing");
      s = s.replace(re1, `$110${marker},`);

      // Patch 2: 非-API 错误重试每次最低等 4 秒
      // 形如 let It=.8+Math.random()*.4,_t=_e*It  →  ...,_t=Math.max(_e*It,4)
      const re2 = /let (\w+)=\.8\+Math\.random\(\)\*\.4,(\w+)=(\w+)\*\1/g;
      const before = s;
      s = s.replace(re2, `let $1=.8+Math.random()*.4,$2=Math.max($3*$1,4)${marker}`);
      if (s === before) throw new Error("anchor 2 missing");

      fs.writeFileSync(p, s);
    ' "$app_js"; then
      patched=$((patched + 1))
      echo "  patched: $app_js"
    else
      # 还原
      cp -p "$app_js.orig.timidly-bak" "$app_js"
      failed=$((failed + 1))
      echo "  FAILED, reverted: $app_js" >&2
    fi
  done < <(find "$pkg_root" -mindepth 3 -maxdepth 4 -name 'app.js' -type f 2>/dev/null)
done

echo ""
echo "Summary: patched=$patched  already-patched=$skipped_done  unknown-layout=$skipped_layout  failed=$failed"

[[ $failed -gt 0 ]] && exit 1 || exit 0
