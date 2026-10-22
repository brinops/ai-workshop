<script setup lang="ts">
import { computed, ref, watch } from 'vue'

// Scenarios mirror demo/scenarios/*.yaml; findings are the real validator output
// from `demo/scripts/scenario.py verify all`.
const props = withDefaults(defineProps<{ step?: number; live?: 'A' | 'B' | 'C' }>(), { step: 99, live: 'C' })

const scenarios = {
  A: {
    title: 'Raise payments-api memory limit',
    category: 'SYNTAX_ERROR',
    failAt: 0,
    finding: 'Invalid YAML: mapping values are not allowed here',
    lines: [
      { t: ' ', n: 22, text: 'resources:' },
      { t: ' ', n: 23, text: '  requests:' },
      { t: '…', text: '' },
      { t: ' ', n: 26, text: '  limits:' },
      { t: ' ', n: 27, text: '    cpu: 500m' },
      { t: '-', text: '    memory: 256Mi' },
      { t: '+', n: 28, text: '     memory: 384Mi', mark: true },
    ],
  },
  B: {
    title: 'Scale payments-api to three replicas',
    category: 'SCHEMA_VIOLATION',
    failAt: 3,
    finding: '/spec/replicas: got string, want null or integer',
    lines: [
      { t: ' ', n: 1, text: '# Payments API — the application process listens on `app.port`.' },
      { t: '…', text: '' },
      { t: '-', text: 'replicaCount: 2' },
      { t: '+', n: 4, text: 'replicaCount: three', mark: true },
      { t: ' ', n: 5, text: '' },
      { t: ' ', n: 6, text: 'image:' },
    ],
  },
  C: {
    title: 'Expose payments-api metrics port on the Service',
    category: 'LOGICAL_CONFIGURATION_ERROR',
    failAt: 4,
    finding: "Service port 'http' targetPort 9090 does not match any container port of Deployment (container ports: [8080])",
    lines: [
      { t: ' ', n: 11, text: 'app:' },
      { t: ' ', n: 12, text: '  # Port the application binds to inside the container.' },
      { t: ' ', n: 13, text: '  port: 8080' },
      { t: '…', text: '' },
      { t: ' ', n: 16, text: 'service:' },
      { t: ' ', n: 17, text: '  type: ClusterIP' },
      { t: ' ', n: 18, text: '  port: 80' },
      { t: ' ', n: 19, text: '  # Must route to the container port the application listens on.' },
      { t: '-', text: '  targetPort: 8080' },
      { t: '+', n: 20, text: '  targetPort: 9090', mark: true },
    ],
  },
} as const
type Key = keyof typeof scenarios
const order: Key[] = ['A', 'B', 'C']

const picked = ref<Key | null>(null)
watch(() => props.step, () => { picked.value = null })
const key = computed<Key>(() => picked.value ?? order[Math.min(Math.max(props.step, 0), 2)])
const sc = computed(() => scenarios[key.value])
</script>

<template>
  <div class="ds">
    <div class="left">
      <div class="tabs">
        <button v-for="k in order" :key="k" class="tab" :class="{ on: k === key }" @click="picked = k">
          <span class="mono">{{ k }}</span>
          <span class="cat mono">{{ scenarios[k].category }}</span>
          <span v-if="k === live" class="pill violet live">live demo</span>
        </button>
      </div>
      <Transition name="fade-up" mode="out-in">
        <div :key="key" class="diffwrap">
          <div class="pr mono"><div class="i-lucide-git-pull-request" /> “{{ sc.title }}”</div>
          <CodeDiff file="demo/charts/payments-api/values.yaml" :lines="sc.lines as any" badge="1 line changed" />
        </div>
      </Transition>
      <slot />
    </div>
    <div class="right">
      <div class="eyebrow">where it gets caught</div>
      <ValidationGate :fail-at="sc.failAt" :category="sc.category" :finding="sc.finding" />
    </div>
  </div>
</template>

<style scoped>
.ds { display: grid; grid-template-columns: 1.15fr 1fr; gap: 28px; margin-top: 18px; }
.left, .right { min-width: 0; }
.tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.tab { flex: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; position: relative; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border); background: rgba(20, 20, 31, 0.6); color: var(--muted); cursor: pointer; transition: all 300ms; font-family: var(--font-sans); text-align: left; }
.tab .mono:first-child { font-size: 15px; color: var(--text); font-weight: 700; }
.tab .cat { font-size: 10px; letter-spacing: 0.05em; }
.tab.on { border-color: rgba(239, 68, 68, 0.5); background: rgba(239, 68, 68, 0.07); color: #fca5a5; }
.live { position: absolute; top: 7px; right: 8px; font-size: 10px; padding: 1px 7px; }
.pr { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.right .eyebrow { margin-bottom: 10px; }
</style>
