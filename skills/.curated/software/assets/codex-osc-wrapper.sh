#!/usr/bin/env bash

# Codex wrapper for terminals whose default foreground/background are queried
# through OSC 10/11. Put this file earlier in PATH as `codex`, and point
# CODEX_REAL_BIN to the real Codex executable.

set -u

script_path="$(readlink -f "$0" 2>/dev/null || printf '%s\n' "$0")"
real_codex="${CODEX_REAL_BIN:-}"
if [ -z "$real_codex" ]; then
    IFS=':' read -r -a path_entries <<< "${PATH:-}"
    for dir in "${path_entries[@]}"; do
        candidate="${dir}/codex"
        [ -x "$candidate" ] || continue
        candidate_path="$(readlink -f "$candidate" 2>/dev/null || printf '%s\n' "$candidate")"
        if [ "$candidate_path" != "$script_path" ]; then
            real_codex="$candidate"
            break
        fi
    done
fi
if [ -z "$real_codex" ]; then
    printf 'codex-osc-wrapper: set CODEX_REAL_BIN to the real codex executable\n' >&2
    exit 127
fi
fg="${CODEX_OSC_FG:-#424242}"
bg="${CODEX_OSC_BG:-#f1f1f1}"
interval="${CODEX_OSC_REFRESH_INTERVAL:-30}"
burst_count="${CODEX_OSC_BURST_COUNT:-3}"
burst_interval="${CODEX_OSC_BURST_INTERVAL:-1}"

emit_osc_colors() {
    if [ -e /dev/tty ]; then
        printf '\033]10;%s\007\033]11;%s\007' "$fg" "$bg" 2>/dev/null > /dev/tty || true
    fi
}

emit_osc_colors

if [ "${CODEX_OSC_KEEPALIVE:-1}" = "0" ]; then
    exec "$real_codex" "$@"
fi

burst_osc_colors() {
    count=1
    while [ "$count" -lt "$burst_count" ]; do
        sleep "$burst_interval" || break
        emit_osc_colors
        count=$((count + 1))
    done
}

keep_colors_alive() {
    burst_osc_colors
    while true; do
        sleep "$interval" || break
        emit_osc_colors
    done
}

keep_colors_alive &
keeper_pid=$!

cleanup() {
    kill "$keeper_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM HUP
trap emit_osc_colors WINCH CONT

"$real_codex" "$@"
status=$?
cleanup
wait "$keeper_pid" 2>/dev/null || true
exit "$status"
