import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import * as Collapsible from '@radix-ui/react-collapsible'
import {
  Search, Sun, Moon, PanelLeftClose, PanelLeftOpen,
  ChevronRight, User, Bot, Star, FoldVertical, UnfoldVertical,
  Brain, Wrench, Info, Bell, Check, X as XIcon, Ban, Hourglass,
  ChevronUp, ChevronDown, Rows3,
  AlertTriangle, Package, Shuffle, CircleDashed, CheckCircle2,
} from 'lucide-react'
import { CodeBlock } from './components/CodeBlock'
import { cn } from './lib/cn'
import raw from './session.json'

/* ─────────────────────────────────────────────── data model ───────────── */
type ResultType = 'success' | 'failure' | 'rejected' | 'denied' | 'pending'
interface ToolEntry {
  callId?: string
  name?: string
  arguments?: unknown
  intentionSummary?: string | null
  result?: { type: ResultType; log?: string; markdown?: boolean } | null
  timestamp?: string | null
  id: string
}
interface BasicEntry {
  type:
    | 'user' | 'copilot' | 'reasoning' | 'info' | 'warning' | 'error'
    | 'system_notification' | 'summary'
    | 'group' | 'handoff' | 'compaction' | 'task_complete'
  text?: string
  agentMode?: string | null
  model?: string | null
  detail?: string | null
  // group / handoff / compaction / task_complete extra fields:
  title?: string
  completed?: boolean
  repository?: { owner: string; name: string; branch?: string | null }
  summary?: string
  summaryContent?: string
  content?: string
  isError?: boolean
  timestamp?: string | null
  id: string
}
type Item =
  | { kind: 'merged-tool'; entry: ToolEntry }
  | { kind: 'passthrough'; entry: BasicEntry }
type RawItem = Item | { kind: 'skip' }

interface Session {
  sessionId: string
  name: string
  cwd: string | null
  repo: string | null
  branch: string | null
  sessionStart: string | null
  exportedAt: string | null
  sourceLabel: string
  entries: RawItem[]
}

const session = raw as unknown as Session

// inject agent-authored summary at top, if provided via build-time replacement
declare const __SUMMARY_HTML__: string | undefined
const SUMMARY_HTML: string | undefined =
  typeof __SUMMARY_HTML__ === 'string' && __SUMMARY_HTML__ ? __SUMMARY_HTML__ : undefined

/* ────────────────────────────────────────── shared helpers ────────────── */
type PillType =
  | 'summary' | 'user' | 'copilot' | 'tool' | 'reasoning' | 'info'
  | 'warning' | 'error' | 'group' | 'notification' | 'handoff'
  | 'compaction' | 'task_complete'

// Order mirrors bundle `y` plus our prepended `summary` (agent-authored).
const PILL_DEF: Array<{ type: PillType; label: string; Icon: typeof User; color: string }> = [
  { type: 'summary',       label: '总结',     Icon: Star,    color: 'text-amber-400' },
  { type: 'user',          label: '用户',     Icon: User,    color: 'text-[var(--user)]' },
  { type: 'copilot',       label: 'Copilot',  Icon: Bot,     color: 'text-[var(--acc2)]' },
  { type: 'tool',          label: '工具',     Icon: Wrench,  color: 'text-violet-400' },
  { type: 'reasoning',     label: '推理',     Icon: Brain,   color: 'text-slate-400' },
  { type: 'info',          label: '信息',     Icon: Info,    color: 'text-sky-400' },
  { type: 'warning',       label: '警告',     Icon: AlertTriangle, color: 'text-amber-400' },
  { type: 'error',         label: '错误',     Icon: XIcon,   color: 'text-rose-400' },
  { type: 'group',         label: '组',       Icon: Package, color: 'text-sky-400' },
  { type: 'notification',  label: '通知',     Icon: Bell,    color: 'text-sky-400' },
  { type: 'handoff',       label: '交接',     Icon: Shuffle, color: 'text-sky-400' },
  { type: 'compaction',    label: '压缩',     Icon: CircleDashed, color: 'text-sky-400' },
  { type: 'task_complete', label: '任务完成', Icon: CheckCircle2, color: 'text-emerald-400' },
]
const PILL_BY_TYPE = Object.fromEntries(PILL_DEF.map((p) => [p.type, p])) as Record<PillType, typeof PILL_DEF[number]>

