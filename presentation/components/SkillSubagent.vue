<script setup lang="ts">
withDefaults(defineProps<{ step?: number }>(), { step: 99 })
</script>

<template>
  <div class="ss">
    <!-- Skill -->
    <section class="side skill" :class="{ on: step >= 1 }">
      <header>
        <div class="ico"><div class="i-lucide-book-open-text" /></div>
        <div>
          <div class="kind mono">skill</div>
          <h3>Reusable knowledge</h3>
        </div>
      </header>
      <ul class="facts">
        <li><span class="mono">description</span> always visible → body loaded <b>only when used</b></li>
        <li>Runs <b>inside the context that loads it</b></li>
        <li><span class="mono">allowed-tools</span> pre-approves; it is not a sandbox</li>
      </ul>
      <div class="code"><slot name="skill" /></div>
    </section>

    <!-- Relationship -->
    <div class="bridge" aria-hidden="true">
      <div class="ctx">
        <div class="mono lbl">main context</div>
        <div class="stack">
          <span class="layer">system prompt</span>
          <span class="layer lit" :class="{ on: step >= 1 }">＋ skill instructions</span>
          <span class="layer">conversation</span>
        </div>
      </div>
      <div class="arrow left" :class="{ on: step >= 1 }"><span>loads into</span></div>
      <div class="arrow right" :class="{ on: step >= 2 }"><span>delegates to</span></div>
      <div class="ret mono" :class="{ on: step >= 2 }">← only the result returns</div>
    </div>

    <!-- Subagent -->
    <section class="side agent" :class="{ on: step >= 2 }">
      <header>
        <div class="ico"><div class="i-lucide-bot" /></div>
        <div>
          <div class="kind mono">subagent</div>
          <h3>Delegated execution</h3>
        </div>
      </header>
      <ul class="facts">
        <li><b>Own context window</b> and system prompt</li>
        <li><span class="mono">tools</span> allowlist — its own permissions</li>
        <li>Starts fresh: sees the task brief, not your history</li>
      </ul>
      <div class="code"><slot name="agent" /></div>
    </section>
  </div>
</template>

<style scoped>
.ss { display: grid; grid-template-columns: 1fr 200px 1fr; gap: 18px; margin-top: 18px; align-items: stretch; }
.side {
  padding: 18px 20px; border-radius: var(--radius-lg); border: 1px solid var(--border);
  background: rgba(20, 20, 31, 0.7); opacity: 0.32; transition: opacity 500ms var(--ease), border-color 500ms, box-shadow 500ms;
  display: flex; flex-direction: column; min-width: 0;
}
.side.on { opacity: 1; }
.skill.on { border-color: rgba(99, 102, 241, 0.45); box-shadow: 0 20px 60px -30px rgba(99, 102, 241, 0.5); }
.agent.on { border-color: rgba(139, 92, 246, 0.5); box-shadow: 0 20px 60px -30px rgba(139, 92, 246, 0.55); }
header { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; }
.ico { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-size: 20px; }
.skill .ico { background: var(--indigo-soft); color: #a5b4fc; }
.agent .ico { background: var(--violet-soft); color: #c4b5fd; }
.kind { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--faint); }
h3 { margin: 0 !important; font-size: 20px !important; }
.facts { list-style: none; padding: 0; margin: 0 0 12px; display: grid; gap: 5px; font-size: 14.5px; color: var(--muted); line-height: 1.4; }
.facts li { padding-left: 16px; position: relative; }
.facts li::before { content: ''; position: absolute; left: 0; top: 9px; width: 6px; height: 6px; border-radius: 2px; background: currentColor; opacity: 0.5; }
.facts b { color: var(--text); font-weight: 600; }
.facts .mono { font-size: 12.5px; color: #c4b5fd; }
.code { margin-top: auto; }
.code :deep(pre.shiki), .code :deep(.slidev-code) { font-size: 12.5px !important; line-height: 1.55 !important; padding: 12px 14px !important; }

.bridge { position: relative; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 16px; }
.ctx { width: 100%; padding: 12px; border-radius: 14px; border: 1px solid var(--border-strong); background: var(--surface); text-align: center; }
.ctx .lbl { font-size: 11px; color: var(--faint); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
.stack { display: grid; gap: 5px; }
.layer { font-family: var(--font-mono); font-size: 11.5px; padding: 5px 6px; border-radius: 7px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border); color: var(--muted); }
.layer.lit { opacity: 0.25; transition: all 500ms var(--ease); }
.layer.lit.on { opacity: 1; color: #c7d2fe; border-color: rgba(99, 102, 241, 0.55); background: var(--indigo-soft); }
.arrow { width: 100%; font-family: var(--font-mono); font-size: 11.5px; color: var(--faint); text-align: center; position: relative; opacity: 0.25; transition: opacity 500ms; }
.arrow.on { opacity: 1; }
.arrow::after { content: ''; display: block; height: 1px; margin-top: 6px; }
.arrow.left::after { background: linear-gradient(270deg, transparent, #6366f1); }
.arrow.left span { color: #a5b4fc; }
.arrow.right::after { background: linear-gradient(90deg, transparent, #8b5cf6); }
.arrow.right span { color: #c4b5fd; }
.ret { font-size: 11px; color: var(--faint); opacity: 0; transition: opacity 500ms; }
.ret.on { opacity: 1; }
</style>
