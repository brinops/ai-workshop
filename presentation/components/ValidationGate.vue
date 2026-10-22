<script setup lang="ts">
import { computed } from 'vue'

interface Gate { key: string; name: string; tool: string; question: string; layer: string }
const props = defineProps<{
  /** index of the gate that fails (0-based); gates after it are skipped */
  failAt: number
  category: string
  finding: string
}>()

const gates: Gate[] = [
  { key: 'yaml', name: 'YAML syntax', tool: 'yaml-parse', question: 'Is it YAML at all?', layer: 'syntax' },
  { key: 'lint', name: 'Chart structure', tool: 'helm lint --strict', question: 'Is it a well-formed chart?', layer: 'chart' },
  { key: 'tpl', name: 'Rendering', tool: 'helm template', question: 'Do the templates render?', layer: 'chart' },
  { key: 'schema', name: 'Kubernetes schema', tool: 'kubeconform -strict', question: 'Do the objects match the API schema?', layer: 'schema' },
  { key: 'logic', name: 'Logical consistency', tool: 'consistency checks', question: 'Do ports, selectors and probes agree?', layer: 'logic' },
  { key: 'ci', name: 'GitHub Actions', tool: 'required check helm-validate', question: 'Does the team gate agree, on this SHA?', layer: 'ci' },
]

// CI runs the same validator, so it fails with the same finding.
const status = (i: number) => {
  if (i === gates.length - 1) return 'fail'
  if (i < props.failAt) return 'pass'
  if (i === props.failAt) return 'fail'
  return 'skip'
}
const failGate = computed(() => gates[props.failAt])
</script>

<template>
  <div class="vg">
    <div v-for="(g, i) in gates" :key="g.key" class="gate" :class="[status(i), { ci: g.key === 'ci' }]">
      <div class="st">
        <div v-if="status(i) === 'pass'" class="i-lucide-check" />
        <div v-else-if="status(i) === 'fail'" class="i-lucide-x" />
        <div v-else class="i-lucide-minus" />
      </div>
      <div class="body">
        <div class="name">{{ g.name }} <span class="tool mono">{{ g.tool }}</span></div>
        <div class="q">{{ g.question }}</div>
      </div>
    </div>
    <div class="finding mono">
      <span class="cat">RCP-FINDING · {{ category }}</span>
      <span class="msg">{{ failGate.tool }}: {{ finding }}</span>
    </div>
  </div>
</template>

<style scoped>
.vg { display: grid; gap: 6px; }
.gate { display: flex; align-items: center; gap: 12px; padding: 6px 12px; border-radius: 10px; border: 1px solid var(--border); background: rgba(20, 20, 31, 0.6); transition: all 400ms var(--ease); }
.gate.ci { margin-top: 6px; border-style: dashed; }
.st { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; font-size: 15px; flex: 0 0 auto; transition: all 400ms; }
.pass .st { background: var(--ok-soft); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); }
.fail .st { background: var(--fail-soft); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.5); }
.skip .st { background: rgba(255, 255, 255, 0.03); color: #3f4250; border: 1px solid var(--border); }
.gate.fail:not(.ci) { border-color: rgba(239, 68, 68, 0.55); box-shadow: var(--glow-fail); background: rgba(239, 68, 68, 0.06); }
.gate.skip { opacity: 0.4; }
.name { font-weight: 600; font-size: 14.5px; line-height: 1.2; }
.tool { font-weight: 400; font-size: 11px; color: var(--faint); margin-left: 6px; }
.q { font-size: 12.5px; color: var(--muted); }
.finding { margin-top: 6px; padding: 9px 12px; border-radius: 10px; background: rgba(239, 68, 68, 0.07); border: 1px solid rgba(239, 68, 68, 0.3); font-size: 11.5px; line-height: 1.5; display: grid; gap: 2px; }
.cat { color: #f87171; letter-spacing: 0.06em; }
.msg { color: #fecaca; }
</style>
