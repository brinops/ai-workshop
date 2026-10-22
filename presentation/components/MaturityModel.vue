<script setup lang="ts">
withDefaults(defineProps<{ step?: number }>(), { step: 99 })

const levels = [
  {
    n: 1, name: 'Detection', icon: 'i-lucide-radar', risk: 'no AI risk',
    build: ['PostToolUse hook or GitHub webhook', 'one table of tasks', 'Slack message on red CI'],
    gain: 'Every broken PR is visible within seconds.',
  },
  {
    n: 2, name: 'Reasoning', icon: 'i-lucide-brain-circuit', risk: 'read-only',
    build: ['claude -p + an analysis skill', '--json-schema diagnosis', 'post it as a PR comment'],
    gain: 'Humans start from a root cause, not a raw log.',
  },
  {
    n: 3, name: 'Remediation', icon: 'i-lucide-wrench', risk: 'gated writes',
    build: ['subagent with an edit allowlist', 'same validator as CI', 'backend-owned push, no merge'],
    gain: 'Routine fixes land as a reviewable commit.',
  },
]
</script>

<template>
  <div class="mm">
    <div v-for="(l, i) in levels" :key="l.n" class="lvl" :class="{ on: step >= i + 1 }" :style="{ '--lift': `${i * 56}px` }">
      <div class="head">
        <span class="n mono">L{{ l.n }}</span>
        <div :class="l.icon" class="ico" />
      </div>
      <h3>{{ l.name }}</h3>
      <span class="pill" :class="i === 0 ? 'ok' : i === 1 ? '' : 'violet'">{{ l.risk }}</span>
      <ul>
        <li v-for="b in l.build" :key="b" class="mono">{{ b }}</li>
      </ul>
      <p class="gain">{{ l.gain }}</p>
    </div>
    <div class="axis mono" aria-hidden="true">
      <span>value</span>
      <span>trust you must earn →</span>
    </div>
  </div>
</template>

<style scoped>
.mm { position: relative; display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; align-items: end; margin-top: 14px; padding-bottom: 28px; }
.lvl {
  margin-bottom: var(--lift);
  padding: 18px 20px 20px; border-radius: var(--radius-lg);
  border: 1px solid var(--border); background: rgba(20, 20, 31, 0.7);
  opacity: 0.18; transform: translateY(14px);
  transition: opacity 600ms var(--ease), transform 600ms var(--ease), border-color 600ms, box-shadow 600ms;
}
.lvl.on { opacity: 1; transform: none; }
.lvl:nth-child(1).on { border-color: rgba(34, 197, 94, 0.35); }
.lvl:nth-child(2).on { border-color: rgba(99, 102, 241, 0.45); }
.lvl:nth-child(3).on { border-color: rgba(139, 92, 246, 0.55); box-shadow: 0 30px 80px -40px rgba(139, 92, 246, 0.7); }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.n { font-size: 13px; color: var(--faint); letter-spacing: 0.1em; }
.ico { font-size: 24px; color: #a78bfa; }
h3 { font-size: 26px !important; margin: 0 0 8px !important; }
ul { list-style: none; padding: 0; margin: 14px 0; display: grid; gap: 6px; }
li { font-size: 12.5px; color: #c7d2fe; padding: 6px 10px; border-radius: 8px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border); }
.gain { font-size: 15px; color: var(--muted); line-height: 1.4; }
.axis { position: absolute; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-between; font-size: 11px; color: var(--faint); letter-spacing: 0.1em; text-transform: uppercase; border-top: 1px solid var(--border); padding-top: 6px; }
</style>
