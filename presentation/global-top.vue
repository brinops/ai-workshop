<script setup lang="ts">
import { computed } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const { currentPage, total } = useNav()
// In export each slide renders its own layer copy with $page; in play mode fall back to nav.
const { $page } = useSlideContext()
const page = computed(() => $page?.value || currentPage.value)

const chapters = [
  { n: '01', name: 'The Problem', from: 1, to: 3 },
  { n: '02', name: 'Claude Code Hooks', from: 4, to: 6 },
  { n: '03', name: 'Headless Agents & Skills', from: 7, to: 9 },
  { n: '04', name: 'Architecture & Guardrails', from: 10, to: 12 },
  { n: '05', name: 'Live Demo', from: 13, to: 14 },
  { n: '06', name: 'Build Your Own', from: 15, to: 16 },
]
// Slides that own the whole canvas and should not show the footer.
const bare = new Set([1, 14])

const current = computed(() => chapters.find(c => page.value >= c.from && page.value <= c.to))
</script>

<template>
  <footer v-if="!bare.has(page) && current" class="deck-footer">
    <div class="chapter">
      <span class="n">{{ current.n }}</span>
      <span class="name">{{ current.name }}</span>
    </div>
    <div class="segments" aria-hidden="true">
      <span
        v-for="c in chapters"
        :key="c.n"
        class="seg"
        :class="{ done: page > c.to, active: c === current }"
      />
    </div>
    <div class="page">{{ String(page).padStart(2, '0') }} / {{ total }}</div>
  </footer>
</template>

<style scoped>
.deck-footer {
  position: absolute;
  left: 72px;
  right: 72px;
  bottom: 22px;
  display: flex;
  align-items: center;
  gap: 24px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--faint);
  pointer-events: none;
}
.chapter { display: flex; gap: 10px; min-width: 260px; }
.chapter .n { color: var(--violet); }
.segments { flex: 1; display: flex; gap: 6px; }
.seg { flex: 1; height: 2px; border-radius: 2px; background: rgba(255, 255, 255, 0.07); transition: background 400ms; }
.seg.done { background: rgba(139, 92, 246, 0.35); }
.seg.active { background: var(--grad-accent); box-shadow: 0 0 10px rgba(139, 92, 246, 0.6); }
.page { min-width: 60px; text-align: right; }
</style>
