import { useEffect, useState } from 'react'
import { createHighlighterCore, type HighlighterCore } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'

// Tuned single-file highlighter: JS regex engine (no oniguruma WASM) + a small
// curated language set, dynamically imported so Vite only bundles these. Dual
// theme (light+dark) so the page theme toggle re-colours code with no re-run.
const LANGS: Record<string, () => Promise<unknown>> = {
  bash: () => import('@shikijs/langs/bash'),
  shell: () => import('@shikijs/langs/bash'),
  sh: () => import('@shikijs/langs/bash'),
  python: () => import('@shikijs/langs/python'),
  py: () => import('@shikijs/langs/python'),
  javascript: () => import('@shikijs/langs/javascript'),
  js: () => import('@shikijs/langs/javascript'),
  typescript: () => import('@shikijs/langs/typescript'),
  ts: () => import('@shikijs/langs/typescript'),
  tsx: () => import('@shikijs/langs/tsx'),
  json: () => import('@shikijs/langs/json'),
  diff: () => import('@shikijs/langs/diff'),
  css: () => import('@shikijs/langs/css'),
  html: () => import('@shikijs/langs/html'),
}

const ALIAS: Record<string, string> = {
  shell: 'bash', sh: 'bash', py: 'python', js: 'javascript', ts: 'typescript',
}

let hlPromise: Promise<HighlighterCore> | null = null
function getHighlighter() {
  if (!hlPromise) {
    hlPromise = (async () => {
      const [light, dark] = await Promise.all([
        import('@shikijs/themes/github-light'),
        import('@shikijs/themes/github-dark'),
      ])
      return createHighlighterCore({
        themes: [light.default, dark.default],
        langs: [],
        engine: createJavaScriptRegexEngine(),
      })
    })()
  }
  return hlPromise
}

export function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const key = lang.toLowerCase()
  const supported = key in LANGS
  const language = supported ? (ALIAS[key] ?? key) : 'text'
  const [html, setHtml] = useState<string>('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      const hl = await getHighlighter()
      if (supported && !hl.getLoadedLanguages().includes(language)) {
        const mod = (await LANGS[key]()) as { default: unknown }
        await hl.loadLanguage(mod.default as never)
      }
      if (!alive) return
      setHtml(
        hl.codeToHtml(code, {
          lang: supported ? language : 'text',
          themes: { light: 'github-light', dark: 'github-dark' },
          defaultColor: false,
        }),
      )
    })()
    return () => {
      alive = false
    }
  }, [code, key, language, supported])

  if (!html) {
    return (
      <pre className="shiki">
        <code>{code}</code>
      </pre>
    )
  }
  return <div dangerouslySetInnerHTML={{ __html: html }} />
}
