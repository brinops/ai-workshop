<script setup lang="ts">
// Ambient background for the title slide: the workshop workflow drawn as a
// quiet node graph. A single pulse travels the loop; nothing here needs clicks.
const nodes = [
  { id: 'pr', x: 140, y: 470, label: 'Jira', tone: 'neutral' },
  { id: 'ci', x: 330, y: 330, label: 'Slack', tone: 'neutral' },
  { id: 'hook', x: 470, y: 560, label: 'Triage', tone: 'neutral' },
  { id: 'skill', x: 620, y: 380, label: 'Skill', tone: 'violet' },
  { id: 'agent', x: 800, y: 520, label: 'Action', tone: 'violet' },
  { id: 'gate', x: 960, y: 340, label: 'Схвалення', tone: 'indigo' },
  { id: 'ok', x: 1130, y: 470, label: 'Jira ✓', tone: 'ok' },
]
const path = 'M140 470 C 220 400, 260 330, 330 330 S 420 560, 470 560 S 560 380, 620 380 S 740 520, 800 520 S 900 340, 960 340 S 1070 470, 1130 470'
</script>

<template>
  <div class="hero-flow" aria-hidden="true">
    <div class="aurora" />
    <svg viewBox="0 0 1280 720" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="hf-line" x1="0" x2="1">
          <stop offset="0" stop-color="#ef4444" stop-opacity="0.5" />
          <stop offset="0.45" stop-color="#8b5cf6" stop-opacity="0.8" />
          <stop offset="1" stop-color="#22c55e" stop-opacity="0.7" />
        </linearGradient>
        <filter id="hf-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
      </defs>
      <path :d="path" fill="none" stroke="url(#hf-line)" stroke-width="1.5" opacity="0.55" />
      <path :d="path" fill="none" stroke="url(#hf-line)" stroke-width="1.5" class="dash" />
      <circle r="5" fill="#c4b5fd" class="pulse-dot">
        <animateMotion dur="9s" repeatCount="indefinite" :path="path" />
      </circle>
      <circle r="14" fill="#8b5cf6" filter="url(#hf-glow)" opacity="0.6" class="pulse-dot">
        <animateMotion dur="9s" repeatCount="indefinite" :path="path" />
      </circle>
      <g v-for="n in nodes" :key="n.id" :class="['node', n.tone]">
        <circle :cx="n.x" :cy="n.y" r="26" class="halo" />
        <circle :cx="n.x" :cy="n.y" r="6" class="core" />
        <text :x="n.x" :y="n.y + 46" text-anchor="middle">{{ n.label }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.hero-flow { position: absolute; inset: 0; overflow: hidden; }
.aurora {
  position: absolute;
  inset: -20%;
  background:
    radial-gradient(40% 35% at 30% 30%, rgba(99, 102, 241, 0.22), transparent 70%),
    radial-gradient(35% 30% at 75% 65%, rgba(139, 92, 246, 0.2), transparent 70%);
  animation: drift 22s ease-in-out infinite alternate;
  filter: blur(10px);
}
@keyframes drift {
  from { transform: translate3d(-3%, -2%, 0) rotate(0deg); }
  to { transform: translate3d(3%, 2%, 0) rotate(8deg); }
}
svg { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0.85; mask-image: linear-gradient(100deg, rgba(0, 0, 0, 0.18) 0%, rgba(0, 0, 0, 0.3) 45%, #000 75%); }
.dash { stroke-dasharray: 2 10; animation: dash-flow 1.6s linear infinite; opacity: 0.9; }
.node .halo { fill: rgba(255, 255, 255, 0.02); stroke: rgba(255, 255, 255, 0.12); }
.node .core { fill: #9ca3af; }
.node text { font-family: var(--font-mono); font-size: 13px; fill: #6b7280; letter-spacing: 0.06em; }
.node.fail .core { fill: #ef4444; }
.node.fail .halo { stroke: rgba(239, 68, 68, 0.45); }
.node.violet .core { fill: #8b5cf6; }
.node.violet .halo { stroke: rgba(139, 92, 246, 0.45); }
.node.indigo .core { fill: #6366f1; }
.node.indigo .halo { stroke: rgba(99, 102, 241, 0.45); }
.node.ok .core { fill: #22c55e; }
.node.ok .halo { stroke: rgba(34, 197, 94, 0.5); }
@media (prefers-reduced-motion: reduce) {
  .pulse-dot { display: none; }
  .aurora { animation: none; }
}
</style>
