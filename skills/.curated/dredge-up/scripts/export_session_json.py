#!/usr/bin/env python3
"""Export one session's merged timeline to JSON for the React report
renderer (scripts/react/).

Reuses dump_session.py's data layer (events.jsonl preferred, db.turns
fallback). Output shape matches what react/src/App.tsx expects:

    { sessionId, name, cwd, repo, branch, sessionStart, sourceLabel,
      entries: [
        { kind: 'merged-tool', entry: {...} } |
        { kind: 'passthrough', entry: {...} }
      ] }

Run from anywhere; default output is react/src/session.json (override with
the second CLI arg).
"""
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dump_session import (  # type: ignore
    fetch_db_meta, fetch_db_turns, parse_events_jsonl, turns_to_entries,
    merge_tool_entries, _parse_iso, DEFAULT_DB, DEFAULT_STATE,
)


def to_iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt


def serialise(entries):
    """Convert datetime fields to ISO strings."""
    out = []
    for item in entries:
        if item["kind"] == "skip":
            continue
        e = dict(item["entry"])
        if "timestamp" in e:
            e["timestamp"] = to_iso(e["timestamp"])
        out.append({"kind": item["kind"], "entry": e})
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: export_session_json.py <session-id> [out.json]")
    sid = sys.argv[1]
    out = (sys.argv[2] if len(sys.argv) > 2
           else os.path.join(HERE, "react", "src", "session.json"))

    meta = fetch_db_meta(DEFAULT_DB, sid)
    if not meta:
        sys.exit(f"session {sid} not in db")
    name, cwd, repo, branch, created_at = meta

    ev = os.path.join(DEFAULT_STATE, sid, "events.jsonl")
    if os.path.exists(ev):
        entries, session_start = parse_events_jsonl(ev)
        source = "events.jsonl"
    else:
        turns = fetch_db_turns(DEFAULT_DB, sid)
        entries = turns_to_entries(turns)
        session_start = _parse_iso(created_at)
        source = "db.turns"

    from datetime import timezone
    merged = merge_tool_entries(entries)
    data = {
        "sessionId": sid, "name": name, "cwd": cwd,
        "repo": repo, "branch": branch,
        "sessionStart": to_iso(session_start),
        # baked at export time so the React view can compute elapsed
        # without drifting whenever the page is reopened
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "sourceLabel": source,
        "entries": serialise(merged),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"wrote {len(data['entries'])} entries -> {out}  ({source})")


if __name__ == "__main__":
    main()
