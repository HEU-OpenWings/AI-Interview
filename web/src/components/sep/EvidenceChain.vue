<template>
  <div class="evidence-chain">
    <div v-if="!items.length" class="evidence-empty">暂无证据条目</div>

    <div
      v-for="(item, idx) in items"
      :key="`${item.concept}-${idx}`"
      class="evidence-item"
    >
      <div class="evidence-header">
        <div class="evidence-header-left">
          <span class="evidence-concept">{{ item.concept }}</span>
          <a-tag color="default" size="small">{{ dimensionLabel(item.dimension) }}</a-tag>
        </div>
        <span
          :class="['evidence-delta', item.score_delta >= 0 ? 'positive' : 'negative']"
        >
          {{ item.score_delta >= 0 ? '+' : '' }}{{ item.score_delta }}
        </span>
      </div>

      <div class="evidence-text">{{ item.evidence_text }}</div>

      <div class="evidence-question">
        <span class="evidence-question-label">题目：</span>{{ item.question }}
      </div>
    </div>
  </div>
</template>

<script setup>
const DIMENSION_LABELS = {
  technical_competence: '技术能力',
  problem_solving: '问题解决',
  communication: '沟通表达',
  soft_skills: '综合素质',
}

defineProps({
  items: { type: Array, default: () => [] },
})

function dimensionLabel(key) {
  return DIMENSION_LABELS[key] ?? key
}
</script>

<style scoped>
.evidence-chain {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.evidence-empty {
  color: var(--color-text-tertiary, #999);
  font-size: 13px;
  padding: 12px 0;
}

.evidence-item {
  border: 1px solid var(--color-border, #e8e8e8);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--color-bg-base, #fff);
  transition: border-color 0.2s;
}

.evidence-item:hover {
  border-color: var(--color-primary, #1677ff);
}

.evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.evidence-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.evidence-concept {
  font-weight: 600;
  font-size: 13px;
}

.evidence-delta {
  font-weight: 700;
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}

.evidence-delta.positive {
  color: #52c41a;
}

.evidence-delta.negative {
  color: #ff4d4f;
}

.evidence-text {
  font-size: 13px;
  color: var(--color-text-secondary, #555);
  margin-bottom: 6px;
  line-height: 1.5;
}

.evidence-question {
  font-size: 12px;
  color: var(--color-text-tertiary, #999);
}

.evidence-question-label {
  font-weight: 500;
}
</style>
