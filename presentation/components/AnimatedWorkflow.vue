<script setup lang="ts">
import { computed } from 'vue'

interface Step {
  label: string
  sub: string
  icon: string
  tone?: 'neutral' | 'fail' | 'human' | 'ok'
}

const props = withDefaults(defineProps<{
  steps: Step[]
  /** current click index: node i is visible when step >= i */
  step?: number
  /** indices (inclusive) wrapped by the "human effort" bracket */
  humanFrom?: number
  humanTo?: number
  /** click at which the bracket + loop appear */
  revealAt?: number
}>(), { step: 99, humanFrom: 3, humanTo: 5, revealAt: 7 })

const visible = (i: number) => props.step >= i
const revealed = computed(() => props.step >= props.revealAt)
const bracketStyle = computed(() => {
  const n = props.steps.length
  const left = (props.humanFrom / n) * 100
  const width = ((props.humanTo - props.humanFrom + 1) / n) * 100
  return { left: `${left}%`, width: `${width}%` }
})
</script>

<template>
  <div class="aw" :class="{ revealed }">
    <div class="row">
      <template v-for="(s, i) in steps" :key="s.label">
        <div
          class="node"
          :class="[s.tone ?? 'neutral', { on: visible(i), current: step === i }]"
        >
          <div class="icon"><div :class="s.icon" /></div>
          <div class="label">{{ s.label }}</div>
          <div class="sub">{{ s.sub }}</div>
        </div>
        <div v-if="i < steps.length - 1" class="edge" :class="{ on: visible(i + 1) }">
          <span />
        </div>
      </template>
    </div>

    <div class="bracket" :style="bracketStyle">
      <div class="line" />
      <div class="tag">
        <div class="i-lucide-user-round" />
        human in the loop · context switch · reading raw logs
      </div>
    </div>

    <svg class="loop" viewBox="0 0 1000 80" preserveAspectRatio="none" aria-hidden="true">
      <path d="M 942 76 C 942 4, 500 4, 500 76" />
    </svg>
    <div class="loop-label mono">wrong guess? repeat ↺</div>
  </div>
</template>

<style scoped>
.aw { position: relative; padding-top: 96px; padding-bottom: 90px; }
.row { display: flex; align-items: stretch; }
.node {
  flex: 0 0 auto;
  width: 132px;
  padding: 16px 12px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  text-align: center;
  opacity: 0;
  transform: translateY(12px) scale(0.97);
  transition: opacity 500ms var(--ease), transform 500ms var(--ease), box-shadow 500ms, border-color 500ms;
}
.node.on { opacity: 1; transform: none; }
.node.current { box-shadow: var(--glow-violet); border-color: rgba(139, 92, 246, 0.6); }
.icon {
  width: 40px; height: 40px; margin: 0 auto 10px;
  display: grid; place-items: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  font-size: 20px; color: var(--muted);
}
.label { font-weight: 600; font-size: 16px; line-height: 1.2; }
.sub { font-family: var(--font-mono); font-size: 11px; color: var(--faint); margin-top: 6px; line-height: 1.35; }
.node.fail .icon { color: var(--fail); background: var(--fail-soft); border-color: rgba(239, 68, 68, 0.35); }
.node.fail.current { box-shadow: var(--glow-fail); border-color: rgba(239, 68, 68, 0.6); }
.node.human .icon { color: var(--warn); background: var(--warn-soft); border-color: rgba(245, 158, 11, 0.35); }
.node.ok .icon { color: var(--ok); background: var(--ok-soft); border-color: rgba(34, 197, 94, 0.35); }

.edge { flex: 1; display: flex; align-items: center; min-width: 14px; }
.edge span {
  display: block; height: 1px; width: 100%;
  background: linear-gradient(90deg, rgba(139, 92, 246, 0.8), rgba(99, 102, 241, 0.4));
  transform: scaleX(0); transform-origin: left;
  transition: transform 500ms var(--ease);
}
.edge.on span { transform: scaleX(1); }

.bracket {
  position: absolute;
  top: calc(100% - 80px);
  opacity: 0;
  transform: translateY(-6px);
  transition: opacity 500ms var(--ease), transform 500ms var(--ease);
}
.revealed .bracket { opacity: 1; transform: none; }
.bracket .line {
  height: 14px;
  margin: 0 8px;
  border: 1px solid rgba(245, 158, 11, 0.6);
  border-top: none;
  border-radius: 0 0 10px 10px;
}
.bracket .tag {
  margin-top: 12px;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  font-family: var(--font-mono); font-size: 12px; color: #fcd34d;
  white-space: nowrap;
}

.loop {
  position: absolute; left: 0; right: 0; top: 14px;
  width: 100%; height: 80px; overflow: visible;
  opacity: 0; transition: opacity 600ms var(--ease) 200ms;
}
.loop path { fill: none; stroke: rgba(239, 68, 68, 0.55); stroke-width: 1.2; stroke-dasharray: 4 6; vector-effect: non-scaling-stroke; animation: dash-flow 1.2s linear infinite; }
.loop-label {
  position: absolute; left: 0; right: 0; text-align: center; padding-left: 44%; top: 0;
  font-size: 12px; color: #fca5a5; opacity: 0; transition: opacity 600ms var(--ease) 300ms;
}
.revealed .loop, .revealed .loop-label { opacity: 1; }
</style>
