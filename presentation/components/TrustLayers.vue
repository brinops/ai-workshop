<script setup lang="ts">
withDefaults(defineProps<{ step?: number }>(), { step: 99 })

const phases = [
  {
    title: 'Before the agent runs',
    sub: 'constrain what it can touch',
    gates: [
      { icon: 'i-lucide-key-round', name: 'Least privilege', detail: '--tools allowlist · dontAsk denies the rest · no git, no network' },
      { icon: 'i-lucide-git-branch', name: 'Isolated worktree', detail: 'fresh checkout at the expected SHA; agent config from operator repo' },
    ],
  },
  {
    title: 'After the agent edits',
    sub: 'verify what it produced',
    gates: [
      { icon: 'i-lucide-folder-lock', name: 'File allowlist', detail: 'diff ⊂ demo/charts/** · ≤ 40 changed lines · no deletions' },
      { icon: 'i-lucide-shield-check', name: 'Same validator as CI', detail: 'tools/chart_validator re-run by the backend, not trusted from the agent' },
      { icon: 'i-lucide-fingerprint', name: 'Commit SHA check', detail: 'remote head must equal expected SHA · fast-forward only' },
    ],
  },
  {
    title: 'Before anything ships',
    sub: 'keep humans in charge',
    gates: [
      { icon: 'i-lucide-repeat', name: 'Bounded retries', detail: '≤ 2 attempts · --max-budget-usd · wall-clock timeout' },
      { icon: 'i-lucide-hand', name: 'Approval gates', detail: 'pending_action: analyze | remediate | push' },
      { icon: 'i-lucide-git-merge', name: 'No automatic merge', detail: 'the control plane pushes to the PR branch, never merges' },
      { icon: 'i-lucide-user-check', name: 'Human review', detail: 'NEEDS_REVIEW for low confidence or anything uncertain' },
    ],
  },
]
</script>

<template>
  <div class="tl">
    <div class="band ai">
      <div class="band-label mono"><div class="i-lucide-sparkles" /> AI layer · proposes &amp; executes</div>
      <div class="ai-items">
        <span class="ai-chip">diagnose</span>
        <span class="ai-chip">plan the fix</span>
        <span class="ai-chip">edit files</span>
        <span class="ai-chip">run the validator</span>
      </div>
    </div>

    <div class="membrane" aria-hidden="true"><span /></div>

    <div class="band det">
      <div class="band-label mono"><div class="i-lucide-cpu" /> deterministic layer · verifies</div>
      <div class="phases">
        <div v-for="(p, i) in phases" :key="p.title" class="phase" :class="{ on: step >= i + 1 }">
          <div class="ph-head">
            <span class="ph-n mono">{{ i + 1 }}</span>
            <div>
              <div class="ph-t">{{ p.title }}</div>
              <div class="ph-s mono">{{ p.sub }}</div>
            </div>
          </div>
          <div v-for="g in p.gates" :key="g.name" class="gate">
            <div :class="g.icon" class="gi" />
            <div>
              <div class="gn">{{ g.name }}</div>
              <div class="gd mono">{{ g.detail }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tl { margin-top: 14px; }
.band { border-radius: var(--radius-lg); padding: 14px 18px; }
.band-label { display: flex; align-items: center; gap: 8px; font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 10px; }
.band.ai { background: linear-gradient(90deg, rgba(139, 92, 246, 0.16), rgba(99, 102, 241, 0.08)); border: 1px solid rgba(139, 92, 246, 0.35); }
.band.ai .band-label { color: #c4b5fd; }
.ai-items { display: flex; gap: 10px; }
.ai-chip { font-family: var(--font-mono); font-size: 13px; padding: 5px 12px; border-radius: 999px; background: rgba(139, 92, 246, 0.18); color: #ede9fe; border: 1px solid rgba(139, 92, 246, 0.4); }
.membrane { height: 26px; display: flex; align-items: center; }
.membrane span { width: 100%; height: 2px; background: repeating-linear-gradient(90deg, rgba(255,255,255,0.35) 0 6px, transparent 6px 12px); }
.band.det { background: rgba(20, 20, 31, 0.7); border: 1px solid var(--border-strong); }
.band.det .band-label { color: var(--muted); }
.phases { display: grid; grid-template-columns: 1fr 1.1fr 1.15fr; gap: 14px; }
.phase { border-radius: var(--radius); padding: 12px 14px; background: rgba(9, 9, 15, 0.6); border: 1px solid var(--border); opacity: 0.22; transform: translateY(6px); transition: opacity 500ms var(--ease), transform 500ms var(--ease), border-color 500ms; }
.phase.on { opacity: 1; transform: none; border-color: rgba(34, 197, 94, 0.28); }
.ph-head { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
.ph-n { width: 24px; height: 24px; border-radius: 7px; display: grid; place-items: center; font-size: 12px; background: var(--ok-soft); color: #86efac; border: 1px solid rgba(34, 197, 94, 0.4); }
.ph-t { font-weight: 600; font-size: 15px; line-height: 1.2; }
.ph-s { font-size: 11px; color: var(--faint); }
.gate { display: flex; gap: 10px; padding: 5px 0; border-top: 1px solid var(--border); }
.gi { flex: 0 0 auto; margin-top: 3px; font-size: 15px; color: #4ade80; }
.gn { font-size: 14px; font-weight: 600; line-height: 1.25; }
.gd { font-size: 11px; color: var(--muted); line-height: 1.4; margin-top: 1px; }
</style>
