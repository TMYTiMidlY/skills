#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown>=3.5"]
# ///
"""dredge-up dump — reconstruct one Copilot CLI session's full timeline offline,
reproducing the exact DOM that the bundle's `/share html` (alias `/export
html`) writes for the same session. CSS/JS are reused verbatim from the
bundle (see assets/share-export.{css,js}); this script's job is to produce a
DOM the bundle's stylesheet + script can drive.

Why this exists: the agent's own in-context view of a long session is *lossy*
— early turns get compressed or dropped from the context window. The full
event stream survives on disk and is the only reliable way to recover what
the user actually asked for across the whole session.

Data sources, in priority order:
  1. `~/.copilot/session-state/<id>/events.jsonl` — the live timeline event
     log, identical source `/share html` reads in-memory. Gives every entry
     type (User / Copilot / Reasoning / Tools / Notifications / …).
  2. `~/.copilot/session-store.db` `turns` table — fallback for older
     sessions whose events.jsonl was pruned. Produces user/copilot only.

The events → timeline-entry mapping, the per-type DOM (`nJn`), the merging
of `tool.execution_start/complete` into one tool entry (`iFs`), and the
filter-pill / sticky-header / sidebar shell (`hFs`) are all reverse-
engineered from the @github/copilot bundle; see software/references/
copilot.md §"`/share html` 对话导出（逆向）" for the full notes.

Usage:
    uv run dump_session.py <session-id> [--format text|html] [--out PATH]
                                        [--summary PATH] [--db PATH]
                                        [--events PATH]
    # plain `python3` also works (markdown then falls back to <pre>).

Localisation: visible labels are Chinese (用户 / Copilot / 推理 / 工具 / …);
`data-type` attributes are kept English because the bundle's JS filters on
them, not on label text.
"""
import argparse
import html
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

DEFAULT_DB = os.path.expanduser("~/.copilot/session-store.db")
DEFAULT_STATE = os.path.expanduser("~/.copilot/session-state")
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


# ─────────────────────────────────────────────────── data layer ──────────────
def fetch_db_meta(db, sid):
    """Pull name/cwd/repo/branch from sessions table (always available)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT summary, cwd, repository, branch, created_at "
            "FROM sessions WHERE id=?",
            (sid,),
        )
        return cur.fetchone()
    finally:
        con.close()


def fetch_db_turns(db, sid):
    """Fallback timeline source: just user_message / assistant_response."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT turn_index, user_message, assistant_response, timestamp "
            "FROM turns WHERE session_id=? ORDER BY turn_index",
            (sid,),
        )
        return cur.fetchall()
    finally:
        con.close()


