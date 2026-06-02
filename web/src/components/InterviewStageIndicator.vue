<template>
  <div class="stage-indicator">
    <div class="stage-indicator__header">
      <Target :size="14" />
      <span>面试阶段</span>
      <span class="stage-badge">{{ currentStage }}/6</span>
    </div>
    <div class="stage-indicator__track">
      <template v-for="(stage, idx) in stages" :key="idx">
        <div
          class="stage-pill"
          :class="`stage-pill--${stage.status}`"
          :title="stage.fullLabel"
        >
          <div class="stage-pill__icon">
            <CheckCircle v-if="stage.status === 'completed'" :size="16" />
            <LoaderCircle v-else-if="stage.status === 'in_progress'" :size="16" class="spinning" />
            <span v-else class="stage-pill__num">{{ idx + 1 }}</span>
          </div>
          <span class="stage-pill__label">{{ stage.shortLabel }}</span>
        </div>
        <div v-if="idx < stages.length - 1" class="stage-connector" :class="`stage-connector--${stage.status}`" />
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CheckCircle, LoaderCircle, Target } from 'lucide-vue-next'

const props = defineProps({
  agentState: { type: Object, default: null }
})

const STAGE_LABELS = [
  { full: '发起开场并请候选人自我介绍', short: '开场介绍' },
  { full: '追问项目经历与技术细节', short: '项目经历' },
  { full: '相关技术知识提问', short: '技术提问' },
  { full: '代码考核', short: '编程考核' },
  { full: '评估岗位匹配度与风险点', short: '匹配评估' },
  { full: '输出总结与评分卡', short: '总结评分' }
]

const stages = computed(() => {
  const todos = props.agentState?.todos
  return STAGE_LABELS.map((label, idx) => {
    const todo = (Array.isArray(todos) && idx < todos.length) ? todos[idx] : null
    return {
      status: todo?.status || 'pending',
      shortLabel: label.short,
      fullLabel: label.full
    }
  })
})

const currentStage = computed(() => {
  const inProgressIdx = stages.value.findIndex(s => s.status === 'in_progress')
  return inProgressIdx >= 0 ? inProgressIdx + 1 : Math.max(1, stages.value.filter(s => s.status === 'completed').length + 1)
})
</script>

<style lang="less" scoped>
.stage-indicator {
  padding: 12px 20px;
  background: linear-gradient(135deg, #f8fafc, #f1f5f9);
  border-bottom: 1px solid #e2e8f0;
  user-select: none;

  &__header {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #64748b;
    margin-bottom: 10px;

    .stage-badge {
      margin-left: auto;
      background: #1976d2;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 10px;
      border-radius: 10px;
    }
  }

  &__track {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0;
  }
}

.stage-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  background: #fff;
  border: 2px solid #e2e8f0;
  transition: all 0.3s ease;
  white-space: nowrap;

  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  &__num { font-size: 12px; font-weight: 700; }

  &__label {
    font-size: 13px;
    font-weight: 500;
    transition: color 0.3s ease;
  }

  &--completed {
    border-color: #a5d6a7;
    background: #f1f8e9;
    .stage-pill__icon { color: #43a047; }
    .stage-pill__label { color: #2e7d32; }
  }

  &--in_progress {
    border-color: #90caf9;
    background: #e3f2fd;
    box-shadow: 0 0 8px rgba(25, 118, 210, 0.25);
    .stage-pill__icon { color: #1976d2; }
    .stage-pill__label { color: #1565c0; font-weight: 700; }
  }

  &--pending {
    border-color: #e2e8f0;
    background: #fff;
    .stage-pill__icon { color: #94a3b8; }
    .stage-pill__label { color: #94a3b8; }
  }
}

.stage-connector {
  width: 24px;
  height: 2px;
  flex-shrink: 0;
  background: #e2e8f0;
  transition: background 0.3s ease;

  &--completed { background: #a5d6a7; }
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
