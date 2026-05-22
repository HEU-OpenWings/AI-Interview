<template>
  <div class="adaptive-trajectory">
    <div class="trajectory-header">
      <span class="trajectory-title">自适应难度轨迹</span>
      <span class="trajectory-hint">纵轴为当前能力估计 θ，点的大小为题目难度</span>
    </div>
    <div ref="chartEl" class="trajectory-chart" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watchEffect } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  // Array of theta values: [initial, after_q1, after_q2, ...]
  trajectory: { type: Array, default: () => [] },
  // Array of question objects with { concept, difficulty }
  questions: { type: Array, default: () => [] },
})

const chartEl = ref(null)
let chart = null

function buildOption() {
  const labels = ['起始', ...props.questions.map((q, i) => `Q${i + 1}: ${q.concept ?? ''}`)]
  const values = props.trajectory.map((v, i) => ({
    value: v,
    symbolSize: i === 0 ? 8 : Math.round((props.questions[i - 1]?.difficulty ?? 0.5) * 24) + 4,
  }))

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        const qIdx = p.dataIndex - 1
        const q = props.questions[qIdx]
        const diffText = q ? `难度 ${q.difficulty}` : '初始值'
        return `${p.name}<br/>θ = ${p.value}<br/>${diffText}`
      },
    },
    grid: { left: 48, right: 16, top: 16, bottom: 40 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 11, rotate: props.questions.length > 5 ? 20 : 0 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      name: 'θ',
      nameTextStyle: { fontSize: 11 },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series: [
      {
        type: 'line',
        data: values,
        smooth: 0.4,
        lineStyle: { width: 2, color: '#1677ff' },
        itemStyle: { color: '#1677ff' },
        markLine: {
          silent: true,
          data: [{ yAxis: 0.5, lineStyle: { type: 'dashed', color: '#aaa' } }],
          label: { formatter: '平均水平' },
        },
      },
    ],
  }
}

onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  watchEffect(() => {
    chart?.setOption(buildOption(), { notMerge: true })
  })
  window.addEventListener('resize', () => chart?.resize())
})

onUnmounted(() => {
  window.removeEventListener('resize', () => chart?.resize())
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.adaptive-trajectory {
  width: 100%;
}

.trajectory-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}

.trajectory-title {
  font-weight: 600;
  font-size: 13px;
}

.trajectory-hint {
  font-size: 11px;
  color: var(--color-text-tertiary, #999);
}

.trajectory-chart {
  height: 200px;
  width: 100%;
}
</style>
