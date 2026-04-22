#!/usr/bin/env bash
# autopilot cron wrapper：独占锁 + 额度检查（含 sleep 等 reset）+ 日志 + 派发 hermes
# 用法：wrapper.sh <task_id>
# 环境变量（可选覆盖）：
#   AUTOPILOT_PROFILE       hermes profile 名，默认 autopilot
#   AUTOPILOT_5H_THRESHOLD     5H 额度熔断阈值，默认 0.1
#   AUTOPILOT_WEEKLY_THRESHOLD  weekly 额度熔断阈值，默认 0.05
#   AUTOPILOT_LOG           日志路径，默认 ~/.local/log/autopilot.log
#   AUTOPILOT_LOCK_WARN     锁超时告警秒数，默认 3600（1h）
set -euo pipefail

TASK_ID="${1:?用法: wrapper.sh <task_id>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK_FILE="/tmp/autopilot-${TASK_ID}.lock"
LOCK_WARN_FLAG="/tmp/autopilot-${TASK_ID}-lock-warned"
LOCK_WARN_SECONDS="${AUTOPILOT_LOCK_WARN:-3600}"
PROFILE="${AUTOPILOT_PROFILE:-autopilot}"
LOG_FILE="${AUTOPILOT_LOG:-$HOME/.local/log/autopilot.log}"

# ── 额度 reset 时间分段表（本地时区，小时数）──
# MiniMax Coding Plan 在这些时间点重置 interval 额度
# 后续如有变化直接改这一行
RESET_HOURS=(0 5 10 15 20)

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date -Iseconds) | task=${TASK_ID} | $1" >> "$LOG_FILE"
}

seconds_until_next_reset() {
    local now_s=$(( $(date +%-H) * 3600 + $(date +%-M) * 60 + $(date +%-S) ))
    for h in "${RESET_HOURS[@]}"; do
        local reset_s=$(( h * 3600 ))
        if (( reset_s > now_s )); then
            echo $(( reset_s - now_s ))
            return
        fi
    done
    echo $(( RESET_HOURS[0] * 3600 + 86400 - now_s ))
}

notify() {
    hermes -p "$PROFILE" chat --yolo -Q \
        "向用户发消息：$1" 2>/dev/null || true
}

# check_quota.py 退出码：0=充足 1=5H不足 2=weekly耗尽 3=错误
check_quota() {
    uv run "$SCRIPT_DIR/check_quota.py" 2>/dev/null
}

# 读 hermes .env 获取 MINIMAX_CN_API_KEY
for envfile in \
    "$HOME/.hermes/profiles/${PROFILE}/.env" \
    "$HOME/.hermes/.env"; do
    [ -f "$envfile" ] && set -a && source "$envfile" && set +a
done

# 1. 独占锁
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    if [ -f "$LOCK_FILE" ]; then
        lock_age=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE") ))
        if (( lock_age >= LOCK_WARN_SECONDS )) && [ ! -f "$LOCK_WARN_FLAG" ]; then
            log "action=lock_stuck | age=${lock_age}s"
            notify "[autopilot] ${TASK_ID} 有一个 session 已跑 $(( lock_age / 60 )) 分钟还没结束，可能卡住了"
            touch "$LOCK_WARN_FLAG"
        else
            log "action=skip | reason=locked"
        fi
    fi
    exit 0
fi
rm -f "$LOCK_WARN_FLAG"

# 2. 额度检查
check_quota
quota_rc=$?

if (( quota_rc == 2 )); then
    # weekly 耗尽，等 reset 也没用
    log "action=quota_weekly | reason=weekly 耗尽"
    notify "[autopilot] ${TASK_ID} weekly 额度耗尽，等下周重置；cron 继续跑，恢复后自动继续"
    exit 0

elif (( quota_rc == 1 )); then
    # 5H 不足，sleep 等下一个 reset 点
    WAIT=$(seconds_until_next_reset)
    WAIT_MIN=$(( WAIT / 60 ))
    log "action=quota_5h_wait | wait=${WAIT_MIN}m | next_reset=$(date -d "+${WAIT} seconds" +%H:%M)"
    notify "[autopilot] ${TASK_ID} 5H 额度不足，等 ${WAIT_MIN} 分钟 reset（$(date -d "+${WAIT} seconds" +%H:%M)）"

    sleep "$WAIT"

    # 醒来重新检查
    check_quota
    quota_rc2=$?

    if (( quota_rc2 == 0 )); then
        log "action=quota_recovered"
        notify "[autopilot] ${TASK_ID} 额度已恢复，继续执行"
    elif (( quota_rc2 == 2 )); then
        log "action=quota_weekly | reason=5H reset 后发现 weekly 耗尽"
        notify "[autopilot] ${TASK_ID} weekly 额度耗尽，等下周重置"
        exit 0
    else
        # 还是 5H 不足，可能时间分段表不准
        log "action=quota_5h_still_short | reason=reset 后 5H 仍不足，检查 RESET_HOURS"
        notify "[autopilot] ${TASK_ID} reset 后 5H 额度仍不足，RESET_HOURS 时间点可能不准，请检查"
        exit 0
    fi

elif (( quota_rc >= 3 )); then
    log "action=quota_error | rc=${quota_rc}"
    exit 0
fi

# 3. 派发 hermes
log "action=dispatch"
exec hermes -p "$PROFILE" chat --yolo -Q -s autopilot \
    "task_id=${TASK_ID}; 按 autopilot runbook 推进一轮"
