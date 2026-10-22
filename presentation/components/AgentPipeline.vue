<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ step?: number }>(), { step: 99 })

const stages = [
  { key: 'ci', title: 'Failed CI', kind: 'deterministic', icon: 'i-lucide-circle-x', note: 'check run helm-validate = failure on head SHA' },
  { key: 'evidence', title: 'Evidence Collection', kind: 'deterministic', icon: 'i-lucide-files', note: 'job log · RCP-FINDING lines · PR diff — redacted, size-limited' },
  { key: 'skill', title: 'Analysis Skill', kind: 'ai', icon: 'i-lucide-book-open-text', note: 'claude -p · Read, Grep, Glob only' },
  { key: 'diag', title: 'Structured Diagnosis', kind: 'deterministic', icon: 'i-lucide-braces', note: 'JSON Schema → reconcile() with validator category' },
  { key: 'agent', title: 'Remediation Subagent', kind: 'ai', icon: 'i-lucide-bot', note: 'claude -p --agent k8s-remediator · edit allowlist' },
]
const active = computed(() => Math.min(props.step - 1, stages.length - 1))
</script>

<template>
  <div class="ap">
    <div class="flow">
      <template v-for="(s, i) in stages" :key="s.key">
        <div class="st" :class="[s.kind, { on: i <= active, cur: i === active }]">
          <div class="ico"><div :class="s.icon" /></div>
          <div class="t">{{ s.title }}</div>
          <div class="n mono">{{ s.note }}</div>
          <span class="tag mono">{{ s.kind === 'ai' ? 'LLM' : 'code' }}</span>
        </div>
        <div v-if="i < stages.length - 1" class="ar" :class="{ on: i < active }">
          <div class="i-lucide-chevron-right" />
        </div>
      </template>
    </div>

    <div class="lower">
      <div class="why" :class="{ on: active >= 3 }">
        <div class="eyebrow">why structured output</div>
        <ul>
          <li><b>Machine-checkable</b> — the backend validates fields, not prose</li>
          <li><b>Gateable</b> — confidence ≥ 0.6, paths ⊂ <span class="mono">demo/charts/**</span></li>
          <li><b>Reconcilable</b> — if the validator says <span class="mono">SCHEMA_VIOLATION</span>, that category wins</li>
          <li><b>Auditable</b> — stored, rendered, posted to Slack verbatim</li>
        </ul>
      </div>
      <div class="json" :class="{ on: active >= 3 }">
        <div class="jhead mono"><span>structured_output</span><span class="pill ok">schema valid</span></div>
<pre><span class="k">"classification"</span>: <span class="s">"LOGICAL_CONFIGURATION_ERROR"</span>,
<span class="k">"root_cause"</span>: <span class="s">"service.targetPort 9090 does not match app.port 8080"</span>,
<span class="k">"affected_files"</span>: [{ <span class="k">"path"</span>: <span class="s">"demo/charts/payments-api/values.yaml"</span> }],
<span class="k">"proposed_fix"</span>: { <span class="k">"summary"</span>: <span class="s">"restore targetPort to 8080"</span>, … },
<span class="k">"confidence"</span>: <span class="num">0.93</span>,
<span class="k">"auto_remediation_appropriate"</span>: <span class="num">true</span></pre>
        <div class="rec mono" :class="{ on: active >= 4 }">
          <div class="i-lucide-scale" /> reconcile(): validator = LOGICAL_CONFIGURATION_ERROR · agreement ✓ · remediable
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ap { margin-top: 20px; }
.flow { display: flex; align-items: stretch; gap: 0; }
.st {
  position: relative; flex: 1; min-width: 0; padding: 16px 14px 14px; border-radius: var(--radius);
  background: var(--surface); border: 1px solid var(--border); opacity: 0.3;
  transition: opacity 450ms var(--ease), box-shadow 450ms, border-color 450ms, transform 450ms var(--ease);
}
.st.on { opacity: 1; }
.st.cur { transform: translateY(-4px); }
.st.ai.cur { box-shadow: var(--glow-violet); border-color: rgba(139, 92, 246, 0.6); }
.st.deterministic.cur { box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.55), 0 0 28px rgba(99, 102, 241, 0.25); border-color: rgba(99, 102, 241, 0.6); }
.st:first-child.cur { box-shadow: var(--glow-fail); border-color: rgba(239, 68, 68, 0.6); }
.ico { font-size: 22px; margin-bottom: 8px; color: var(--muted); }
.st.ai .ico { color: #a78bfa; }
.st:first-child .ico { color: #f87171; }
.t { font-weight: 600; font-size: 16px; line-height: 1.25; }
.n { font-size: 11px; color: var(--faint); margin-top: 6px; line-height: 1.45; }
.tag { position: absolute; top: 12px; right: 12px; font-size: 10px; letter-spacing: 0.1em; padding: 2px 6px; border-radius: 5px; border: 1px solid var(--border-strong); color: var(--faint); }
.st.ai .tag { color: #c4b5fd; border-color: rgba(139, 92, 246, 0.45); }
.ar { display: grid; place-items: center; width: 26px; flex: 0 0 auto; color: rgba(255, 255, 255, 0.15); transition: color 400ms; }
.ar.on { color: #8b5cf6; }

.lower { display: grid; grid-template-columns: 0.9fr 1.3fr; gap: 22px; margin-top: 22px; }
.why, .json { opacity: 0; transform: translateY(8px); transition: opacity 500ms var(--ease), transform 500ms var(--ease); }
.why.on, .json.on { opacity: 1; transform: none; }
.why ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; font-size: 16px; color: var(--muted); }
.why b { color: var(--text); }
.why .mono { font-size: 13px; color: #c4b5fd; }
.json { border-radius: var(--radius); border: 1px solid var(--border-strong); background: rgba(6, 6, 12, 0.9); overflow: hidden; }
.jhead { display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; font-size: 12px; color: var(--faint); border-bottom: 1px solid var(--border); }
pre { margin: 0; padding: 12px 16px; font-family: var(--font-mono); font-size: 12.5px; line-height: 1.65; color: var(--muted); white-space: pre; overflow: hidden; }
.k { color: #93c5fd; } .s { color: #86efac; } .num { color: #fcd34d; }
.rec { display: flex; gap: 8px; align-items: center; padding: 8px 14px; font-size: 12px; color: #86efac; border-top: 1px solid var(--border); background: rgba(34, 197, 94, 0.06); opacity: 0; transition: opacity 500ms; }
.rec.on { opacity: 1; }
</style>
