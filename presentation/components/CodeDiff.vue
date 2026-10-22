<script setup lang="ts">
interface DiffLine {
  /** ' ' context, '+' added, '-' removed, '…' elision */
  t: ' ' | '+' | '-' | '…'
  text: string
  /** line number in the new file (context / added) */
  n?: number
  /** emphasise this line (the intended failure) */
  mark?: boolean
}

withDefaults(defineProps<{ file: string; lines: DiffLine[]; badge?: string; tone?: 'fail' | 'ok' }>(), { tone: 'fail' })

// YAML-ish colouring: key, value, comment
function paint(text: string) {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  const c = esc.match(/^(\s*)(#.*)$/)
  if (c) return `${c[1]}<span class="cm">${c[2]}</span>`
  const kv = esc.match(/^(\s*)([\w.-]+)(:)(\s*)(.*)$/)
  if (kv) return `${kv[1]}<span class="ky">${kv[2]}</span>${kv[3]}${kv[4]}<span class="vl">${kv[5]}</span>`
  return esc
}
</script>

<template>
  <div class="cd">
    <div class="hd">
      <div class="i-lucide-file-code-2" />
      <span class="mono">{{ file }}</span>
      <span v-if="badge" class="pill" :class="tone">{{ badge }}</span>
    </div>
    <div class="bd">
      <div v-for="(l, i) in lines" :key="i" class="ln" :class="[{ add: l.t === '+', del: l.t === '-', gap: l.t === '…', mark: l.mark }]">
        <span class="no">{{ l.t === '…' ? '' : (l.n ?? '') }}</span>
        <span class="sg">{{ l.t === '…' ? '⋯' : l.t }}</span>
        <span class="tx" v-html="l.t === '…' ? '' : paint(l.text)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.cd { border-radius: var(--radius); border: 1px solid var(--border-strong); background: rgba(6, 6, 12, 0.92); overflow: hidden; }
.hd { display: flex; align-items: center; gap: 10px; padding: 9px 14px; border-bottom: 1px solid var(--border); font-size: 12.5px; color: var(--muted); }
.hd .pill { margin-left: auto; }
.bd { padding: 8px 0; font-family: var(--font-mono); font-size: 13.5px; line-height: 1.6; }
.ln { display: grid; grid-template-columns: 40px 22px 1fr; white-space: pre; padding-right: 14px; }
.no { text-align: right; padding-right: 10px; color: #3f4250; user-select: none; }
.sg { color: #3f4250; }
.ln.add { background: rgba(34, 197, 94, 0.09); }
.ln.add .sg { color: #4ade80; }
.ln.del { background: rgba(239, 68, 68, 0.09); }
.ln.del .sg { color: #f87171; }
.ln.del .tx { opacity: 0.7; }
.ln.mark { background: rgba(239, 68, 68, 0.16); box-shadow: inset 3px 0 0 #ef4444; }
.ln.mark.add .sg { color: #f87171; }
.ln.gap { color: #3f4250; }
.tx :deep(.cm) { color: #5b5f6e; font-style: italic; }
.tx :deep(.ky) { color: #93c5fd; }
.tx :deep(.vl) { color: #f5f5f7; }
.ln.mark .tx :deep(.vl) { color: #fca5a5; font-weight: 700; }
</style>
