#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown>=3.5"]
# ///
"""Dump one Copilot CLI session from the local session store as a report.

Why this exists: the agent's own in-context view of a long session is *lossy* —
early turns get compressed or dropped from the context window, and that is
exactly where "聊过但忘记处理" (discussed-but-dropped) items hide. The local
SQLite store keeps every turn verbatim, so re-reading it is the only reliable
way to recover what the user actually asked for across the whole session.

The HTML output reuses Copilot CLI's own `/share html` interactive export look
& feel — its dark GitHub (Primer) theme, sticky header, type-filter pills,
search, collapsible entries, sidebar map and jump-nav — by inlining the CSS/JS
extracted verbatim from the installed @github/copilot bundle (see
assets/share-export.{css,js}). Visible labels are localised to Chinese; the
data-type attributes the JS filters on stay English. On top of the conversation
archive the agent can inject a summary block via --summary.

Usage:
    uv run dump_session.py <session-id> [--format text|html] [--out PATH]
                                        [--summary PATH] [--db PATH]
    # plain `python3` also works (markdown then falls back to <pre>).

Notes:
- Opens the DB read-only (mode=ro); never writes to it.
- The live store lags by the most recent turn or two, so the very last exchange
  may be missing — combine this dump with your own context.
- Default DB path is ~/.copilot/session-store.db (override with --db).
- --summary PATH injects an agent-authored summary (HTML fragment, e.g. the
  recap "做过的事 / 承诺未做" verdict) as a pinned block at the top. The fragment
  is trusted and inserted verbatim; conversation content from the DB is always
  HTML-escaped (user) or markdown-rendered (assistant).
"""
import argparse
import html
import os
import sqlite3
import sys
from datetime import datetime

DEFAULT_DB = os.path.expanduser("~/.copilot/session-store.db")
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


def fetch(db, sid):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT summary, cwd, repository, branch FROM sessions WHERE id=?", (sid,))
    meta = cur.fetchone()
    cur.execute(
        "SELECT turn_index, user_message, assistant_response, timestamp "
        "FROM turns WHERE session_id=? ORDER BY turn_index",
        (sid,),
    )
    turns = cur.fetchall()
    con.close()
    return meta, turns


def as_text(meta, turns, sid, summary_html=None):
    out = []
    name = meta[0] if meta else "(unknown)"
    out.append(f"# Session {sid}")
    out.append(f"name: {name}")
    if meta:
        out.append(f"cwd: {meta[1]}  repo: {meta[2]}  branch: {meta[3]}")
    out.append(f"turns: {len(turns)}")
    out.append("=" * 100)
    for ti, um, ar, ts in turns:
        out.append(f"\n----- turn {ti}  [{ts}] -----")
        out.append("USER:")
        out.append((um or "").rstrip())
        out.append("\nASSISTANT:")
        out.append((ar or "").rstrip())
    return "\n".join(out)


# ---------------------------------------------------------------- HTML helpers
def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def md_to_html(text):
    """Render assistant markdown like the bundle's marked.parse, wrapped in
    .markdown-body. Falls back to an escaped <pre> if markdown is unavailable."""
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


def _asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


def _title(turns, name):
    for _, um, _ar, _ts in turns:
        if um and um.strip():
            s = " ".join(um.split())
            return s if len(s) <= 80 else s[:77] + "..."
    return name or "Copilot CLI Session"


def _clock(ts):
    if not ts:
        return ""
    t = ts.replace("T", " ")[:19]
    return t[11:] or t  # HH:MM:SS when available


# visible (Chinese) labels — the JS filters on data-type (English), not these
TYPE_LABEL = {
    "summary": "本次总结", "user": "用户", "copilot": "Copilot",
}
TYPE_ICON = {
    "summary": "&#x2605;", "user": "&#x1F464;", "copilot": "&#x1F4AC;",
}


