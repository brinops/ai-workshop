<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ step?: number }>(), { step: 99 })

// step 0: states on the board · 1: happy path · 2: review / retry / cancel paths · 3: Kanban mapping
const columns = [
  { name: 'NEW', x: 20, tone: 'neutral' },
  { name: 'TODO', x: 320, tone: 'warn' },
  { name: 'IN PROGRESS', x: 620, tone: 'violet' },
  { name: 'DONE', x: 920, tone: 'ok' },
]
const W = 200
const H = 44
const states: Record<string, { x: number; y: number; tone: string }> = {
  NEW: { x: 155, y: 110, tone: 'neutral' },
  WAITING_CI: { x: 155, y: 200, tone: 'neutral' },
  ANALYZING: { x: 155, y: 290, tone: 'violet' },
  TODO: { x: 455, y: 290, tone: 'neutral' },
  NEEDS_REVIEW: { x: 455, y: 400, tone: 'warn' },
  IN_PROGRESS: { x: 755, y: 290, tone: 'violet' },
  VALIDATING: { x: 755, y: 200, tone: 'neutral' },
  DONE: { x: 1050, y: 200, tone: 'ok' },
  FAILED: { x: 1050, y: 400, tone: 'fail' },
}
const happy = [
  { d: 'M155 132 L155 176', label: '' },
  { d: 'M155 222 L155 266', label: 'check failed', lx: 205, ly: 249 },
  { d: 'M255 290 L353 290', label: 'remediable', lx: 304, ly: 280 },
  { d: 'M555 290 L653 290', label: 'auto / Start', lx: 604, ly: 280 },
  { d: 'M755 268 L755 224', label: 'pushed', lx: 795, ly: 251 },
  { d: 'M855 200 L948 200', label: 'checks ✓', lx: 902, ly: 190 },
]
const side = [
  { d: 'M255 192 Q 600 120 948 190', label: 'checks pass, nothing to fix', lx: 600, ly: 146, tone: 'ok' },
  { d: 'M155 312 Q 155 400 353 400', label: 'low confidence · unknown', lx: 340, ly: 356, tone: 'warn' },
  { d: 'M755 312 Q 755 400 557 400', label: 'validation / scope fail · attempts exhausted', lx: 760, ly: 420, tone: 'warn' },
  { d: 'M655 205 Q 450 222 248 270', label: 'checks fail · retry (≤ 2)', lx: 455, ly: 210, tone: 'violet' },
  { d: 'M353 410 C -10 440, -10 200, 53 202', label: 'Retry (human)', lx: 88, ly: 384, tone: 'warn' },
]
const s = computed(() => props.step)
</script>

<template>
  <div class="sm">
    <svg viewBox="0 0 1200 470" aria-label="Task state machine">
      <defs>
        <marker v-for="t in ['violet', 'ok', 'warn']" :id="`sm-${t}`" :key="t" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" :class="`fill-${t}`" />
        </marker>
      </defs>

      <!-- Kanban columns -->
      <g v-for="c in columns" :key="c.name" class="col" :class="[c.tone, { lit: s >= 3 }]">
        <rect :x="c.x" y="10" width="260" height="450" rx="16" />
        <text :x="c.x + 20" y="44" class="col-name">{{ c.name }}</text>
        <line :x1="c.x + 20" :x2="c.x + 240" y1="60" y2="60" />
      </g>

      <!-- review / retry paths -->
      <g class="paths side" :class="{ on: s >= 2 }">
        <g v-for="e in side" :key="e.d">
          <path :d="e.d" :class="`stroke-${e.tone}`" :marker-end="`url(#sm-${e.tone})`" />
          <text :x="e.lx" :y="e.ly" text-anchor="middle" class="elabel">{{ e.label }}</text>
        </g>
      </g>

      <!-- happy path -->
      <g class="paths happy" :class="{ on: s >= 1 }">
        <g v-for="(e, i) in happy" :key="e.d" :style="{ transitionDelay: `${i * 120}ms` }" class="seg">
          <path :d="e.d" marker-end="url(#sm-violet)" />
          <text v-if="e.label" :x="e.lx" :y="e.ly" text-anchor="middle" class="elabel">{{ e.label }}</text>
        </g>
      </g>

      <!-- states -->
      <g
        v-for="(st, name) in states"
        :key="name"
        class="state"
        :class="[st.tone, { dim: s >= 1 && s < 2 && (name === 'NEEDS_REVIEW' || name === 'FAILED') }]"
      >
        <rect :x="st.x - W / 2" :y="st.y - H / 2" :width="W" :height="H" rx="10" />
        <text :x="st.x" :y="st.y + 5" text-anchor="middle">{{ name }}</text>
      </g>

      <text x="1050" y="446" text-anchor="middle" class="note" :class="{ on: s >= 2 }">Cancel · from any non-terminal state</text>
    </svg>

    <div class="flags" :class="{ on: s >= 3 }">
      <span class="mono faint">cross-cutting flags, not states →</span>
      <span class="pill">paused</span>
      <span class="pill">cancel_requested</span>
      <span class="pill violet">pending_action: analyze | remediate | push</span>
    </div>
  </div>
