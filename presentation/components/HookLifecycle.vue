<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ step?: number }>(), { step: 99 })

const stages = [
  {
    key: 'session',
    title: 'Claude Code',
    where: 'developer laptop',
    icon: 'i-lucide-terminal-square',
    caption: 'The developer asks Claude to open a PR. Claude decides to call the Bash tool.',
    code: `> open a PR for the memory bump

● Bash(gh pr create --fill)`,
  },
  {
    key: 'tool',
    title: 'Tool Execution',
    where: 'Bash tool',
    icon: 'i-lucide-play',
    caption: 'The command runs. GitHub creates the PR and gh prints its URL.',
    code: `https://github.com/brinops/ai-workshop/pull/42`,
  },
  {
    key: 'hook',
    title: 'PostToolUse',
    where: 'hook process · stdin JSON',
    icon: 'i-lucide-webhook',
    caption: 'Matcher "Bash" fires the hook. It ignores everything except gh pr create, then confirms the PR with gh pr view.',
    code: `{ "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": { "command": "gh pr create --fill" },
  "tool_response": { "stdout": "https://…/pull/42" },
  "cwd": "/Users/dev/ai-workshop" }`,
  },
  {
    key: 'api',
    title: 'Registration API',
    where: 'FastAPI · POST',
    icon: 'i-lucide-server',
    caption: 'Idempotent: the backend de-duplicates on (repo, pr_number) and re-verifies the PR against GitHub itself.',
    code: `POST /api/tasks/register
{ "repo": "brinops/ai-workshop", "pr_number": 42,
  "head_sha": "9f3c1e2", "source": "hook" }
→ 200 { "task_id": 7, "created": true }`,
  },
  {
    key: 'db',
    title: 'SQLite',
    where: 'WAL · UNIQUE(repo, pr_number)',
    icon: 'i-lucide-database',
    caption: 'One row per PR. The state machine records an audit event in the same transaction.',
    code: `tasks   #7  repo=brinops/ai-workshop  pr=42  state=WAITING_CI
events  state_changed  "NEW → WAITING_CI: registered"`,
  },
  {
    key: 'ui',
    title: 'Dashboard',
    where: 'REST + SSE',
    icon: 'i-lucide-layout-dashboard',
    caption: 'SSE tails the events table by id, so the card appears live — even across restarts.',
    code: `event: state_changed
id: 1287
data: {"task_id": 7, "to": "WAITING_CI"}`,
  },
]

const active = computed(() => Math.min(props.step - 1, stages.length - 1))
const current = computed(() => (active.value >= 0 ? stages[active.value] : null))
</script>

<template>
  <div class="hl">
    <div class="rail">
      <template v-for="(s, i) in stages" :key="s.key">
        <div class="stage" :class="{ done: i < active, active: i === active, hookish: s.key === 'hook' }">
          <div class="dot"><div :class="s.icon" /></div>
          <div class="title">{{ s.title }}</div>
          <div class="where mono">{{ s.where }}</div>
        </div>
        <div v-if="i < stages.length - 1" class="link" :class="{ on: i < active }">
          <span class="packet" :class="{ go: i === active - 1 }" />
        </div>
      </template>
    </div>

    <div class="boundary">
      <div class="bound local" :class="{ on: active >= 0 && active <= 2 }">
        <span class="mono">runs locally, inside the Claude Code session</span>
      </div>
      <div class="bound remote" :class="{ on: active >= 3 }">
        <span class="mono">control plane · one Python process</span>
      </div>
    </div>

    <Transition name="fade-up" mode="out-in">
      <div v-if="current" :key="current.key" class="detail glass">
        <div class="cap">
          <div class="eyebrow">{{ String(active + 1).padStart(2, '0') }} · {{ current.title }}</div>
          <p>{{ current.caption }}</p>
        </div>
        <pre class="payload">{{ current.code }}</pre>
      </div>
      <div v-else class="detail hint mono">press → to follow one PR through the hook</div>
    </Transition>
  </div>
</template>

<style scoped>
.hl { margin-top: 22px; }
.rail { display: flex; align-items: flex-start; }
.stage { width: 150px; flex: 0 0 auto; text-align: center; opacity: 0.35; transition: opacity 400ms var(--ease); }
.stage.done, .stage.active { opacity: 1; }
.dot {
  width: 58px; height: 58px; margin: 0 auto 12px; border-radius: 16px;
  display: grid; place-items: center; font-size: 24px;
  background: var(--surface); border: 1px solid var(--border-strong); color: var(--muted);
  transition: all 400ms var(--ease);
}
.stage.done .dot { color: #c4b5fd; border-color: rgba(139, 92, 246, 0.4); }
.stage.active .dot { color: #fff; background: linear-gradient(135deg, #8b5cf6, #6366f1); border-color: transparent; animation: pulse-ring 1.6s var(--ease) 2; }
.stage.hookish.active .dot { box-shadow: 0 0 30px rgba(139, 92, 246, 0.6); }
.title { font-weight: 600; font-size: 16px; }
.where { font-size: 11px; color: var(--faint); margin-top: 4px; line-height: 1.35; }
.link { flex: 1; position: relative; height: 1px; margin-top: 29px; background: rgba(255, 255, 255, 0.1); }
.link.on { background: linear-gradient(90deg, #8b5cf6, #6366f1); }
.packet {
  position: absolute; top: -4px; left: 0; width: 9px; height: 9px; border-radius: 50%;
  background: #c4b5fd; box-shadow: 0 0 12px #8b5cf6; opacity: 0;
}
.packet.go { animation: travel 700ms var(--ease) forwards; }
@keyframes travel { 0% { left: 0; opacity: 1; } 90% { opacity: 1; } 100% { left: calc(100% - 9px); opacity: 0; } }

.boundary { display: grid; grid-template-columns: 3fr 3fr; gap: 14px; margin: 14px 0 18px; }
.bound { border-top: 1px dashed rgba(255, 255, 255, 0.12); padding-top: 8px; text-align: center; font-size: 11px; color: var(--faint); letter-spacing: 0.06em; transition: all 400ms; }
.bound.on.local { border-color: rgba(139, 92, 246, 0.6); color: #c4b5fd; }
.bound.on.remote { border-color: rgba(99, 102, 241, 0.6); color: #c7d2fe; }

.detail { display: grid; grid-template-columns: 1fr 1.25fr; gap: 26px; padding: 20px 24px; align-items: center; min-height: 150px; }
.detail .eyebrow { margin-bottom: 8px; }
.detail p { color: var(--muted); font-size: 18px; line-height: 1.45; }
.payload {
  margin: 0; font-family: var(--font-mono); font-size: 13.5px; line-height: 1.6;
  color: #ddd6fe; background: rgba(5, 5, 10, 0.7); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 16px; white-space: pre; overflow: hidden;
}
.hint { display: grid; place-items: center; color: var(--faint); font-size: 14px; border: 1px dashed var(--border-strong); border-radius: var(--radius); }
</style>