def _entry(idx, etype, label, icon, time_str, body_html, collapsed=False):
    cls = f"entry border-{'info' if etype == 'summary' else etype}"
    if collapsed:
        cls += " collapsed"
    return (
        f'<div class="{cls}" data-type="{etype}" data-index="{idx}" id="entry-{idx}">\n'
        f'<div class="entry-header" role="button" tabindex="0">\n'
        f'<span class="entry-icon">{icon}</span>\n'
        f'<span class="entry-number">#{idx + 1}</span>\n'
        f'<span class="entry-label">{label}</span>\n'
        f'<a class="entry-time" href="#entry-{idx}">{esc(time_str)}</a>\n'
        f'<span class="collapse-indicator"></span>\n'
        f'</div>\n'
        f'<div class="entry-body">{body_html}</div>\n'
        f'</div>'
    )


def as_html(meta, turns, sid, summary_html=None):
    name = meta[0] if meta and meta[0] else "(unknown)"
    cwd = meta[1] if meta and meta[1] else ""
    repo = meta[2] if meta and meta[2] else ""
    branch = meta[3] if meta and meta[3] else ""
    title = _title(turns, name)
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    entries = []
    counts = {}
    idx = 0

    if summary_html and summary_html.strip():
        entries.append(_entry(
            idx, "summary", TYPE_LABEL["summary"], TYPE_ICON["summary"],
            gen, f'<div class="markdown-body">{summary_html}</div>'))
        counts["summary"] = counts.get("summary", 0) + 1
        idx += 1

    for ti, um, ar, ts in turns:
        entries.append(_entry(
            idx, "user", TYPE_LABEL["user"], TYPE_ICON["user"],
            _clock(ts), f'<div class="user-text">{esc(um)}</div>'))
        counts["user"] = counts.get("user", 0) + 1
        idx += 1
        entries.append(_entry(
            idx, "copilot", TYPE_LABEL["copilot"], TYPE_ICON["copilot"],
            _clock(ts), md_to_html(ar)))
        counts["copilot"] = counts.get("copilot", 0) + 1
        idx += 1

    body_entries = ("\n".join(entries) if entries
                    else '<div class="empty-state">本会话没有对话记录。</div>')

    pill_order = ["summary", "user", "copilot"]
    pills = "".join(
        f'<button class="filter-pill active" data-filter-type="{t}">'
        f'{TYPE_LABEL[t]}<span class="pill-count">{counts[t]}</span></button>'
        for t in pill_order if counts.get(t)
    )

    meta_bits = [f"<code>{esc(sid)}</code>", esc(gen)]
    if cwd:
        meta_bits.append(f"<code>{esc(cwd)}</code>")
    if repo:
        meta_bits.append(esc(repo + (f"@{branch}" if branch else "")))
    meta_bits.append(f"{len(turns)} 轮 · {idx} 条")
    header_meta = " &middot; ".join(meta_bits)

    css = _asset("share-export.css")
    js = _asset("share-export.js")
    import re as _re
    js = _re.sub(r"</script", r"<\\/script", js, flags=_re.I)

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
{body_entries}
</div>
<div class="jump-buttons">
<button class="jump-btn" id="jump-prev" title="上一条用户消息">&#x25B2;</button>
<button class="jump-btn" id="jump-next" title="下一条用户消息">&#x25BC;</button>
</div>
</div>
<script>{js}</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_id")
    ap.add_argument("--format", choices=["text", "html"], default="text")
    ap.add_argument("--out", help="write to file instead of stdout")
    ap.add_argument("--summary", help="path to an agent-authored summary "
                    "(HTML fragment) to pin at the top of the HTML report")
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"session store not found: {args.db}")

    summary_html = None
    if args.summary:
        if not os.path.exists(args.summary):
            sys.exit(f"summary file not found: {args.summary}")
        with open(args.summary, encoding="utf-8") as f:
            summary_html = f.read()

    meta, turns = fetch(args.db, args.session_id)
    if not turns:
        if meta is None:
            sys.exit(
                f"session {args.session_id} not found in {args.db} "
                f"(wrong id? check the session-state folder name)"
            )
        sys.exit(
            f"session {args.session_id} exists but has no turns yet "
            f"(live store lags by a turn or two — newest exchanges may not be flushed)"
        )
    render = as_html if args.format == "html" else as_text
    doc = render(meta, turns, args.session_id, summary_html)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"wrote {len(turns)} turns -> {args.out}")
    else:
        print(doc)


if __name__ == "__main__":
    main()
