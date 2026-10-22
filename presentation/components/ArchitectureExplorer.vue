<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ step?: number }>(), { step: 99 })

type Kind = 'det' | 'ai' | 'ext'
interface Node { id: string; x: number; y: number; title: string; sub: string; kind: Kind; zone: number; path: string; does: string }

// Coordinates are node centres in a 1136×300 design space (snake layout).
const nodes: Node[] = [
  { id: 'hook', x: 100, y: 60, title: 'Claude Code Hook', sub: 'PostToolUse · Bash', kind: 'det', zone: 1, path: '.claude/hooks/register_pr.py', does: 'Detects a successful gh pr create, confirms the PR with gh, registers it idempotently, spools if the backend is down. Always exits 0.' },
  { id: 'api', x: 322, y: 60, title: 'FastAPI', sub: 'REST · SSE · webhook', kind: 'det', zone: 1, path: 'backend/app/api/', does: 'Registration endpoint (de-duplicates, re-verifies against GitHub), task actions, settings, HMAC-verified GitHub webhook, SSE stream.' },
  { id: 'db', x: 544, y: 60, title: 'SQLite', sub: 'WAL · UNIQUE(repo, pr)', kind: 'det', zone: 1, path: 'tasks · events · agent_runs', does: 'The only coordination point. A task is a PR, so the row lease doubles as the PR-level lock.' },
  { id: 'sched', x: 766, y: 60, title: 'Scheduler', sub: 'async worker loop', kind: 'det', zone: 2, path: 'backend/app/orchestration/worker.py', does: 'Claims a stage with one conditional UPDATE, heartbeats while an agent runs, recovers expired leases, polls check runs.' },
  { id: 'gha', x: 988, y: 60, title: 'GitHub Actions', sub: 'helm-validate ✗', kind: 'ext', zone: 2, path: '.github/workflows/helm-validate.yaml', does: 'Required check. Runs the same validator as the backend and prints machine-readable RCP-FINDING lines.' },
  { id: 'skill', x: 1030, y: 230, title: 'Analysis Skill', sub: 'read-only · JSON', kind: 'ai', zone: 3, path: '.claude/skills/k8s-failure-analysis/', does: 'Headless claude -p with Read, Grep, Glob. Returns classification, root cause, fix plan and confidence via --json-schema.' },
  { id: 'agent', x: 842, y: 230, title: 'Remediation Subagent', sub: 'k8s-remediator', kind: 'ai', zone: 4, path: '.claude/agents/k8s-remediator.md', does: 'Applies the smallest fix in an isolated worktree. Edit allowed only under demo/charts/**; the only shell command is the validator.' },
  { id: 'local', x: 654, y: 230, title: 'Local Validation', sub: 'validator + scope', kind: 'det', zone: 4, path: 'tools/chart_validator · check_scope()', does: 'YAML → helm lint → helm template → kubeconform → consistency. Diff must stay inside the allowlist and ≤ 40 changed lines.' },
  { id: 'push', x: 466, y: 230, title: 'Git Push', sub: 'fast-forward only', kind: 'det', zone: 5, path: 'backend (not the agent)', does: 'Backend commits and pushes only if the remote head still equals the expected SHA. Protected branches refused. Never merges.' },
  { id: 'gha2', x: 278, y: 230, title: 'GitHub Actions', sub: 'helm-validate on new SHA', kind: 'ext', zone: 5, path: 'required checks · exact SHA', does: 'DONE only when every required check passes on the pushed SHA. Otherwise retry (bounded) or NEEDS_REVIEW.' },
  { id: 'slack', x: 90, y: 230, title: 'Slack', sub: 'Incoming Webhook', kind: 'ext', zone: 5, path: 'backend/app/integrations/slack.py', does: 'Block Kit summary: problem, root cause, diff, links. Secrets redacted before sending.' },
]

