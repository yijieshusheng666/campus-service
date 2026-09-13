<template>
  <div v-if="report" class="page">
    <div class="page-header">
      <h2>面试评估报告 · {{ detail.job_position }}</h2>
      <el-button @click="$router.push({ name: 'InterviewList' })">返回列表</el-button>
    </div>

    <!-- 教练式报告（新结构） -->
    <template v-if="isCoachReport">
      <el-card class="score-card">
        <div class="overall">
          <div class="number">{{ report.overall_score }}</div>
          <div class="label">综合得分 / 100（参考值）</div>
        </div>
        <el-tag v-if="conclusion" :type="conclusion.type" size="large" effect="dark" class="hire-tag">
          {{ conclusion.label }}
        </el-tag>
        <el-tag v-else-if="hireSignal.label" :type="hireSignal.type" size="large" effect="dark" class="hire-tag">
          {{ hireSignal.label }}
        </el-tag>
        <div v-if="report.summary" class="report-summary">{{ report.summary }}</div>
      </el-card>

      <el-card v-if="report.red_flags?.length" class="section red-flag-card">
        <template #header>红线检查（触发任一项，结论不得为「过」）</template>
        <ul class="red-flags">
          <li v-for="(f, i) in report.red_flags" :key="i">{{ f }}</li>
        </ul>
      </el-card>

      <el-card class="section">
        <template #header>五维评分（按行为锚点定档：1=答非所问 / 3=有结论无依据 / 5=结论+依据+适用边界）</template>
        <div v-for="d in report.dimensions" :key="d.name" class="dim">
          <span class="dim-name">{{ dimLabel(d.name) }}</span>
          <el-progress :percentage="(d.score || 0) * 20" :stroke-width="12" style="flex: 1; margin: 0 16px" />
          <span class="dim-score">{{ d.score }}/5</span>
        </div>
        <div v-for="d in report.dimensions" :key="'c' + d.name" class="dim-comment">
          <b>{{ dimLabel(d.name) }}：{{ d.score }}/5</b> — {{ d.comment }}
        </div>
      </el-card>

      <el-card class="section">
        <template #header>逐题复盘</template>
        <div v-for="q in report.per_question" :key="q.index" class="pq">
          <div class="pq-head">
            <span class="pq-index">Q{{ q.index }}</span>
            <span class="pq-question">{{ q.question }}</span>
          </div>
          <div class="pq-scores">
            <el-tag
              v-for="dim in dimOrder"
              :key="dim"
              size="small"
              :type="scoreTagType((q.scores || {})[dim])"
              effect="plain"
            >{{ dimLabel(dim) }} {{ (q.scores || {})[dim] ?? '-' }}</el-tag>
          </div>
          <div v-if="q.strongest" class="pq-strong">👍 {{ q.strongest }}</div>
          <div v-if="q.missed" class="pq-missed">⚠ {{ q.missed }}</div>
        </div>
        <el-empty v-if="!report.per_question?.length" description="本场没有候选人回答记录" :image-size="60" />
      </el-card>

      <el-card class="section">
        <template #header>整体模式（全场才看得见的问题）</template>
        <div v-if="patterns.crutch_phrases?.length" class="pattern-row">
          <span class="pattern-label">口头禅/套路：</span>
          <el-tag v-for="p in patterns.crutch_phrases" :key="p" size="small" type="warning" effect="plain" class="pattern-tag">{{ p }}</el-tag>
        </div>
        <div v-if="patterns.avoided_topics?.length" class="pattern-row">
          <span class="pattern-label">回避话题：</span>
          <el-tag v-for="t in patterns.avoided_topics" :key="t" size="small" type="info" effect="plain" class="pattern-tag">{{ t }}</el-tag>
        </div>
        <div v-if="patterns.best_moment" class="pattern-block best">🏆 全场最佳：{{ patterns.best_moment }}</div>
        <div v-if="patterns.worst_moment" class="pattern-block worst">💔 最弱时刻：{{ patterns.worst_moment }}</div>
      </el-card>

      <el-card class="section">
        <template #header>下一场最该改的 3 件事</template>
        <ol class="top-changes"><li v-for="(c, i) in report.top_changes" :key="i">{{ c }}</li></ol>
      </el-card>
    </template>

    <!-- 旧版报告（历史数据兼容） -->
    <template v-else>
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
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getInterview } from '@/api/interview'

