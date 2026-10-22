<script setup lang="ts">
import { computed } from 'vue'

// Every hook event from code.claude.com/docs/en/hooks, split into four slides.
// `effect` is what the hook can decide; `use` is an example (only PostToolUse is implemented here).
const props = defineProps<{ group: 1 | 2 | 3 | 4 }>()

type Kind = 'gate' | 'loop' | 'observe'
interface Ev { name: string; when: string; effect: string; kind: Kind; use: string; used?: boolean }

const groups: Record<number, Ev[]> = {
  1: [
    { name: 'SessionStart', when: 'session begins, resumes, clears or compacts', effect: 'add context · set session title', kind: 'observe', use: 'inject git status + open remediation tasks' },
    { name: 'Setup', when: 'claude --init-only, or --init / --maintenance with -p', effect: 'one-time preparation, no decision', kind: 'observe', use: 'install deps, seed the DB in CI' },
    { name: 'InstructionsLoaded', when: 'a CLAUDE.md or .claude/rules/*.md file is loaded', effect: 'observe only · exit code ignored', kind: 'observe', use: 'audit which rules the agent actually saw' },
    { name: 'ConfigChange', when: 'a settings or skills file changes mid-session', effect: 'block the change (not policy settings)', kind: 'gate', use: 'stop an agent from widening its own permissions' },
    { name: 'CwdChanged', when: 'working directory changes, e.g. after cd', effect: 'side effect only', kind: 'observe', use: 'direnv-style environment reload' },
    { name: 'DirectoryAdded', when: 'a directory is added via /add-dir or the SDK', effect: 'side effect only', kind: 'observe', use: 'record extra repos in the audit trail' },
    { name: 'FileChanged', when: 'a watched file changes on disk (matcher = file names)', effect: 'side effect only', kind: 'observe', use: 'react when .env or .envrc changes' },
    { name: 'SessionEnd', when: 'session terminates: clear, logout, exit …', effect: 'side effect only', kind: 'observe', use: 'release the task lease, flush logs' },
  ],
  2: [
    { name: 'UserPromptSubmit', when: 'a prompt is submitted, before Claude processes it', effect: 'block · add context (no rewrite)', kind: 'gate', use: 'reject prompts that contain a token' },
    { name: 'UserPromptExpansion', when: 'a typed /command expands into a prompt', effect: 'block the expansion · add context', kind: 'gate', use: 'restrict which slash commands may run' },
    { name: 'PreToolUse', when: 'before a tool call executes', effect: 'allow · deny · ask · defer · rewrite input', kind: 'gate', use: 'deny edits outside demo/charts/**' },
    { name: 'PermissionRequest', when: 'a tool call needs a permission decision', effect: 'allow · deny via decision object', kind: 'gate', use: 'auto-approve helm template, never kubectl' },
    { name: 'PermissionDenied', when: 'auto mode denies a tool call', effect: 'retry: true → model may try again', kind: 'loop', use: 'log denials, let safe retries through' },
    { name: 'PostToolUse', when: 'after a tool call succeeds', effect: 'feedback · replace output · tool already ran', kind: 'observe', use: 'register the PR with the control plane', used: true },
    { name: 'PostToolUseFailure', when: 'after a tool call fails', effect: 'add context', kind: 'observe', use: 'attach the runbook for a failing command' },
    { name: 'PostToolBatch', when: 'a batch of parallel tool calls resolves, before the next model call', effect: 'block → stop the agentic loop', kind: 'gate', use: 'halt when one batch touched too many files' },
    { name: 'MessageDisplay', when: 'assistant text is displayed', effect: 'replace on-screen text only', kind: 'observe', use: 'mask secrets in the terminal view' },
  ],
  3: [
    { name: 'Stop', when: 'Claude finishes responding', effect: 'block → keep working', kind: 'loop', use: 'not done until the chart validator passes' },
    { name: 'StopFailure', when: 'the turn ends due to an API error (rate_limit, overloaded …)', effect: 'output ignored · notify only', kind: 'observe', use: 'alert on billing or rate-limit failures' },
    { name: 'SubagentStart', when: 'a subagent is spawned (matcher = agent type)', effect: 'add context', kind: 'observe', use: 'brief the remediator with the task id' },
    { name: 'SubagentStop', when: 'a subagent finishes', effect: 'block → keep the subagent going', kind: 'loop', use: 'reject a remediator diff over 40 lines' },
    { name: 'TaskCreated', when: 'a task is being created via TaskCreate', effect: 'block → cancel the task', kind: 'gate', use: 'cap how many tasks one agent may open' },
    { name: 'TaskCompleted', when: 'a task is being marked as completed', effect: 'block → not completed yet', kind: 'loop', use: 'require green tests before "done"' },
    { name: 'TeammateIdle', when: 'an agent-team teammate is about to go idle', effect: 'block → keep it working', kind: 'loop', use: 'hand the next queued PR to an idle teammate' },
  ],
  4: [
    { name: 'PreCompact', when: 'before context compaction (manual or auto)', effect: 'block compaction', kind: 'gate', use: 'save the diagnosis before it is summarised' },
    { name: 'PostCompact', when: 'after context compaction completes', effect: 'side effect only', kind: 'observe', use: 'note the compaction in the audit trail' },
    { name: 'PreModelSwitch', when: 'before a requested model switch is applied', effect: 'allow · deny · ask', kind: 'gate', use: 'pin the remediator to an approved model' },
    { name: 'PostModelSwitch', when: 'after the model changes, incl. on resume', effect: 'add context', kind: 'observe', use: 'record the model per task for cost reports' },
    { name: 'Elicitation', when: 'an MCP server asks the user for input', effect: 'accept · decline · cancel · fill content', kind: 'gate', use: 'answer or decline automatically in headless runs' },
    { name: 'ElicitationResult', when: 'the user answered, before it goes back to the server', effect: 'change or block (→ decline)', kind: 'gate', use: 'validate what is sent to MCP servers' },
    { name: 'WorktreeCreate', when: 'a worktree is created (--worktree, isolation)', effect: 'replaces git · returns the path, non-zero fails', kind: 'gate', use: 'custom worktree layout or a non-git VCS' },
    { name: 'WorktreeRemove', when: 'a hook-created worktree is removed', effect: 'non-zero exit fails removal', kind: 'observe', use: 'clean up what WorktreeCreate made' },
    { name: 'Notification', when: 'Claude Code sends a notification', effect: 'side effect only', kind: 'observe', use: 'ping Slack when the agent waits for input' },
  ],
}