const edges: [string, string, string][] = [
  ['hook', 'api', 'POST /register'],
  ['api', 'db', 'insert task'],
  ['db', 'sched', 'claim lease'],
  ['sched', 'gha', 'poll checks'],
  ['gha', 'skill', 'job log + findings'],
  ['skill', 'agent', 'diagnosis'],
  ['agent', 'local', 'edited worktree'],
  ['local', 'push', 'all gates ✓'],
  ['push', 'gha2', 'new SHA'],
  ['gha2', 'slack', 'result'],
]

const zones = [
  { n: 0, name: 'Overview', text: 'Eleven parts, one loop. Violet nodes are LLM-driven; everything else is ordinary, deterministic code.' },
  { n: 1, name: 'Detect', text: 'A local hook turns "Claude opened a PR" into a durable task. The database is the single source of truth.' },
  { n: 2, name: 'Observe', text: 'The worker polls GitHub check runs for the PR head SHA and pulls the failed job log as evidence.' },
  { n: 3, name: 'Reason', text: 'A read-only headless run applies the analysis skill and must answer in a JSON schema.' },
  { n: 4, name: 'Repair', text: 'The subagent edits an isolated worktree; the backend re-validates and re-checks scope on the real diff.' },
  { n: 5, name: 'Deliver', text: 'Only the backend pushes. GitHub — not the agent — decides when the task is DONE. Slack tells the humans.' },
]

const byId = Object.fromEntries(nodes.map(n => [n.id, n]))
const zone = computed(() => Math.min(Math.max(props.step, 0), 6))
const selected = ref<Node | null>(null)
watch(() => props.step, () => { selected.value = null })

const isOn = (n: Node) => zone.value === 0 || zone.value === 6 || n.zone === zone.value
const isPast = (n: Node) => zone.value > 0 && zone.value < 6 && n.zone < zone.value
const edgeOn = (a: string, b: string) => {
  const z = zone.value
  if (z === 0) return false
  if (z === 6) return true
  return byId[b].zone <= z && byId[a].zone <= z
}
const edgeCurrent = (a: string, b: string) => zone.value === 6 || byId[b].zone === zone.value

function edgePath(a: Node, b: Node) {
  if (a.y === b.y) {
    const dir = b.x > a.x ? 1 : -1
    return `M ${a.x + dir * 80} ${a.y} L ${b.x - dir * 80} ${b.y}`
  }
  // the turn from the top row down to the bottom row
  return `M ${a.x + 70} ${a.y + 30} C ${a.x + 150} ${a.y + 80}, ${b.x + 120} ${b.y - 80}, ${b.x + 40} ${b.y - 32}`
}
function labelPos(a: Node, b: Node) {
  if (a.y === b.y) return { x: (a.x + b.x) / 2, y: a.y - 40 }
  return { x: Math.min(a.x, b.x) - 40, y: (a.y + b.y) / 2 + 4 }
}

const panel = computed(() => {
  if (selected.value) return { eyebrow: selected.value.path, title: selected.value.title, text: selected.value.does }
  const z = zones[Math.min(zone.value, 5)]
  if (zone.value === 6) return { eyebrow: 'the whole loop', title: 'AI proposes. Deterministic systems verify.', text: 'Two violet boxes out of eleven. Every arrow that leaves an AI step lands on a deterministic check.' }
  return { eyebrow: z.n ? `zone ${z.n} of 5` : 'click any node for details', title: z.name, text: z.text }
})
</script>

