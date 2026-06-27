#!/usr/bin/env bash
# Build a single-file React HTML recap report for one Copilot CLI session.
#
# Usage:
#   build_react_report.sh <session-id> [output.html] [--summary <fragment.html>]
#
# Pipeline (data layer is shared with the vanilla path — the React side never
# re-parses events.jsonl in JS, it only consumes the exported JSON):
#   1. export_session_json.py <sid>  -> react/src/session.json
#   2. (optional) --summary <frag.html>: baked in at build time via
#      RECAP_SUMMARY_PATH and rendered raw (trusted local HTML) at the top.
#   3. pnpm install (first run only) + pnpm build  -> dist/index.html
#   4. move dist/index.html -> <output.html> (default: ./session-recap-react-<sid8>-<ts>.html)
#
# Requires: uv, pnpm, node. The vanilla path (dump_session.py) needs none of
# these — use it when you want zero-build. Use this for the richer visual.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REACT="$HERE/react"

sid=""; out=""; summary=""
while [ $# -gt 0 ]; do
  case "$1" in
    --summary)   summary="$2"; shift 2 ;;
    --summary=*) summary="${1#*=}"; shift ;;
    -h|--help)   sed -n '2,18p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) if [ -z "$sid" ]; then sid="$1"; elif [ -z "$out" ]; then out="$1"; fi; shift ;;
  esac
done
[ -n "$sid" ] || { echo "usage: build_react_report.sh <session-id> [out.html] [--summary frag.html]" >&2; exit 2; }

ts="$(date +%Y%m%d-%H%M%S)"
[ -n "$out" ] || out="$PWD/session-recap-react-${sid:0:8}-${ts}.html"
# absolutise (we cd into $REACT before building)
case "$out" in /*) ;; *) out="$PWD/$out" ;; esac
[ -n "$summary" ] && case "$summary" in /*) ;; *) summary="$PWD/$summary" ;; esac

echo "==> export session.json  (session $sid)"
uv run --with markdown python3 "$HERE/export_session_json.py" "$sid" "$REACT/src/session.json"

cd "$REACT"
[ -d node_modules ] || { echo "==> pnpm install"; pnpm install; }

echo "==> pnpm build${summary:+  (with summary: $summary)}"
if [ -n "$summary" ]; then
  RECAP_SUMMARY_PATH="$summary" pnpm build
else
  pnpm build
fi

mkdir -p "$(dirname "$out")"
mv dist/index.html "$out"
echo "==> wrote $out  ($(du -h "$out" | cut -f1))"
