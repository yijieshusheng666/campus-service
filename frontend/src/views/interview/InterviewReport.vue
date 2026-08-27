<template>
  <div v-if="report" class="page">
    <div class="page-header">
      <h2>面试评估报告 · {{ detail.job_position }}</h2>
      <el-button @click="$router.push({ name: 'InterviewList' })">返回列表</el-button>
    </div>

    <el-card class="score-card">
      <div class="overall">
        <div class="number">{{ report.overall_score }}</div>
        <div class="label">综合得分 / 100</div>
      </div>
    </el-card>

    <el-card class="section">
      <template #header>维度评分</template>
      <div v-for="d in report.dimensions" :key="d.name" class="dim">
        <span class="dim-name">{{ d.name }}</span>
        <el-progress :percentage="d.score" :stroke-width="12" style="flex: 1; margin: 0 16px" />
        <span class="dim-score">{{ d.score }}</span>
      </div>
      <div v-for="d in report.dimensions" :key="'c' + d.name" class="dim-comment">
        {{ d.name }}：{{ d.comment }}
      </div>
    </el-card>

    <div class="grid">
      <el-card class="section">
        <template #header>优势</template>
        <ul><li v-for="s in report.strengths" :key="s">{{ s }}</li></ul>
      </el-card>
      <el-card class="section">
        <template #header>短板</template>
        <ul><li v-for="w in report.weaknesses" :key="w">{{ w }}</li></ul>
      </el-card>
    </div>

    <el-card class="section">
      <template #header>改进建议</template>
      <ol><li v-for="s in report.suggestions" :key="s">{{ s }}</li></ol>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getInterview } from '@/api/interview'

const route = useRoute()
const detail = ref({})
const report = ref(null)

onMounted(async () => {
  const res = await getInterview(route.params.id)
  detail.value = res.data
  report.value = res.data.report
})
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 18px; }
.score-card { text-align: center; margin-bottom: 16px; }
.overall .number { font-size: 48px; font-weight: 700; color: var(--el-color-primary); }
.overall .label { color: var(--el-text-color-secondary); }
.section { margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.dim { display: flex; align-items: center; margin-bottom: 8px; }
.dim-name { width: 110px; flex-shrink: 0; }
.dim-score { width: 36px; text-align: right; flex-shrink: 0; }
.dim-comment { color: var(--el-text-color-secondary); font-size: 13px; margin-bottom: 4px; }
ul, ol { padding-left: 20px; line-height: 1.8; margin: 0; }
@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