# ─────────────────────────────────────── events.jsonl → timeline entries ─────
# Mirrors the bundle's event→entry mapping (see copilot.md §share-html):
#   user.message              -> {type:user, text}
#   assistant.message         -> {type:reasoning, text} + {type:copilot, text}
#                                (toolRequests handled via tool.* events)
#   tool.execution_start      -> {type:tool_call_requested, callId, name, args}
#   tool.execution_complete   -> {type:tool_call_completed, callId, result}
#   system.notification       -> {type:system_notification, text, detail?}
#   session.model_change      -> {type:info, text:"切换到模型 X"}
# hook.* / assistant.turn_* / session.start / system.message (long system
# prompt) are dropped — they would be noise in the report.
def parse_events_jsonl(path):
    """Returns (entries, session_start_dt). entries are timeline-entry
    dicts ready for iFs+nJn rendering."""
    entries = []
    session_start = None
    eid = 0

    def new_id():
        nonlocal eid
        eid += 1
        return f"e{eid}"

    def parse_ts(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            d = ev.get("data") or {}
            ts = parse_ts(ev.get("timestamp"))

            if t == "session.start":
                session_start = parse_ts(d.get("startTime")) or ts

            elif t == "user.message":
                txt = d.get("content") or ""
                if txt.strip():
                    entries.append({
                        "type": "user", "text": txt,
                        "agentMode": None, "timestamp": ts, "id": new_id(),
                    })

            elif t == "assistant.message":
                reasoning = d.get("reasoningText") or ""
                content = d.get("content") or ""
                if reasoning.strip():
                    entries.append({
                        "type": "reasoning", "text": reasoning,
                        "timestamp": ts, "id": new_id(),
                    })
                if content.strip():
                    entries.append({
                        "type": "copilot", "text": content,
                        "model": d.get("model"),
                        "timestamp": ts, "id": new_id(),
                    })

            elif t == "tool.execution_start":
                entries.append({
                    "type": "tool_call_requested",
                    "callId": d.get("toolCallId"),
                    "name": d.get("toolName"),
                    "arguments": d.get("arguments"),
                    "intentionSummary": d.get("intentionSummary"),
                    "timestamp": ts, "id": new_id(),
                })

            elif t == "tool.execution_complete":
                entries.append({
                    "type": "tool_call_completed",
                    "callId": d.get("toolCallId"),
                    "name": d.get("toolName"),
                    "arguments": d.get("arguments"),
                    "result": _normalise_tool_result(d),
                    "timestamp": ts, "id": new_id(),
                })

            elif t == "system.notification":
                kind = d.get("kind") or {}
                kind_t = kind.get("type") if isinstance(kind, dict) else None
                entries.append({
                    "type": "system_notification",
                    "text": d.get("content") or kind_t or "",
                    "detail": None, "kind": kind,
                    "timestamp": ts, "id": new_id(),
                })

            elif t == "session.info":
                # Bundle: `addTimelineEntry({type:"info", text: data.message})`
                # for persisted `session.info` events. infoType=model is the
                # one users usually see ("Model changed from X to Y"); the
                # cancellation infoType is emitted *ephemerally* and doesn't
                # land in events.jsonl, so it's not picked up here — `abort`
                # below replaces it.
                msg = d.get("message")
                if msg:
                    entries.append({
                        "type": "info", "text": msg,
                        "timestamp": ts, "id": new_id(),
                    })

            elif t == "abort":
                # Mirrors bundle's emitEphemeral(session.info, "Operation
                # cancelled by user") — that ephemeral never reaches disk, so
                # we synthesise the same text from the persisted `abort`.
                reason = d.get("reason", "user_initiated")
                if reason in ("user_initiated", "user initiated"):
                    text = "Operation cancelled by user"
                else:
                    text = f"Operation aborted ({reason})"
                entries.append({
                    "type": "info", "text": text,
                    "timestamp": ts, "id": new_id(),
                })

            # other types (hook.*, assistant.turn_*, system.message,
            # session.start, session.model_change) are intentionally
            # dropped: hook noise, turn boundaries, the 67KB system prompt,
            # and the per-turn model_change (we use the higher-quality
            # session.info(infoType=model) entry instead).

    return entries, session_start


def _normalise_tool_result(d):
    """Coerce a tool.execution_complete data dict into the bundle's
    result shape: {type, log?, markdown?}."""
    if not d.get("success", True) and d.get("error"):
        return {"type": "failure", "log": str(d.get("error"))}
    r = d.get("result")
    if isinstance(r, dict):
        log = r.get("content")
        if isinstance(log, list):  # list of {type:'text', text:...} chunks
            log = "\n".join(
                c.get("text", "") if isinstance(c, dict) else str(c)
                for c in log
            )
        return {
            "type": "success" if d.get("success", True) else "failure",
            "log": log if isinstance(log, str) else (
                json.dumps(r, ensure_ascii=False, indent=2) if r else None
            ),
            "markdown": bool(r.get("markdown")),
        }
    if isinstance(r, str):
        return {"type": "success" if d.get("success", True) else "failure",
                "log": r}
    return {"type": "success" if d.get("success", True) else "pending"}


def turns_to_entries(turns):
    """Fallback when events.jsonl is missing."""
    entries = []
    for i, (_ti, um, ar, ts) in enumerate(turns):
        timestamp = _parse_iso(ts)
        if um and um.strip():
            entries.append({"type": "user", "text": um,
                            "agentMode": None, "timestamp": timestamp,
                            "id": f"db-u{i}"})
        if ar and ar.strip():
            entries.append({"type": "copilot", "text": ar,
                            "model": None, "timestamp": timestamp,
                            "id": f"db-c{i}"})
    return entries


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ───────────────────────────────────────────── iFs: merge tool entries ───────
def merge_tool_entries(entries):
    """Mirrors bundle's `iFs`: pair tool_call_requested + tool_call_completed
    on `callId` into a single merged-tool entry; orphans pass through."""
    completed = {}
    for e in entries:
        if e["type"] == "tool_call_completed" and e.get("callId"):
            completed[e["callId"]] = e

    paired_ids = set()
    out = []
    for e in entries:
        if e["type"] == "tool_call_requested":
            s = completed.get(e.get("callId"))
            merged = {
                "callId": e.get("callId"),
                "name": e.get("name"),
                "arguments": e.get("arguments")
                             or (s.get("arguments") if s else None),
                "intentionSummary": e.get("intentionSummary")
                             or (s.get("intentionSummary") if s else None),
                "result": s.get("result") if s else None,
                "timestamp": e.get("timestamp"),
                "id": e.get("id"),
            }
            if s:
                paired_ids.add(s["id"])
            out.append({"kind": "merged-tool", "entry": merged})
        elif e["type"] == "tool_call_completed":
            if e["id"] in paired_ids:
                out.append({"kind": "skip"})
            else:
                out.append({"kind": "merged-tool", "entry": {
                    "callId": e.get("callId"), "name": e.get("name"),
                    "arguments": e.get("arguments"),
                    "intentionSummary": e.get("intentionSummary"),
                    "result": e.get("result"),
                    "timestamp": e.get("timestamp"), "id": e.get("id"),
                }})
        else:
            out.append({"kind": "passthrough", "entry": e})
    return out


# ──────────────────────────────────────────── tool argument summaries ────────
# Mirrors `nFs`+`Lj` from the bundle.
def _paths_summary(args):
    if not isinstance(args, dict):
        return None
    raw = args.get("paths") or args.get("path")
    if not raw:
        return None
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = [str(x) for x in raw if str(x) != "."]
    else:
        return None
    items = [x for x in items if x and x != "."]
    return ", ".join(items) if items else None


def tool_arg_summary(name, args):
    if not isinstance(args, dict):
        return None
    if name in ("grep", "rg"):
        parts = [f'"{args.get("pattern", "")}"']
        if args.get("glob"):
            parts.append(f'in {args["glob"]}')
        elif args.get("type"):
            parts.append(f'in {args["type"]} files')
        p = _paths_summary(args)
        if p:
            parts.append(f'({p})')
        return " ".join(parts)
    if name == "glob":
        parts = [f'"{args.get("pattern", "")}"']
        p = _paths_summary(args)
        if p:
            parts.append(f'in {p}')
        return " ".join(parts)
    if name in ("bash", "local_shell"):
        return f'$ {args.get("command", "")}'
    if name == "view":
        path = args.get("path", "")
        rng = args.get("view_range")
        if isinstance(rng, list) and len(rng) == 2:
            return f"{path} (lines {rng[0]}-{rng[1]})"
        return path
    if name in ("edit", "create"):
        return args.get("path", "")
    return None


def is_diff_output(t):
    if not t:
        return False
    return "diff --git" in t or (
        "@@" in t and ("+++" in t or "---" in t)
    )


# ─────────────────────────────────────────────────── HTML rendering ──────────
def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def md_to_html(text):
    """Mirrors bundle's `qbr`: wrap markdown→html in .markdown-body."""
    text = text or ""
    try:
        import markdown
        body = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
            output_format="html5",
        )
        return f'<div class="markdown-body">{body}</div>'
    except Exception:
        return f'<pre class="md-fallback">{esc(text)}</pre>'


def asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


def title_from(entries, fallback):
    """Mirrors bundle's `aFs`."""
    for e in entries:
        if e["type"] == "user" and (e.get("text") or "").strip():
            t = re.sub(r"\s+", " ", e["text"].strip())
            return t if len(t) <= 80 else t[:77] + "..."
    return fallback or "Copilot CLI Session"


def entry_time(ts, session_start):
    """Per-entry display: absolute local time. HH:MM:SS when on the same
    local-date as session_start; MM-DD HH:MM:SS otherwise (so multi-day
    sessions stay unambiguous).

    Diverges from the bundle's `Jbr` (which returns 'Xm Ys' relative to
    session start) by FrostHan's preference: per-entry timestamps should be
    absolute, not relative."""
    if not ts:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone()
    if session_start:
        ss = session_start
        if ss.tzinfo is None:
            ss = ss.replace(tzinfo=timezone.utc)
        if local.date() == ss.astimezone().date():
            return local.strftime("%H:%M:%S")
    return local.strftime("%m-%d %H:%M:%S")


def elapsed_str(start_dt):
    """Mirrors the bundle's elapsed string (header position 3): 'Ys' if
    <60s else 'Xm Ys'. Computed at generation time (not view time), since
    the dredge-up report is pre-baked HTML."""
    if not start_dt:
        return ""
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    s = max(0, int((datetime.now(timezone.utc) - start_dt).total_seconds()))
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


