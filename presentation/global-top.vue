<script setup lang="ts">
import { computed } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const { currentPage, total } = useNav()
// In export each slide renders its own layer copy with $page; in play mode fall back to nav.
const { $page } = useSlideContext()
const page = computed(() => $page?.value || currentPage.value)

const chapters = [
  { n: '01', name: 'Workflow', from: 1, to: 5 },
  { n: '02', name: 'Написання skill', from: 6, to: 12 },
  { n: '03', name: 'Сабагенти', from: 13, to: 18 },
  { n: '04', name: 'Практика наживо', from: 19, to: 25 },
]
const bare = new Set([1])

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