<template>
  <div class="ax">
    <div class="canvas">
      <svg viewBox="0 0 1136 300" class="wires" aria-hidden="true">
        <defs>
          <marker id="ax-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b5cf6" />
          </marker>
        </defs>
        <g v-for="[a, b, label] in edges" :key="a + b">
          <path
            :d="edgePath(byId[a], byId[b])"
            class="edge"
            :class="{ on: edgeOn(a, b), cur: edgeOn(a, b) && edgeCurrent(a, b) }"
            :marker-end="edgeOn(a, b) ? 'url(#ax-arrow)' : undefined"
          />
          <text
            :x="labelPos(byId[a], byId[b]).x"
            :y="labelPos(byId[a], byId[b]).y"
            text-anchor="middle"
            class="elabel"
            :class="{ on: edgeOn(a, b) }"
          >{{ label }}</text>
        </g>
      </svg>

      <button
        v-for="n in nodes"
        :key="n.id"
        class="node"
        :class="[n.kind, { on: isOn(n), past: isPast(n), sel: selected?.id === n.id }]"
        :style="{ left: `${(n.x / 1136) * 100}%`, top: `${(n.y / 300) * 100}%` }"
        @click="selected = selected?.id === n.id ? null : n"
      >
        <span class="t">{{ n.title }}</span>
        <span class="s mono">{{ n.sub }}</span>
      </button>
    </div>

    <div class="legend mono">
      <span><i class="sw det" /> deterministic code</span>
      <span><i class="sw ai" /> LLM agent</span>
      <span><i class="sw ext" /> external system</span>
    </div>

    <Transition name="fade-up" mode="out-in">
      <div :key="panel.title" class="panel glass">
        <div class="eyebrow">{{ panel.eyebrow }}</div>
        <div class="row">
          <h3>{{ panel.title }}</h3>
          <p>{{ panel.text }}</p>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ax { margin-top: 10px; }
.canvas { position: relative; width: 100%; aspect-ratio: 1136 / 300; }
.wires { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.edge { fill: none; stroke: rgba(255, 255, 255, 0.1); stroke-width: 1.4; transition: stroke 400ms; }
.edge.on { stroke: rgba(139, 92, 246, 0.55); }
.edge.cur { stroke: #8b5cf6; stroke-dasharray: 5 7; animation: dash-flow 1s linear infinite; }
.elabel { font-family: var(--font-mono); font-size: 10.5px; fill: #3f4250; transition: fill 400ms; }
.elabel.on { fill: #9ca3af; }

.node {
  position: absolute; transform: translate(-50%, -50%);
  width: 156px; padding: 10px 10px 9px; border-radius: 12px; cursor: pointer;
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  background: var(--surface); border: 1px solid var(--border); color: var(--text);
  font-family: var(--font-sans); opacity: 0.28;
  transition: opacity 400ms var(--ease), box-shadow 400ms, border-color 400ms, transform 400ms var(--ease);
}
.node.on, .node.past { opacity: 1; }
.node.past { opacity: 0.6; }
.node .t { font-size: 14px; font-weight: 600; line-height: 1.2; text-align: center; }
.node .s { font-size: 10.5px; color: var(--faint); text-align: center; }
.node.ai { background: linear-gradient(180deg, rgba(139, 92, 246, 0.2), rgba(20, 20, 31, 0.95)); border-color: rgba(139, 92, 246, 0.45); }
.node.ai .s { color: #c4b5fd; }
.node.ext { border-style: dashed; border-color: rgba(255, 255, 255, 0.2); }
.node.on.ai { box-shadow: var(--glow-violet); }
.node.on.det { border-color: rgba(99, 102, 241, 0.45); }
.node.sel { transform: translate(-50%, -50%) scale(1.06); box-shadow: 0 0 0 2px #a78bfa, 0 0 36px rgba(139, 92, 246, 0.45); opacity: 1; }
.node:focus-visible { outline: 2px solid #a78bfa; outline-offset: 3px; }

.legend { display: flex; gap: 22px; justify-content: center; font-size: 11px; color: var(--faint); margin: 2px 0 12px; }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.sw { width: 12px; height: 12px; border-radius: 4px; display: inline-block; border: 1px solid; }
.sw.det { border-color: rgba(99, 102, 241, 0.6); background: var(--surface); }
.sw.ai { border-color: rgba(139, 92, 246, 0.7); background: var(--violet-soft); }
.sw.ext { border: 1px dashed rgba(255, 255, 255, 0.35); }

.panel { padding: 14px 22px; min-height: 92px; }
.panel .eyebrow { margin-bottom: 6px; text-transform: none; letter-spacing: 0.04em; }
.panel .row { display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: baseline; }
.panel h3 { margin: 0 !important; font-size: 22px !important; }
.panel p { color: var(--muted); font-size: 16px; line-height: 1.45; }
</style>
