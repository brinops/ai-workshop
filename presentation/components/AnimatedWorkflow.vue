<script setup lang="ts">
interface Step {
  label: string
  sub: string
  icon: string
  tone?: 'human'
}

defineProps<{ steps: Step[] }>()
</script>

<template>
  <ol class="workflow">
    <li v-for="step in steps" :key="step.label" class="node" :class="step.tone">
      <div class="icon" :class="step.icon" aria-hidden="true" />
      <div class="label">{{ step.label }}</div>
      <div class="description">{{ step.sub }}</div>
    </li>
  </ol>
</template>

<style scoped>
.workflow {
  display: flex;
  gap: 24px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.node {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  padding: 12px 14px;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
.node + .node::before {
  content: '';
  position: absolute;
  top: 50%;
  right: 100%;
  width: 24px;
  height: 1px;
  background: var(--violet);
  opacity: 0.65;
}
.node.human { border-color: rgba(245, 158, 11, 0.35); }
.icon { margin-bottom: 5px; font-size: 21px; color: #c4b5fd; }
.human .icon { color: #fbbf24; }
.label { font-size: 20px; font-weight: 600; }
.description { margin-top: 4px; color: var(--muted); font-size: 16px; line-height: 1.35; }
</style>