const route = useRoute()
const detail = ref({})
const report = ref(null)

const dimOrder = ['substance', 'structure', 'relevance', 'credibility', 'differentiation']
const dimNames = {
  substance: '实质证据',
  structure: '叙事结构',
  relevance: '切题聚焦',
  credibility: '可信度',
  differentiation: '差异化',
}
const dimLabel = (name) => dimNames[name] || name

const hireSignalMap = {
  strong_hire: { label: '强推荐', type: 'success' },
  hire: { label: '推荐', type: 'primary' },
  mixed: { label: '存疑', type: 'warning' },
  no_hire: { label: '不推荐', type: 'danger' },
}
const hireSignal = computed(() => hireSignalMap[report.value?.hire_signal] || { label: '', type: 'info' })

// 结论三档：比 hire_signal 更克制，是报告的主要定性判断（旧报告无此字段则回退展示 hire_signal）
const conclusionMap = {
  pass: { label: '结论：过', type: 'success' },
  pending: { label: '结论：待定', type: 'warning' },
  fail: { label: '结论：挂', type: 'danger' },
}
const conclusion = computed(() => conclusionMap[report.value?.conclusion] || null)

const isCoachReport = computed(() => {
  const r = report.value
  return !!(r && (r.per_question?.length || r.hire_signal || r.conclusion))
})

const patterns = computed(() => report.value?.patterns || {})

const scoreTagType = (score) => {
  if (score >= 4) return 'success'
  if (score === 3) return 'warning'
  if (score >= 1) return 'danger'
  return 'info'
}

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
.hire-tag { margin-top: 10px; }
.report-summary { margin-top: 12px; color: var(--el-text-color-regular); font-size: 14px; }
.section { margin-bottom: 16px; }
.red-flag-card { border-left: 3px solid var(--el-color-danger); }
.red-flags { color: var(--el-color-danger); }
.red-flags li { margin-bottom: 6px; line-height: 1.7; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.dim { display: flex; align-items: center; margin-bottom: 8px; }
.dim-name { width: 110px; flex-shrink: 0; }
.dim-score { width: 44px; text-align: right; flex-shrink: 0; }
.dim-comment { color: var(--el-text-color-secondary); font-size: 13px; margin-bottom: 6px; line-height: 1.6; }
.pq { padding: 12px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.pq:last-child { border-bottom: none; }
.pq-head { display: flex; gap: 8px; align-items: baseline; margin-bottom: 8px; }
.pq-index { font-weight: 700; color: var(--el-color-primary); flex-shrink: 0; }
.pq-question { font-size: 14px; color: var(--el-text-color-primary); }
.pq-scores { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.pq-strong { font-size: 13px; color: var(--el-color-success); line-height: 1.6; }
.pq-missed { margin-top: 4px; font-size: 13px; color: var(--el-color-warning); line-height: 1.6; }
.pattern-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.pattern-label { font-size: 13px; color: var(--el-text-color-secondary); flex-shrink: 0; }
.pattern-tag { margin-right: 4px; }
.pattern-block { font-size: 13.5px; line-height: 1.7; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
.pattern-block.best { background: #f0f9eb; color: #529b2e; }
.pattern-block.worst { background: #fdf6ec; color: #b88230; }
.top-changes li { margin-bottom: 10px; line-height: 1.7; }
ul, ol { padding-left: 20px; line-height: 1.8; margin: 0; }
@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