def share_format(dt):
    """Header start-time format. We use **24-hour** `YYYY-MM-DD HH:MM:SS`
    instead of the bundle's en-US `M/D/YYYY, H:MM:SS AM/PM` because the
    12-hour AM/PM rendering is easy to misread (`11:04:21 PM` ≠ "morning",
    it's 23:04:21). This is the one place we deliberately diverge from
    share's byte-level output."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ────────────── per-type entry renderers (mirror nJn + sFs) ──────────────────
def _entry_shell(*, etype, border, collapsed, idx, eid, icon, label,
                 time_str, body, extra_cls=""):
    cls = ["entry"]
    if collapsed:
        cls.append("collapsed")
    cls.append(f"border-{border}")
    if extra_cls:
        cls.append(extra_cls)
    return (
        f'<div class="{" ".join(cls)}" data-type="{etype}" '
        f'data-entry-id="{esc(eid)}" data-index="{idx}" id="entry-{idx}">\n'
        f'<div class="entry-header" role="button" tabindex="0">\n'
        f'<span class="entry-icon">{icon}</span>\n'
        f'<span class="entry-number">#{idx + 1}</span>\n'
        f'<span class="entry-label">{label}</span>\n'
        f'<a class="entry-time" href="#entry-{idx}">{esc(time_str)}</a>\n'
        f'<span class="collapse-indicator"></span>\n'
        f'</div>\n'
        f'<div class="entry-body">{body}</div>\n'
        f'</div>'
    )


def render_user(e, idx, time_str):
    agent = (f' <span class="agent-mode">{esc(e["agentMode"])}</span>'
             if e.get("agentMode") else "")
    return _entry_shell(
        etype="user", border="user", collapsed=False, idx=idx, eid=e["id"],
        icon="&#x1F464;", label=f"用户{agent}", time_str=time_str,
        body=f'<div class="user-text">{esc(e.get("text", ""))}</div>',
    )


def render_copilot(e, idx, time_str):
    return _entry_shell(
        etype="copilot", border="copilot", collapsed=False, idx=idx,
        eid=e["id"], icon="&#x1F4AC;", label="Copilot", time_str=time_str,
        body=md_to_html(e.get("text", "")),
    )


def render_reasoning(e, idx, time_str):
    return _entry_shell(
        etype="reasoning", border="reasoning", collapsed=True, idx=idx,
        eid=e["id"], icon="&#x1F4AD;", label="推理", time_str=time_str,
        body=f'<div class="reasoning-text">{esc(e.get("text", ""))}</div>',
    )


def render_info(e, idx, time_str):
    return _entry_shell(
        etype="info", border="info", collapsed=True, idx=idx, eid=e["id"],
        icon="&#x2139;", label="信息", time_str=time_str,
        body=esc(e.get("text", "")),
    )


def render_warning(e, idx, time_str):
    return _entry_shell(
        etype="warning", border="warning", collapsed=True, idx=idx,
        eid=e["id"], icon="&#x26A0;", label="警告", time_str=time_str,
        body=esc(e.get("text", "")),
    )


def render_error(e, idx, time_str):
    return _entry_shell(
        etype="error", border="error", collapsed=False, idx=idx, eid=e["id"],
        icon="&#x2718;", label="错误", time_str=time_str,
        extra_cls="entry-error-bg",
        body=f'<div class="error-text">{esc(e.get("text", ""))}</div>',
    )


def render_notification(e, idx, time_str):
    detail = (f'<div class="notification-detail"><div class="md-code-block">'
              f'<pre><code>{esc(e["detail"])}</code></pre></div></div>'
              if e.get("detail") else "")
    return _entry_shell(
        etype="notification", border="info", collapsed=True, idx=idx,
        eid=e["id"], icon="&#x2139;", label="通知", time_str=time_str,
        body=f'<p>{esc(e.get("text", ""))}</p>{detail}',
    )


def render_summary(e, idx, time_str):
    """Agent-authored summary pinned ABOVE the numbered timeline.

    Special: `data-index="summary"`/`id="entry-summary"` (not a number) and
    its `entry-number` shows `★`. This means the summary doesn't consume an
    entry index, so the real timeline still starts at #1 with the first
    actual event. `data-type="summary"` still works for the filter pill."""
    return (
        '<div class="entry border-info" data-type="summary" '
        'data-entry-id="summary" data-index="summary" id="entry-summary">\n'
        '<div class="entry-header" role="button" tabindex="0">\n'
        '<span class="entry-icon">&#x2605;</span>\n'
        '<span class="entry-number">&#x2605;</span>\n'
        '<span class="entry-label">本次总结</span>\n'
        f'<a class="entry-time" href="#entry-summary">{esc(time_str)}</a>\n'
        '<span class="collapse-indicator"></span>\n'
        '</div>\n'
        f'<div class="entry-body"><div class="markdown-body">{e["text"]}</div></div>\n'
        '</div>'
    )


def render_merged_tool(e, idx, time_str):
    """Mirrors `sFs`."""
    rt = (e.get("result") or {}).get("type") or "pending"
    icon = {"success": "&#x2714;", "failure": "&#x2718;",
            "rejected": "&#x26D4;", "denied": "&#x26D4;",
            "pending": "&#x23F3;"}.get(rt, "&#x23F3;")
    border = {"success": "tool-success", "failure": "tool-failure",
              "rejected": "tool-rejected", "denied": "tool-failure",
              "pending": "info"}.get(rt, "info")
    extra = " entry-error-bg" if rt in ("failure", "denied") else ""

    name = e.get("name") or "?"
    label = (f'{esc(name)} - {esc(e["intentionSummary"])}'
             if e.get("intentionSummary") else esc(name))

    # arguments block
    args = e.get("arguments")
    if args is None:
        args_html = ""
    else:
        summary = tool_arg_summary(name, args)
        if summary:
            args_html = (f'<div class="tool-args"><code class="md-codespan">'
                         f'{esc(summary)}</code></div>')
        else:
            pretty = json.dumps(args, ensure_ascii=False, indent=2)
            args_html = (f'<div class="tool-args"><div class="md-code-block">'
                         f'<pre data-lang="json"><code>{esc(pretty)}'
                         f'</code></pre></div></div>')

    # output block
    out_html = ""
    res = e.get("result")
    if res:
        if rt in ("success", "failure", "denied") and res.get("log"):
            log = res["log"]
            if res.get("markdown"):
                out_html = f'<div class="tool-output">{md_to_html(log)}</div>'
            elif is_diff_output(log):
                out_html = (f'<div class="tool-output">'
                            f'<div class="md-code-block">'
                            f'<pre data-lang="diff"><code>{esc(log)}'
                            f'</code></pre></div></div>')
            else:
                out_html = (f'<div class="tool-output">'
                            f'<div class="md-code-block">'
                            f'<pre><code>{esc(log)}</code></pre></div></div>')
        elif rt == "rejected":
            out_html = ('<div class="tool-output">'
                        '<em class="text-muted">被用户拒绝</em></div>')

    return (
        f'<div class="entry collapsed border-{border}{extra}" '
        f'data-type="tool" data-entry-id="{esc(e["id"])}" '
        f'data-index="{idx}" id="entry-{idx}">\n'
        f'<div class="entry-header" role="button" tabindex="0">\n'
        f'<span class="entry-icon">{icon}</span>\n'
        f'<span class="entry-number">#{idx + 1}</span>\n'
        f'<span class="entry-label">{label}</span>\n'
        f'<a class="entry-time" href="#entry-{idx}">{esc(time_str)}</a>\n'
        f'<span class="collapse-indicator"></span>\n'
        f'</div>\n'
        f'<div class="entry-body">{args_html}{out_html}</div>\n'
        f'</div>'
    )


def render_group(e, idx, time_str):
    """Mirrors bundle's `rJn`. Children rendering is best-effort: events.jsonl
    in current Copilot CLI versions does not synthesise group entries (tool
    groups arrive as plain tool_call_requested/completed pairs and get merged
    by iFs), so this is mostly a renderer-of-last-resort kept for parity."""
    title = e.get("title", "")
    completed = e.get("completed", False)
    suffix = "（已完成）" if completed else ""
    nested_html = []
    for ci, child in enumerate(e.get("timelineEntries") or []):
        ct = child.get("type")
        cts = entry_time(child.get("timestamp"), None)
        if ct in RENDERERS:
            # children get a composite id; reuse renderer
            tmp = RENDERERS[ct](child, ci, cts)
            nested_html.append(tmp)
    body = f'<div class="nested-entries">{"".join(nested_html)}</div>'
    return _entry_shell(
        etype="group", border="info", collapsed=True, idx=idx, eid=e["id"],
        icon="&#x1F4E6;", label=f"{esc(title)}{suffix}", time_str=time_str,
        body=body,
    )


def render_handoff(e, idx, time_str):
    repo = e.get("repository") or {}
    repo_str = (f'{repo.get("owner", "")}/{repo.get("name", "")}'
                + (f' ({repo["branch"]})' if repo.get("branch") else ""))
    summary = (f'<p>{esc(e.get("summary"))}</p>' if e.get("summary") else "")
    return _entry_shell(
        etype="handoff", border="info", collapsed=True, idx=idx, eid=e["id"],
        icon="&#x1F500;", label="会话交接", time_str=time_str,
        body=f'<p><strong>仓库：</strong> {esc(repo_str)}</p>{summary}',
    )


def render_compaction(e, idx, time_str):
    return _entry_shell(
        etype="compaction", border="info", collapsed=True, idx=idx,
        eid=e["id"], icon="&#x25CC;", label="对话已压缩", time_str=time_str,
        body=f'<p>{esc(e.get("summaryContent", ""))}</p>',
    )


def render_task_complete(e, idx, time_str):
    extra = "entry-error-bg" if e.get("isError") else ""
    return _entry_shell(
        etype="task_complete", border="info", collapsed=False, idx=idx,
        eid=e["id"], icon="&#x2713;", label="任务完成", time_str=time_str,
        extra_cls=extra, body=md_to_html(e.get("content", "")),
    )


RENDERERS = {
    "user": render_user,
    "copilot": render_copilot,
    "reasoning": render_reasoning,
    "info": render_info,
    "warning": render_warning,
    "error": render_error,
    "system_notification": render_notification,
    "summary": render_summary,
    # bundle parity (rarely seen in events.jsonl, kept for completeness):
    "group": render_group,
    "handoff": render_handoff,
    "compaction": render_compaction,
    "task_complete": render_task_complete,
}


def render_entry(item, idx, start):
    if item["kind"] == "skip":
        return None
    e = item["entry"]
    t = entry_time(e.get("timestamp"), start)
    if item["kind"] == "merged-tool":
        return render_merged_tool(e, idx, t)
    fn = RENDERERS.get(e["type"])
    return fn(e, idx, t) if fn else None


# ──────────────────────────────────────────────────── document shell ─────────
# Pill order mirrors bundle `y` (user/copilot/tool/reasoning/info/warning/
# error/group/notification/handoff/compaction/task_complete) plus our
# additional `summary` (agent-authored dredge-up verdict) pinned first.
PILL_ORDER = [
    ("summary", "总结"),
    ("user", "用户"),
    ("copilot", "Copilot"),
    ("tool", "工具"),
    ("reasoning", "推理"),
    ("info", "信息"),
    ("warning", "警告"),
    ("error", "错误"),
    ("group", "组"),
    ("notification", "通知"),
    ("handoff", "交接"),
    ("compaction", "压缩"),
    ("task_complete", "任务完成"),
]


def render_html(name, sid, cwd, repo, branch, entries, session_start,
                source_label, summary_text=None):
    title = title_from(entries, name)
    if not session_start and entries:
        session_start = next((e.get("timestamp") for e in entries
                              if e.get("timestamp")), None)

    merged = merge_tool_entries(entries)

    rendered = []
    counts = {}
    idx = 0
    for item in merged:
        html_block = render_entry(item, idx, session_start)
        if html_block is None:
            continue
        rendered.append(html_block)
        # tally by data-type for filter pills
        if item["kind"] == "merged-tool":
            counts["tool"] = counts.get("tool", 0) + 1
        else:
            t = item["entry"]["type"]
            if t == "system_notification":
                t = "notification"
            counts[t] = counts.get(t, 0) + 1
        idx += 1

    body_entries = ("\n".join(rendered) if rendered
                    else '<div class="empty-state">本会话没有可显示的条目。</div>')

    # Summary lives ABOVE the numbered timeline so the indexed entries still
    # start at #1 with the real first event (per FrostHan: "AI 总结不应该覆盖
    # 真实的 #1"). The bundle's JS treats it as just another `.entry` with
    # data-type="summary", so the `总结` filter pill toggles it normally.
    summary_block = ""
    if summary_text and summary_text.strip():
        # build a synthetic entry dict (same shape render_summary expects)
        ss_local = session_start.astimezone() if (
            session_start and session_start.tzinfo) else session_start
        ts_str = share_format(ss_local) if ss_local else ""
        summary_block = render_summary(
            {"id": "summary", "text": summary_text}, None, ts_str) + "\n"
        counts["summary"] = counts.get("summary", 0) + 1

    body = summary_block + body_entries

    pills = "".join(
        f'<button class="filter-pill active" data-filter-type="{t}">'
        f'{label}<span class="pill-count">{counts[t]}</span></button>'
        for t, label in PILL_ORDER if counts.get(t)
    )

    # Header mirrors the bundle: <code>sid</code> · start · elapsed · N entries.
    # No cwd/repo/branch/generated (the bundle has none); show a fallback
    # warning only when we couldn't load events.jsonl and dropped back to the
    # db.turns lossy view (per FrostHan: "数据源对你有用、给别人看是噪音").
    meta_bits = [f"<code>{esc(sid)}</code>"]
    if session_start:
        ss_local = session_start
        if ss_local.tzinfo is None:
            ss_local = ss_local.replace(tzinfo=timezone.utc)
        ss_local = ss_local.astimezone()
        meta_bits.append(esc(share_format(ss_local)))
        meta_bits.append(esc(elapsed_str(session_start)))
    meta_bits.append(f"{idx} 条")
    if source_label and source_label != "events.jsonl":
        meta_bits.append(
            f'<span style="color:#ffb454">⚠ 数据源回退到 {esc(source_label)}'
            f'</span>'
        )
    header_meta = " &middot; ".join(meta_bits)

    css = asset("share-export.css")
    js = re.sub(r"</script", r"<\\/script", asset("share-export.js"), flags=re.I)

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-color-mode="dark" data-light-theme="light" data-dark-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)} — Session 回顾</title>
<style>{css}</style>
</head>
<body>
<div class="sticky-header">
<div class="header-meta">{header_meta}</div>
<div class="header-controls">
<input type="text" id="search-input" class="search-box" placeholder="搜索（按 / 聚焦）" />
<div class="filter-pills">{pills}</div>
<button class="btn" id="compact-mode">紧凑</button>
<button class="btn" id="collapse-all">全部折叠</button>
<button class="btn" id="expand-all">全部展开</button>
<button class="btn active" id="sidebar-toggle">目录</button>
<button class="btn" id="theme-toggle">&#x2600;</button>
</div>
</div>
<div class="scroll-container">
<div id="sidebar" class="sidebar visible"></div>
<div class="main-container sidebar-visible">
{body}
</div>
<div class="jump-buttons">
<button class="jump-btn" id="jump-prev" title="上一条用户消息">&#x25B2;</button>
<button class="jump-btn" id="jump-next" title="下一条用户消息">&#x25BC;</button>
</div>
</div>
<script>{js}</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────── text format ────────
def render_text(name, sid, cwd, repo, branch, entries):
    lines = [f"# Session {sid}", f"name: {name}",
             f"cwd: {cwd} | repo: {repo} | branch: {branch}",
             f"entries: {len(entries)}", "=" * 100]
    for e in entries:
        ts = e.get("timestamp")
        ts_s = ts.isoformat() if ts else ""
        lines.append(f"\n----- {e['type']} [{ts_s}] -----")
        if e["type"] in ("user", "copilot", "reasoning", "info",
                         "warning", "error", "system_notification"):
            lines.append((e.get("text") or "").rstrip())
        elif e["type"] == "tool_call_requested":
            lines.append(f"call {e.get('name')} args="
                         f"{json.dumps(e.get('arguments'), ensure_ascii=False)}")
        elif e["type"] == "tool_call_completed":
            r = e.get("result") or {}
            lines.append(f"-> {r.get('type')} : {(r.get('log') or '')[:200]}")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────── main ─────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_id")
    ap.add_argument("--format", choices=["text", "html"], default="text")
    ap.add_argument("--out", help="write to file instead of stdout")
    ap.add_argument("--summary",
                    help="path to an agent-authored HTML fragment to pin "
                         "at the top of the report")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--events",
                    help="path to events.jsonl (default: "
                         "~/.copilot/session-state/<id>/events.jsonl)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"session store not found: {args.db}")

    # meta from sessions table
    meta = fetch_db_meta(args.db, args.session_id)
    if not meta:
        sys.exit(f"session {args.session_id} not found in {args.db}")
    name, cwd, repo, branch, created_at = meta

    # pick data source
    events_path = args.events or os.path.join(
        DEFAULT_STATE, args.session_id, "events.jsonl")
    if os.path.exists(events_path):
        entries, session_start = parse_events_jsonl(events_path)
        source_label = "events.jsonl"
    else:
        turns = fetch_db_turns(args.db, args.session_id)
        if not turns:
            sys.exit(
                f"session {args.session_id} has no events.jsonl and no turns "
                f"in the DB yet (live store lags by a turn or two)"
            )
        entries = turns_to_entries(turns)
        session_start = _parse_iso(created_at)
        source_label = "db.turns (fallback)"

    # Pass summary as a separate kwarg to render_html so it gets rendered
    # ABOVE the indexed timeline (with data-index="summary") rather than
    # consuming index #1. text-mode dump just appends it.
    summary_text = None
    if args.summary:
        if not os.path.exists(args.summary):
            sys.exit(f"summary file not found: {args.summary}")
        with open(args.summary, encoding="utf-8") as f:
            summary_text = f.read()

    if args.format == "html":
        doc = render_html(name, args.session_id, cwd, repo, branch,
                          entries, session_start, source_label,
                          summary_text=summary_text)
    else:
        doc = render_text(name, args.session_id, cwd, repo, branch, entries)
        if summary_text:
            doc = (doc + "\n\n===== AGENT SUMMARY =====\n"
                       + summary_text.rstrip())

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(doc)
        mix = {}
        for e in entries:
            mix[e["type"]] = mix.get(e["type"], 0) + 1
        print(f"wrote {len(entries)} entries -> {args.out}  "
              f"({source_label}; {mix})")
    else:
        print(doc)


if __name__ == "__main__":
    main()
