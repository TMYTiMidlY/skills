#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""检查 MiniMax Coding Plan 额度。

退出码：
  0 = 额度充足
  1 = 5H 额度不足（等 reset 可恢复）
  2 = weekly 额度不足（等 reset 也没用）
  3 = 其他错误

注意：API 返回的 usage_count 是"剩余可用次数"而非"已用次数"。

环境变量：
  MINIMAX_CN_API_KEY          必需
  AUTOPILOT_5H_THRESHOLD      5H 额度熔断阈值，默认 0.1（剩余 10%）
  AUTOPILOT_WEEKLY_THRESHOLD  weekly 额度熔断阈值，默认 0.05（剩余 5%）
"""

import json
import os
import sys
import urllib.request

api_key = os.environ.get("MINIMAX_CN_API_KEY")
if not api_key:
    print("需要 MINIMAX_CN_API_KEY", file=sys.stderr)
    sys.exit(3)

h5_threshold = float(os.environ.get("AUTOPILOT_5H_THRESHOLD", "0.1"))
weekly_threshold = float(os.environ.get("AUTOPILOT_WEEKLY_THRESHOLD", "0.05"))

try:
    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
except Exception as e:
    print(f"请求额度 API 失败: {e}", file=sys.stderr)
    sys.exit(3)

for m in data.get("model_remains", []):
    model_name = m.get("model_name", "")
    if model_name.startswith("MiniMax-M"):
        iv_total = m["current_interval_total_count"]
        wk_total = m["current_weekly_total_count"]
        iv_rate = m["current_interval_usage_count"] / iv_total if iv_total else 0
        wk_rate = m["current_weekly_usage_count"] / wk_total if wk_total else 0

        # weekly 先查：weekly 不足时 5H reset 也没用
        if wk_rate <= weekly_threshold:
            print(f"weekly 耗尽：剩余 {wk_rate:.1%} <= {weekly_threshold:.1%}")
            sys.exit(2)

        # 5H 不足：等 reset 可恢复
        if iv_rate <= h5_threshold:
            print(f"5H 不足：剩余 {iv_rate:.1%} <= {h5_threshold:.1%}")
            sys.exit(1)

        print(f"额度充足：5H {iv_rate:.1%} / weekly {wk_rate:.1%}")
        sys.exit(0)

print(f"未找到 MiniMax-M* 模型数据，现有模型：{[m.get('model_name') for m in data.get('model_remains', [])]}", file=sys.stderr)
sys.exit(3)
