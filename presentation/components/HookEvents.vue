<script setup lang="ts">
// The most useful hook events, laid out along a session's lifecycle.
// Click 1 reveals what each event can decide; click 2 shows how this repo could use it.
withDefaults(defineProps<{ step?: number }>(), { step: 99 })

type Kind = 'gate' | 'loop' | 'observe'
interface Ev { name: string; when: string; effect: string; kind: Kind; idea: string; used?: boolean }

const phases: { title: string; icon: string; events: Ev[] }[] = [
  {
    title: 'Session & prompt',
    icon: 'i-lucide-log-in',
    events: [
      { name: 'SessionStart', when: 'session starts, resumes or compacts', effect: 'adds context', kind: 'observe', idea: 'inject open remediation tasks + git status' },
      { name: 'UserPromptSubmit', when: 'before Claude reads your prompt', effect: 'block prompt · add context', kind: 'gate', idea: 'reject prompts that contain a token' },
    ],
  },
  {
    title: 'Tool loop',
    icon: 'i-lucide-repeat',
    events: [
      { name: 'PreToolUse', when: 'before a tool call runs', effect: 'allow · deny · ask · rewrite input', kind: 'gate', idea: 'deny edits outside demo/charts/**' },
      { name: 'PermissionRequest', when: 'a permission dialog would appear', effect: 'approve · deny for the user', kind: 'gate', idea: 'auto-approve helm template, never kubectl' },
      { name: 'PostToolUse', when: 'after a tool call succeeds', effect: 'feedback to Claude · tool already ran', kind: 'observe', idea: 'register the PR with the control plane', used: true },
    ],
  },
  {
    title: 'Finishing',
    icon: 'i-lucide-flag',
    events: [
      { name: 'Stop', when: 'Claude is about to end its turn', effect: 'block → keep working', kind: 'loop', idea: 'not done until the chart validator passes' },
      { name: 'SubagentStop', when: 'a subagent is about to finish', effect: 'block → keep the subagent going', kind: 'loop', idea: 'reject a remediator diff over 40 lines' },
    ],
  },
  {
    title: 'Around the session',
    icon: 'i-lucide-orbit',
    events: [
      { name: 'Notification', when: 'Claude needs input or permission', effect: 'side effect only', kind: 'observe', idea: 'ping Slack when the agent waits' },
      { name: 'PreCompact', when: 'before context is compacted', effect: 'block compaction', kind: 'gate', idea: 'save the diagnosis before it is summarised' },
      { name: 'SessionEnd', when: 'session terminates', effect: 'side effect only', kind: 'observe', idea: 'release the task lease, flush logs' },
    ],
  },
]

const kindLabel: Record<Kind, string> = { gate: 'can block', loop: 'can continue', observe: 'observe / inform' }
</script>

<template>
  <div class="he">
    <div class="rail" aria-hidden="true" />
    <div class="phases">
      <section v-for="(p, i) in phases" :key="p.title" class="phase">
        <header>
          <span class="idx mono">{{ i + 1 }}</span>
          <div :class="p.icon" />
          <span>{{ p.title }}</span>
        </header>
        <article
          v-for="e in p.events"
          :key="e.name"
          class="ev"
          :class="[e.kind, { used: e.used, lit: step >= 1 }]"
        >
          <div class="top">
            <span class="name mono">{{ e.name }}</span>
            <span v-if="e.used" class="tag mono">used here</span>
          </div>
          <div class="when">{{ e.when }}</div>
          <div class="effect" :class="{ on: step >= 1 }">
            <span class="dot" />{{ e.effect }}
          </div>
          <div class="idea" :class="{ on: step >= 2 }">
            <div class="i-lucide-lightbulb" />{{ e.used ? 'this repo: ' : 'could: ' }}{{ e.idea }}
          </div>
        </article>
      </section>
    </div>

    <div class="legend" :class="{ on: step >= 1 }">
      <span v-for="(label, k) in kindLabel" :key="k" class="lg" :class="k"><span class="dot" />{{ label }}</span>
      <span class="more mono">+ 20 more events · handler types: command · http · prompt · agent · mcp_tool</span>
    </div>
  </div>
</template>

<style scoped>
.he { position: relative; margin-top: 14px; }
.rail {
  position: absolute; left: 0; right: 0; top: 15px; height: 1px;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.6), rgba(34, 197, 94, 0.3));
}
.phases { display: grid; grid-template-columns: 1fr 1.08fr 1fr 1fr; gap: 14px; }
.phase { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.phase header {
  position: relative; display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600;
  color: var(--text); margin-bottom: 4px; padding-right: 8px; background: var(--bg, #0a0a0f); width: fit-content;
}
.phase header .idx {
  width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font-size: 12px;
  border: 1px solid var(--border-strong); background: var(--surface); color: #c4b5fd;
}
.phase header > div { color: var(--faint); font-size: 15px; }

.ev {
  padding: 9px 12px 10px; border-radius: 12px; border: 1px solid var(--border);
  background: rgba(20, 20, 31, 0.7); transition: border-color 450ms var(--ease), box-shadow 450ms, opacity 450ms;
}
.ev.used { border-color: rgba(139, 92, 246, 0.65); box-shadow: 0 16px 44px -26px rgba(139, 92, 246, 0.8); }
.ev.lit.gate { border-color: rgba(239, 68, 68, 0.4); }
.ev.lit.loop { border-color: rgba(245, 158, 11, 0.42); }
.ev.lit.used { border-color: rgba(139, 92, 246, 0.75); }
.top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.name { font-size: 13.5px; font-weight: 600; color: #e0e7ff; }
.tag {
  font-size: 9.5px; letter-spacing: 0.08em; text-transform: uppercase; padding: 2px 6px; border-radius: 6px;
  background: var(--violet-soft); color: #c4b5fd; white-space: nowrap;
}
.when { font-size: 12px; color: var(--muted); line-height: 1.35; margin-top: 2px; }
.effect {
  display: flex; align-items: center; gap: 6px; margin-top: 6px; font-size: 11.5px; font-family: var(--font-mono);
  color: var(--faint); opacity: 0.35; transition: opacity 450ms, color 450ms;
}
.effect.on { opacity: 1; }
.gate .effect.on { color: #fca5a5; }
.loop .effect.on { color: #fcd34d; }
.observe .effect.on { color: #a5b4fc; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: none; }
.idea {
  display: flex; align-items: flex-start; gap: 6px; font-size: 11.5px; line-height: 1.35; color: #c4b5fd;
  max-height: 0; opacity: 0; overflow: hidden; transition: max-height 500ms var(--ease), opacity 500ms, margin 500ms;
}
.idea.on { max-height: 40px; opacity: 1; margin-top: 6px; }
.idea > div { flex: none; margin-top: 1px; font-size: 12px; }

.legend {
  display: flex; align-items: center; gap: 18px; margin-top: 14px; font-size: 12px; color: var(--muted);
  opacity: 0; transition: opacity 450ms;
}
.legend.on { opacity: 1; }
.lg { display: flex; align-items: center; gap: 6px; }
.lg.gate { color: #fca5a5; }
.lg.loop { color: #fcd34d; }
.lg.observe { color: #a5b4fc; }
.more { margin-left: auto; font-size: 11px; color: var(--faint); }
</style>
