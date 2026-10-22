<script setup lang="ts">
// A static, step-revealed terminal. It never "types" on its own: each click
// reveals the next group, so the presenter controls pacing.
interface TermLine {
  /** text, may contain [[token|class]] spans for colouring */
  text: string
  /** click at which the line appears */
  at?: number
  kind?: 'cmd' | 'cont' | 'out' | 'comment' | 'json'
}

const props = withDefaults(defineProps<{
  title?: string
  lines: TermLine[]
  step?: number
  badge?: string
}>(), { title: 'zsh', step: 99 })

function render(text: string) {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\[\[(.+?)\|([\w-]+)\]\]/g, '<span class="$2">$1</span>')
}
const shown = (l: TermLine) => props.step >= (l.at ?? 0)
</script>

<template>
  <div class="term">
    <div class="bar">
      <span class="d r" /><span class="d y" /><span class="d g" />
      <span class="title mono">{{ title }}</span>
      <span v-if="badge" class="pill warn badge">{{ badge }}</span>
    </div>
    <div class="body">
      <div
        v-for="(l, i) in lines"
        :key="i"
        class="line"
        :class="[l.kind ?? 'out', { on: shown(l) }]"
      >
        <span v-if="l.kind === 'cmd'" class="prompt">$</span>
        <span v-else-if="l.kind === 'cont'" class="prompt"> </span>
        <span class="txt" v-html="render(l.text)" />
      </div>
      <span class="cursor" />
    </div>
  </div>
</template>

<style scoped>
.term {
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-strong);
  background: rgba(6, 6, 12, 0.92);
  box-shadow: 0 30px 80px -30px rgba(99, 102, 241, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.02) inset;
  overflow: hidden;
}
.bar { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--border); background: rgba(255, 255, 255, 0.02); }
.d { width: 11px; height: 11px; border-radius: 50%; }
.d.r { background: #ff5f57; } .d.y { background: #febc2e; } .d.g { background: #28c840; }
.title { margin-left: 10px; font-size: 12px; color: var(--faint); }
.badge { margin-left: auto; }
.body { padding: 16px 20px 18px; font-family: var(--font-mono); font-size: 14.5px; line-height: 1.62; }
.line { display: flex; gap: 10px; white-space: pre; opacity: 0; transform: translateX(-4px); transition: opacity 350ms var(--ease), transform 350ms var(--ease); }
.line.on { opacity: 1; transform: none; }
.prompt { color: #8b5cf6; width: 10px; flex: 0 0 auto; }
.line.cmd .txt, .line.cont .txt { color: #f5f5f7; }
.line.out .txt { color: #9ca3af; }
.line.comment .txt { color: #5b5f6e; font-style: italic; }
.line.json .txt { color: #c7d2fe; }
.txt :deep(.flag) { color: #a78bfa; }
.txt :deep(.str) { color: #86efac; }
.txt :deep(.key) { color: #93c5fd; }
.txt :deep(.num) { color: #fcd34d; }
.txt :deep(.ok) { color: #4ade80; }
.txt :deep(.bad) { color: #f87171; }
.cursor { display: inline-block; width: 8px; height: 16px; margin-left: 20px; background: #8b5cf6; vertical-align: middle; animation: blink 1.1s steps(1) infinite; }
</style>
