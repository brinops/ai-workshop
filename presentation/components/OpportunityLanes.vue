<script setup lang="ts">
withDefaults(defineProps<{ step?: number }>(), { step: 99 })
</script>

<template>
  <div class="lanes">
    <!-- Lane 1: CI only -->
    <div class="lane before">
      <div class="lane-head mono">today · CI only</div>
      <div class="track">
        <div class="chip neutral">push</div>
        <div class="wire" />
        <div class="chip fail"><div class="i-lucide-x" />helm-validate</div>
        <div class="wire dim" />
        <div class="void">
          <div class="i-lucide-user-round-search" />
          <span>a human opens the raw job log</span>
        </div>
      </div>
    </div>

    <!-- Lane 2: with agents + validation -->
    <div class="lane after">
      <div class="lane-head mono">with agents · deterministic gate</div>
      <div class="track">
        <div class="chip neutral">push</div>
        <div class="wire" />
        <div class="chip fail" :class="{ lit: step === 1 }"><div class="i-lucide-x" />helm-validate</div>
        <div class="wire" :class="{ on: step >= 2 }" />
        <div class="chip violet" :class="{ on: step >= 2, lit: step === 2 }"><div class="i-lucide-sparkles" />diagnose</div>
        <div class="wire" :class="{ on: step >= 2 }" />
        <div class="chip violet" :class="{ on: step >= 2 }"><div class="i-lucide-wrench" />fix</div>
        <div class="wire" :class="{ on: step >= 3 }" />
        <div class="chip gate" :class="{ on: step >= 3, lit: step === 3 }"><div class="i-lucide-shield-check" />validate</div>
        <div class="wire" :class="{ on: step >= 3 }" />
        <div class="chip ok" :class="{ on: step >= 3 }"><div class="i-lucide-check" />CI on new SHA</div>
      </div>
    </div>

    <!-- Thesis -->
    <div class="thesis">
      <div class="t" :class="{ on: step >= 1 }"><span class="k fail">CI</span> tells us <em>what</em> failed.</div>
      <div class="t" :class="{ on: step >= 2 }"><span class="k violet">Agents</span> can investigate <em>why</em>.</div>
      <div class="t" :class="{ on: step >= 3 }"><span class="k ok">Validation</span> determines whether the fix is <em>acceptable</em>.</div>
    </div>
  </div>
</template>

<style scoped>
.lanes { display: grid; gap: 18px; margin-top: 26px; }
.lane { padding: 18px 22px; border-radius: var(--radius-lg); border: 1px solid var(--border); background: rgba(20, 20, 31, 0.6); }
.lane.after { border-color: rgba(139, 92, 246, 0.28); background: linear-gradient(90deg, rgba(139, 92, 246, 0.06), rgba(20, 20, 31, 0.6) 60%); }
.lane-head { font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); margin-bottom: 12px; }
.after .lane-head { color: #a78bfa; }
.track { display: flex; align-items: center; }
.chip {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 14px; border-radius: 10px;
  font-family: var(--font-mono); font-size: 14px; white-space: nowrap;
  border: 1px solid var(--border-strong); background: var(--surface-2); color: var(--text);
  transition: opacity 500ms var(--ease), transform 500ms var(--ease), box-shadow 500ms;
}
.chip.fail { border-color: rgba(239, 68, 68, 0.5); color: #fca5a5; background: var(--fail-soft); }
.chip.violet, .chip.gate, .chip.ok { opacity: 0.18; transform: translateY(4px); }
.chip.on { opacity: 1; transform: none; }
.chip.violet { border-color: rgba(139, 92, 246, 0.5); color: #ddd6fe; background: var(--violet-soft); }
.chip.gate { border-color: rgba(99, 102, 241, 0.6); color: #c7d2fe; background: var(--indigo-soft); }
.chip.ok { border-color: rgba(34, 197, 94, 0.5); color: #86efac; background: var(--ok-soft); }
.chip.lit.fail { box-shadow: var(--glow-fail); }
.chip.lit.violet { box-shadow: var(--glow-violet); }
.chip.lit.gate { box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.6), 0 0 30px rgba(99, 102, 241, 0.35); }
.wire { flex: 1; min-width: 18px; height: 1px; background: var(--border-strong); }
.after .wire { background: rgba(255, 255, 255, 0.08); transition: background 500ms; }
.after .wire.on { background: linear-gradient(90deg, #8b5cf6, #6366f1); }
.wire.dim { background: repeating-linear-gradient(90deg, rgba(255,255,255,.18) 0 4px, transparent 4px 9px); }
.void {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 9px 16px; border-radius: 10px; border: 1px dashed rgba(245, 158, 11, 0.45);
  color: #fcd34d; font-size: 15px;
}
.thesis { margin-top: 18px; display: grid; gap: 8px; }
.t { font-size: 30px; font-weight: 600; letter-spacing: -0.025em; line-height: 1.25; opacity: 0.14; transition: opacity 600ms var(--ease); }
.t.on { opacity: 1; }
.t em { font-style: normal; color: var(--muted); }
.k.fail { color: #f87171; }
.k.violet { color: #a78bfa; }
.k.ok { color: #4ade80; }
</style>
