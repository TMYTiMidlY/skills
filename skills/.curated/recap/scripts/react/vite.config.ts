import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { readFileSync } from 'node:fs'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'RECAP_')
  let summary = ''
  if (env.RECAP_SUMMARY_PATH) {
    try { summary = readFileSync(env.RECAP_SUMMARY_PATH, 'utf-8') }
    catch (e) { console.warn('summary file unreadable:', e) }
  }
  return {
    plugins: [react(), tailwindcss(), viteSingleFile()],
    define: { __SUMMARY_HTML__: JSON.stringify(summary) },
  }
})