</template>

<style scoped>
.sm { margin-top: 6px; }
svg { width: 100%; height: auto; display: block; }
.col rect { fill: rgba(20, 20, 31, 0.55); stroke: rgba(255, 255, 255, 0.06); transition: all 500ms; }
.col line { stroke: rgba(255, 255, 255, 0.06); }
.col-name { font-family: var(--font-mono); font-size: 14px; letter-spacing: 0.14em; fill: #5b5f6e; transition: fill 500ms; }
.col.lit rect { stroke: rgba(255, 255, 255, 0.14); }
.col.lit.neutral .col-name { fill: #e5e7eb; }
.col.lit.warn .col-name { fill: #fcd34d; }
.col.lit.violet .col-name { fill: #c4b5fd; }
.col.lit.ok .col-name { fill: #86efac; }
.col.lit.violet rect { fill: rgba(139, 92, 246, 0.06); }

.state rect { fill: #1b1b2a; stroke: rgba(255, 255, 255, 0.16); stroke-width: 1; transition: opacity 400ms; }
.state text { font-family: var(--font-mono); font-size: 14px; fill: #f5f5f7; letter-spacing: 0.04em; }
.state.violet rect { stroke: rgba(139, 92, 246, 0.7); fill: rgba(139, 92, 246, 0.14); }
.state.ok rect { stroke: rgba(34, 197, 94, 0.7); fill: rgba(34, 197, 94, 0.12); }
.state.warn rect { stroke: rgba(245, 158, 11, 0.7); fill: rgba(245, 158, 11, 0.1); }
.state.fail rect { stroke: rgba(239, 68, 68, 0.7); fill: rgba(239, 68, 68, 0.1); }
.state.dim { opacity: 0.35; }

.paths path { fill: none; stroke-width: 1.6; }
.happy path { stroke: #8b5cf6; }
.happy .seg { opacity: 0; transition: opacity 400ms var(--ease); }
.happy.on .seg { opacity: 1; }
.side { opacity: 0; transition: opacity 600ms var(--ease); }
.side.on { opacity: 1; }
.side path { stroke-dasharray: 5 6; }
.stroke-violet { stroke: #a78bfa; } .stroke-ok { stroke: #22c55e; } .stroke-warn { stroke: #f59e0b; }
.fill-violet { fill: #a78bfa; } .fill-ok { fill: #22c55e; } .fill-warn { fill: #f59e0b; }
.elabel { font-family: var(--font-mono); font-size: 11.5px; fill: #9ca3af; paint-order: stroke; stroke: #09090f; stroke-width: 4px; }
.note { font-family: var(--font-mono); font-size: 11px; fill: #fca5a5; opacity: 0; transition: opacity 500ms; }
.note.on { opacity: 1; }

.flags { display: flex; gap: 10px; align-items: center; justify-content: center; margin-top: 10px; font-size: 12px; opacity: 0; transition: opacity 500ms; }
.flags.on { opacity: 1; }
</style>
