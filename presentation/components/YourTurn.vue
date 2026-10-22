<script setup lang="ts">
withDefaults(defineProps<{ step?: number }>(), { step: 99 })

const apps = [
  { label: 'Kubernetes & Helm remediation', icon: 'i-lucide-ship-wheel', a: -90 },
  { label: 'CI/CD failure analysis', icon: 'i-lucide-workflow', a: -30 },
  { label: 'Dependency updates', icon: 'i-lucide-package-check', a: 30 },
  { label: 'Configuration validation', icon: 'i-lucide-file-check-2', a: 90 },
  { label: 'Documentation automation', icon: 'i-lucide-book-marked', a: 150 },
  { label: 'Infrastructure troubleshooting', icon: 'i-lucide-server-cog', a: 210 },
]
const pos = (a: number) => {
  const r = (a * Math.PI) / 180
  return { left: `${50 + Math.cos(r) * 40}%`, top: `${50 + Math.sin(r) * 40}%` }
}
</script>

<template>
  <div class="yt">
    <div class="orbit" :class="{ on: step >= 1 }">
      <svg viewBox="0 0 100 100" class="rings" aria-hidden="true">
        <circle cx="50" cy="50" r="40" />
        <circle cx="50" cy="50" r="24" class="inner" />
      </svg>
      <div class="core">
        <div class="mono k">one event</div>
        <div class="mono v">+ one skill</div>
        <div class="mono v">+ one gate</div>
      </div>
      <div v-for="(a, i) in apps" :key="a.label" class="app" :style="{ ...pos(a.a), transitionDelay: `${i * 70}ms` }">
        <div :class="a.icon" class="ico" />
        <span>{{ a.label }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.yt { height: 100%; display: grid; place-items: center; }
.orbit { position: relative; width: 480px; height: 480px; }
.rings { position: absolute; inset: 0; width: 100%; height: 100%; }
.rings circle { fill: none; stroke: rgba(139, 92, 246, 0.25); stroke-width: 0.25; stroke-dasharray: 1 1.5; }
.rings .inner { stroke: rgba(99, 102, 241, 0.3); animation: spin 60s linear infinite; transform-origin: 50% 50%; }
@keyframes spin { to { transform: rotate(360deg); } }
.core {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
  width: 150px; height: 150px; border-radius: 50%; display: grid; place-content: center; text-align: center; gap: 2px;
  background: radial-gradient(circle at 50% 35%, rgba(139, 92, 246, 0.35), rgba(20, 20, 31, 0.95) 70%);
  border: 1px solid rgba(139, 92, 246, 0.5); box-shadow: 0 0 60px rgba(139, 92, 246, 0.35);
}
.core .k { font-size: 15px; color: #fff; font-weight: 700; }
.core .v { font-size: 12px; color: #c4b5fd; }
.app {
  position: absolute; transform: translate(-50%, -50%) scale(0.9);
  display: flex; align-items: center; gap: 8px; white-space: nowrap;
  padding: 8px 14px; border-radius: 999px; font-size: 14px;
  background: rgba(20, 20, 31, 0.92); border: 1px solid var(--border-strong);
  opacity: 0; transition: opacity 500ms var(--ease), transform 500ms var(--ease);
}
.orbit.on .app { opacity: 1; transform: translate(-50%, -50%) scale(1); }
.app .ico { color: #a78bfa; font-size: 16px; }
</style>