function itemPillType(it: Item): PillType | null {
  if (it.kind === 'merged-tool') return 'tool'
  const t = it.entry.type
  if (t === 'system_notification') return 'notification'
  return t as PillType
}

function firstLine(t?: string): string {
  const line = (t || '').split('\n').find((l) => l.trim())?.trim() || ''
  return line.length > 90 ? line.slice(0, 90) + '…' : line
}

/* ─────────────────────────────────────────── markdown wrapper ─────────── */
function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          pre: ({ children }) => <>{children}</>,
          code({ className, children, ...props }) {
            const m = /language-(\w+)/.exec(className || '')
            const code = String(children).replace(/\n$/, '')
            if (m) return <CodeBlock code={code} lang={m[1]} />
            return <code className={className} {...props}>{children}</code>
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

/* The agent-authored summary fragment arrives as HTML (from `--summary
   <file.html>`), not markdown — vanilla injects it as raw HTML too. It is
   trusted local content the agent wrote itself (never external or user
   input), so we render it raw. Passing it through <Markdown> would escape
   the tags and show <h3>/<ul>/<code> literally (react-markdown drops raw
   HTML by default). Reuses the `.md` body styles. */
function TrustedHtml({ html }: { html: string }) {
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}

/* ─────────────────────────────── tool arg summary (mirrors nFs/Lj) ───── */
function pathsSummary(args: Record<string, unknown>): string | null {
  const raw = (args.paths ?? args.path) as unknown
  if (!raw) return null
  const items = Array.isArray(raw) ? raw.map(String) : [String(raw)]
  const kept = items.filter((x) => x && x !== '.')
  return kept.length ? kept.join(', ') : null
}
function toolArgSummary(name: string, args: unknown): string | null {
  if (!args || typeof args !== 'object') return null
  const a = args as Record<string, unknown>
  if (name === 'grep' || name === 'rg') {
    const parts = [`"${a.pattern ?? ''}"`]
    if (a.glob) parts.push(`in ${a.glob}`)
    else if (a.type) parts.push(`in ${a.type} files`)
    const p = pathsSummary(a); if (p) parts.push(`(${p})`)
    return parts.join(' ')
  }
  if (name === 'glob') {
    const parts = [`"${a.pattern ?? ''}"`]
    const p = pathsSummary(a); if (p) parts.push(`in ${p}`)
    return parts.join(' ')
  }
  if (name === 'bash' || name === 'local_shell') return `$ ${a.command ?? ''}`
  if (name === 'view') {
    const r = a.view_range as number[] | undefined
    if (r && r.length === 2) return `${a.path} (lines ${r[0]}-${r[1]})`
    return String(a.path ?? '')
  }
  if (name === 'edit' || name === 'create') return String(a.path ?? '')
  return null
}
function isDiff(s: string): boolean {
  return s.includes('diff --git') || (s.includes('@@') && (s.includes('+++') || s.includes('---')))
}

/* ─────────────────────────────────────────── per-type renderers ───────── */
/* per-entry display: absolute local time. HH:MM:SS when on the same
   local-date as sessionStart; MM-DD HH:MM:SS otherwise (so multi-day
   sessions stay unambiguous). Diverges from bundle's `Jbr` by FrostHan's
   preference. */
function entryTime(ts?: string | null, sessionStart?: string | null): string {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  if (sessionStart) {
    const ss = new Date(sessionStart)
    if (d.getFullYear() === ss.getFullYear() &&
        d.getMonth() === ss.getMonth() &&
        d.getDate() === ss.getDate()) {
      return time
    }
  }
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${time}`
}

/* bundle-style elapsed for header: 'Ys' if <60 else 'Xm Ys'. Baked at
   the moment session.json was exported (not at view time). */
function elapsedStr(start: string | null, exportedAt: string | null): string {
  if (!start) return ''
  const end = exportedAt ? new Date(exportedAt).getTime() : Date.now()
  const s = Math.max(0, Math.floor((end - new Date(start).getTime()) / 1000))
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

/* 24-hour `YYYY-MM-DD HH:MM:SS` for header session-start. We deliberately
   diverge from share's en-US `toLocaleString()` (12h AM/PM) since the
   12-hour form misreads easily — "11:04:21 PM" is not "morning" but 23:04:21. */
function formatStart(ts: string): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function BasicCard({
  entry, idx, open, onToggle, sessionStart,
}: { entry: BasicEntry; idx: number; open: boolean; onToggle: (v: boolean) => void; sessionStart: string | null }) {
  const pillType = entry.type === 'system_notification' ? 'notification' : (entry.type as PillType)
  const M = PILL_BY_TYPE[pillType] ?? PILL_BY_TYPE.info
  const time = entryTime(entry.timestamp, sessionStart)
  const borderCls = {
    user: 'border-l-[var(--user)]',
    copilot: 'border-l-[var(--acc2)]',
    reasoning: 'border-l-slate-500',
    summary: 'border-l-amber-400',
    info: 'border-l-sky-500',
    warning: 'border-l-amber-500',
    error: 'border-l-rose-500',
    system_notification: 'border-l-sky-500',
    group: 'border-l-sky-500',
    handoff: 'border-l-sky-500',
    compaction: 'border-l-sky-500',
    task_complete: 'border-l-emerald-500',
  }[entry.type] || 'border-l-[var(--line)]'

  let body: React.ReactNode
  switch (entry.type) {
    case 'user':
    case 'reasoning':
    case 'info':
    case 'warning':
    case 'error':
    case 'system_notification':
      body = (
        <pre className="m-0 whitespace-pre-wrap break-words rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3 font-mono text-[12.8px] leading-relaxed">
          {entry.text || ''}
        </pre>
      )
      break
    case 'copilot':
    case 'summary':
    case 'task_complete':
      body = <Markdown text={entry.content || entry.text || ''} />
      break
    case 'group':
      body = (
        <p className="text-sm text-[var(--mut)]">
          组：{entry.title || '(无标题)'}{entry.completed ? ' （已完成）' : ''}
        </p>
      )
      break
    case 'handoff': {
      const repo = entry.repository
      const repoStr = repo
        ? `${repo.owner}/${repo.name}${repo.branch ? ` (${repo.branch})` : ''}`
        : ''
      body = (
        <>
          <p><strong>仓库：</strong> {repoStr}</p>
          {entry.summary && <p>{entry.summary}</p>}
        </>
      )
      break
    }
    case 'compaction':
      body = <p>{entry.summaryContent || ''}</p>
      break
  }

  return (
    <Collapsible.Root open={open} onOpenChange={onToggle} id={`entry-${idx}`}
      className={cn('scroll-mt-28 rounded-xl border border-[var(--line)] border-l-2 bg-[var(--panel)] overflow-hidden', borderCls)}>
      <Collapsible.Trigger className="recap-trigger flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-[var(--panel2)] transition-colors">
        <ChevronRight size={15} className={cn('shrink-0 text-[var(--mut)] transition-transform', open && 'rotate-90')} />
        <M.Icon size={15} className={cn('shrink-0', M.color)} />
        <span className="shrink-0 rounded-md bg-[var(--panel2)] px-2 py-0.5 text-xs font-bold text-[var(--mut)]">#{idx + 1}</span>
        <span className={cn('shrink-0 text-sm font-semibold', M.color)}>
          {entry.type === 'summary' ? '本次总结'
            : entry.type === 'handoff' ? '会话交接'
            : entry.type === 'compaction' ? '对话已压缩'
            : entry.type === 'task_complete' ? '任务完成'
            : M.label}
        </span>
        <span className="flex-1 truncate text-sm text-[var(--mut)]">
          {!open && firstLine(entry.text || entry.content || entry.summaryContent || entry.title || '')}
        </span>
        <span className="shrink-0 text-xs text-[var(--mut)]">{time}</span>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <div className="recap-body border-t border-[var(--line)] px-4 py-3">{body}</div>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

/* Agent-authored summary card. Sits ABOVE the numbered timeline (no
   numeric data-index), so the first actual event keeps entry #1. Filter
   pill `总结` still toggles it via the `active.summary` state in App. */
function SummaryCard({
  entry, open, onToggle, sessionStart,
}: {
  entry: BasicEntry; open: boolean; onToggle: (v: boolean) => void
  sessionStart: string | null
}) {
  const time = entryTime(entry.timestamp, sessionStart)
  return (
    <Collapsible.Root open={open} onOpenChange={onToggle} id="entry-summary"
      data-type="summary"
      className="scroll-mt-28 rounded-xl border border-[var(--line)] border-l-2 border-l-amber-400 bg-[var(--panel)] overflow-hidden">
      <Collapsible.Trigger className="recap-trigger flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-[var(--panel2)] transition-colors">
        <ChevronRight size={15} className={cn('shrink-0 text-[var(--mut)] transition-transform', open && 'rotate-90')} />
        <Star size={15} className="shrink-0 text-amber-400" />
        <span className="shrink-0 rounded-md bg-[var(--panel2)] px-2 py-0.5 text-xs font-bold text-amber-400">★</span>
        <span className="shrink-0 text-sm font-semibold text-amber-400">本次总结</span>
        <span className="flex-1 truncate text-sm text-[var(--mut)]">
          {!open && firstLine(entry.text)}
        </span>
        <span className="shrink-0 text-xs text-[var(--mut)]">{time}</span>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <div className="recap-body border-t border-[var(--line)] px-4 py-3">
          <TrustedHtml html={entry.text || ''} />
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}


function ToolCard({
  entry, idx, open, onToggle, sessionStart,
}: { entry: ToolEntry; idx: number; open: boolean; onToggle: (v: boolean) => void; sessionStart: string | null }) {
  const rt: ResultType = (entry.result?.type ?? 'pending')
  const time = entryTime(entry.timestamp, sessionStart)
  const RIcon = { success: Check, failure: XIcon, rejected: Ban, denied: Ban, pending: Hourglass }[rt]
  const accent = {
    success: 'text-emerald-400 border-l-emerald-500',
    failure: 'text-rose-400 border-l-rose-500',
    rejected: 'text-amber-400 border-l-amber-500',
    denied: 'text-rose-400 border-l-rose-500',
    pending: 'text-sky-400 border-l-sky-500',
  }[rt]
  const [accentText, accentBorder] = accent.split(' ')

  const name = entry.name || '?'
  const label = entry.intentionSummary ? `${name} — ${entry.intentionSummary}` : name

  const summary = toolArgSummary(name, entry.arguments)
  const argsBlock = entry.arguments == null ? null : summary ? (
    <code className="block w-fit max-w-full overflow-x-auto rounded border border-[var(--line)] bg-[var(--code-bg)] px-2 py-1 font-mono text-[12.5px]">
      {summary}
    </code>
  ) : (
    <CodeBlock code={JSON.stringify(entry.arguments, null, 2)} lang="json" />
  )

  const log = entry.result?.log || ''
  const outBlock = !entry.result ? null
    : rt === 'rejected' ? <em className="text-[var(--mut)]">被用户拒绝</em>
    : !log ? null
    : entry.result.markdown ? <Markdown text={log} />
    : <CodeBlock code={log} lang={isDiff(log) ? 'diff' : 'text'} />

  return (
    <Collapsible.Root open={open} onOpenChange={onToggle} id={`entry-${idx}`}
      className={cn('scroll-mt-28 rounded-xl border border-[var(--line)] border-l-2 bg-[var(--panel)] overflow-hidden', accentBorder)}>
      <Collapsible.Trigger className="recap-trigger flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-[var(--panel2)] transition-colors">
        <ChevronRight size={15} className={cn('shrink-0 text-[var(--mut)] transition-transform', open && 'rotate-90')} />
        <RIcon size={15} className={cn('shrink-0', accentText)} />
        <span className="shrink-0 rounded-md bg-[var(--panel2)] px-2 py-0.5 text-xs font-bold text-[var(--mut)]">#{idx + 1}</span>
        <span className={cn('shrink-0 text-sm font-mono', accentText)}>{label}</span>
        <span className="flex-1 truncate text-sm text-[var(--mut)]">{!open && summary}</span>
        <span className="shrink-0 text-xs text-[var(--mut)]">{time}</span>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <div className="recap-body space-y-3 border-t border-[var(--line)] px-4 py-3">
          {argsBlock}
          {outBlock}
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

/* ───────────────────────────────────────────────────── App ───────────── */
export default function App() {
  // Real timeline items (summary lives separately above this list so it
  // doesn't push entry #1 down, per FrostHan's review).
  const items = useMemo<Item[]>(() => {
    return (session.entries || [])
      .filter((i): i is Item => i.kind !== 'skip')
  }, [])

  // Synthetic summary card (data-index="summary"); rendered above `items`.
  const summary = SUMMARY_HTML
    ? {
        kind: 'passthrough' as const,
        entry: {
          type: 'summary' as const, text: SUMMARY_HTML,
          timestamp: session.sessionStart, id: 'summary-fragment',
        },
      }
    : null

  const [dark, setDark] = useState(true)
  const [compact, setCompact] = useState(
    () => typeof localStorage !== 'undefined' && localStorage.getItem('recap-compact') === '1',
  )
  const [query, setQuery] = useState('')
  const [active, setActive] = useState<Record<PillType, boolean>>(() => {
    const a: Record<PillType, boolean> = {} as Record<PillType, boolean>
    for (const p of PILL_DEF) a[p.type] = true
    return a
  })
  const [openMap, setOpenMap] = useState<Record<number, boolean>>(() => {
    const m: Record<number, boolean> = {}
    items.forEach((it, i) => {
      const t = itemPillType(it)
      m[i] = t === 'user' || t === 'error'
    })
    return m
  })
  const [summaryOpen, setSummaryOpen] = useState(true)
  const [showSidebar, setShowSidebar] = useState(true)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])
  useEffect(() => {
    localStorage.setItem('recap-compact', compact ? '1' : '0')
  }, [compact])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault(); searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    if (summary) c.summary = 1
    for (const it of items) {
      const t = itemPillType(it); if (t) c[t] = (c[t] || 0) + 1
    }
    return c
  }, [items, summary])

  function itemText(it: Item): string {
    if (it.kind === 'merged-tool') {
      const e = it.entry
      return [e.name, e.intentionSummary, JSON.stringify(e.arguments || {}),
              e.result?.log || ''].filter(Boolean).join(' ')
    }
    return it.entry.text || ''
  }

  const visible = useMemo(() => {
    const ql = query.trim().toLowerCase()
    return items
      .map((it, idx) => ({ it, idx }))
      .filter(({ it }) => {
        const t = itemPillType(it); if (t && !active[t]) return false
        if (ql && !itemText(it).toLowerCase().includes(ql)) return false
        return true
      })
  }, [items, query, active])

  const setAll = (v: boolean) =>
    setOpenMap(Object.fromEntries(items.map((_, i) => [i, v])))
  const jump = (dir: 1 | -1) => {
    const userIdx = items.map((it, i) => ({ it, i }))
      .filter(({ it }) => it.kind === 'passthrough' && it.entry.type === 'user')
      .map(({ i }) => i)
    const cur = Math.round(window.scrollY + 200)
    let target: number | undefined
    if (dir === 1) target = userIdx.find((i) => {
      const el = document.getElementById(`entry-${i}`); return el && el.offsetTop > cur
    })
    else {
      const before = userIdx.filter((i) => {
        const el = document.getElementById(`entry-${i}`); return el && el.offsetTop < cur - 50
      })
      target = before[before.length - 1]
    }
    if (target != null) document.getElementById(`entry-${target}`)?.scrollIntoView({ behavior: 'smooth' })
  }

  const present = PILL_DEF.filter((p) => counts[p.type])

  return (
    <div className={cn('min-h-full', compact && 'compact')}>
      <header className="sticky top-0 z-20 border-b border-[var(--line)] bg-[var(--bg)]/85 backdrop-blur">
        <div className="mx-auto max-w-6xl px-5 py-3">
          <div className="flex items-baseline gap-2">
            <h1 className="text-lg font-bold">🌀 {session.name}</h1>
            <span className="text-xs text-[var(--mut)]">Session 回顾 (React)</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--mut)]">
            <Pill><code className="text-[var(--txt)]">{session.sessionId}</code></Pill>
            {session.sessionStart && (
              <Pill>{formatStart(session.sessionStart)}</Pill>
            )}
            {session.sessionStart && (
              <Pill>{elapsedStr(session.sessionStart, session.exportedAt)}</Pill>
            )}
            <Pill>{items.length} 条</Pill>
            {session.sourceLabel !== 'events.jsonl' && (
              <Pill><span className="text-amber-400">⚠ 数据源回退到 {session.sourceLabel}</span></Pill>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--mut)]" />
              <input
                ref={searchRef} value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索（按 / 聚焦）"
                className="h-8 w-60 rounded-lg border border-[var(--line)] bg-[var(--panel)] pl-8 pr-2 text-sm outline-none focus:border-[var(--acc)]" />
            </div>
            <div className="flex flex-wrap gap-1">
              {present.map((p) => (
                <button key={p.type}
                  onClick={() => setActive((a) => ({ ...a, [p.type]: !a[p.type] }))}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                    active[p.type] ? 'border-[var(--acc)] text-[var(--txt)]'
                                   : 'border-[var(--line)] text-[var(--mut)] opacity-50',
                  )}>
                  <p.Icon size={12} className={p.color} />
                  {p.label}<span className="rounded bg-[var(--panel2)] px-1 text-[10px]">{counts[p.type]}</span>
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-1">
              <IconBtn title="上一条用户消息" onClick={() => jump(-1)}><ChevronUp size={15} /></IconBtn>
              <IconBtn title="下一条用户消息" onClick={() => jump(1)}><ChevronDown size={15} /></IconBtn>
              <IconBtn title="全部折叠" onClick={() => setAll(false)}><FoldVertical size={15} /></IconBtn>
              <IconBtn title="全部展开" onClick={() => setAll(true)}><UnfoldVertical size={15} /></IconBtn>
              <IconBtn title="目录" onClick={() => setShowSidebar((s) => !s)}>
                {showSidebar ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
              </IconBtn>
              <IconBtn title="紧凑模式" onClick={() => setCompact((c) => !c)} active={compact}>
                <Rows3 size={15} />
              </IconBtn>
              <IconBtn title="主题" onClick={() => setDark((d) => !d)}>
                {dark ? <Sun size={15} /> : <Moon size={15} />}
              </IconBtn>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-6xl gap-5 px-5 py-5">
        {showSidebar && (
          <nav className="sticky top-28 hidden h-[calc(100vh-8rem)] w-56 shrink-0 overflow-y-auto md:block">
            <ul className="space-y-0.5 text-sm">
              {visible.map(({ it, idx }) => {
                const t = itemPillType(it) || 'info'
                const M = PILL_BY_TYPE[t]
                const text = it.kind === 'merged-tool'
                  ? `${it.entry.name}${it.entry.intentionSummary ? ' — ' + it.entry.intentionSummary : ''}`
                  : firstLine(it.entry.text)
                return (
                  <li key={idx}>
                    <a href={`#entry-${idx}`}
                       className="flex items-center gap-2 rounded-md px-2 py-1 text-[var(--mut)] hover:bg-[var(--panel2)] hover:text-[var(--txt)]">
                      <M.Icon size={12} className={cn('shrink-0', M.color)} />
                      <span className="truncate">{text}</span>
                    </a>
                  </li>
                )
              })}
            </ul>
          </nav>
        )}

        <main className="min-w-0 flex-1 space-y-2">
          {summary && active.summary && (
            <SummaryCard
              entry={summary.entry}
              open={summaryOpen}
              onToggle={setSummaryOpen}
              sessionStart={session.sessionStart}
            />
          )}
          {visible.length === 0
            ? (
              <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-8 text-center text-[var(--mut)]">
                没有匹配的条目。
              </div>
            )
            : visible.map(({ it, idx }) => (
              it.kind === 'merged-tool'
                ? <ToolCard key={idx} entry={it.entry} idx={idx}
                    open={!!openMap[idx]} sessionStart={session.sessionStart}
                    onToggle={(v) => setOpenMap((m) => ({ ...m, [idx]: v }))} />
                : <BasicCard key={idx} entry={it.entry} idx={idx}
                    open={!!openMap[idx]} sessionStart={session.sessionStart}
                    onToggle={(v) => setOpenMap((m) => ({ ...m, [idx]: v }))} />
            ))}
          <footer className="pt-4 text-center text-xs text-[var(--mut)]">
            recap React 原型 · Vite + React 19 + Tailwind v4 + Radix + Shiki · 单文件自包含
          </footer>
        </main>
      </div>
    </div>
  )
}

function Pill({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-[var(--line)] bg-[var(--panel)] px-2.5 py-0.5">{children}</span>
}
function IconBtn({ children, title, onClick, active }: { children: React.ReactNode; title: string; onClick: () => void; active?: boolean }) {
  return (
    <button title={title} onClick={onClick} aria-pressed={active}
      className={cn(
        'grid h-8 w-8 place-items-center rounded-lg border bg-[var(--panel)] hover:text-[var(--txt)] hover:bg-[var(--panel2)]',
        active ? 'border-[var(--acc)] text-[var(--txt)]' : 'border-[var(--line)] text-[var(--mut)]',
      )}>
      {children}
    </button>
  )
}