const events = computed(() => groups[props.group])
const kindLabel: Record<Kind, string> = { gate: 'can block', loop: 'can continue', observe: 'observe / inform' }
</script>

<template>
  <div class="hc">
    <div class="grid">
      <article v-for="e in events" :key="e.name" class="ev" :class="[e.kind, { used: e.used }]">
        <div class="top">
          <span class="name mono">{{ e.name }}</span>
          <span v-if="e.used" class="tag mono">used here</span>
        </div>
        <div class="when">{{ e.when }}</div>
        <div class="effect"><span class="dot" />{{ e.effect }}</div>
        <div class="use"><div class="i-lucide-lightbulb" />{{ e.used ? 'this repo: ' : 'could: ' }}{{ e.use }}</div>
      </article>
    </div>
    <div class="legend">
      <span v-for="(label, k) in kindLabel" :key="k" class="lg" :class="k"><span class="dot" />{{ label }}</span>
      <span class="count mono">{{ group }} / 4 · 33 events</span>
    </div>
  </div>
</template>

<style scoped>
.hc { margin-top: 14px; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 14px; }
.ev {
  padding: 9px 12px 10px; border-radius: 12px; border: 1px solid var(--border);
  background: rgba(20, 20, 31, 0.7); min-width: 0;
}
.ev.gate { border-color: rgba(239, 68, 68, 0.32); }
.ev.loop { border-color: rgba(245, 158, 11, 0.35); }
.ev.used { border-color: rgba(139, 92, 246, 0.75); box-shadow: 0 16px 44px -26px rgba(139, 92, 246, 0.8); }
.top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.name { font-size: 13.5px; font-weight: 600; color: #e0e7ff; }
.tag {
  font-size: 9.5px; letter-spacing: 0.08em; text-transform: uppercase; padding: 2px 6px; border-radius: 6px;
  background: var(--violet-soft); color: #c4b5fd; white-space: nowrap;
}
.when { font-size: 12px; color: var(--muted); line-height: 1.35; margin-top: 2px; }
.effect { display: flex; align-items: center; gap: 6px; margin-top: 5px; font-size: 11.5px; font-family: var(--font-mono); }
.gate .effect { color: #fca5a5; }
.loop .effect { color: #fcd34d; }
.observe .effect { color: #a5b4fc; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: none; }
.use { display: flex; align-items: flex-start; gap: 6px; margin-top: 5px; font-size: 11.5px; line-height: 1.35; color: #c4b5fd; }
.use > div { flex: none; margin-top: 1px; font-size: 12px; }

.legend { display: flex; align-items: center; gap: 18px; margin-top: 12px; font-size: 12px; }
.lg { display: flex; align-items: center; gap: 6px; }
.lg.gate { color: #fca5a5; }
.lg.loop { color: #fcd34d; }
.lg.observe { color: #a5b4fc; }
.count { margin-left: auto; font-size: 11px; color: var(--faint); }
</style>
