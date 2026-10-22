<script setup lang="ts">
// Numbered legend that follows the slide's click index (e.g. code line highlights).
withDefaults(defineProps<{
  items: { title: string; text: string }[]
  step?: number
  /** click index of the first item */
  offset?: number
}>(), { step: 0, offset: 1 })
</script>

<template>
  <ol class="sl">
    <li v-for="(it, i) in items" :key="it.title" :class="{ on: step === i + offset, past: step > i + offset }">
      <span class="n mono">{{ i + 1 }}</span>
      <div>
        <div class="t">{{ it.title }}</div>
        <div class="x">{{ it.text }}</div>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.sl { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
li { display: flex; gap: 12px; padding: 5px 10px; border-radius: 10px; border: 1px solid transparent; opacity: 0.45; transition: all 350ms var(--ease); }
li.past { opacity: 0.75; }
li.on { opacity: 1; border-color: rgba(139, 92, 246, 0.45); background: var(--violet-soft); }
.n { flex: 0 0 auto; width: 22px; height: 22px; border-radius: 7px; display: grid; place-items: center; font-size: 11px; color: #c4b5fd; border: 1px solid rgba(139, 92, 246, 0.4); margin-top: 1px; }
.t { font-weight: 600; font-size: 14px; line-height: 1.3; }
.x { font-size: 12.5px; color: var(--muted); line-height: 1.4; }
</style>
