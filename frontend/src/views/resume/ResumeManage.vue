<template>
  <div class="resume-manage-page">
    <el-card class="mb-16">
      <template #header>
        <div class="card-header">
          <b>我的简历</b>
          <div class="header-actions">
            <el-upload :show-file-list="false" accept=".pdf" :before-upload="beforeUpload" :http-request="onUpload">
              <el-button type="primary" :loading="uploading">
                <el-icon style="margin-right:4px"><DocumentAdd /></el-icon>
                {{ uploading ? '解析中...' : '上传 PDF 简历' }}
              </el-button>
            </el-upload>
          </div>
        </div>
      </template>
      <p class="tips">上传 PDF 简历后，点击「AI 优化建议」获取针对简历内容的诊断与修改建议；建议保存在平台上，可随时查看。</p>
    </el-card>

    <el-empty v-if="!loading && !resumes.length" description="暂无简历，请先上传" />

    <div v-for="r in resumes" :key="r.id" class="resume-card-wrapper">
      <el-card class="resume-card mb-16" v-loading="deletingId === r.id">
        <div class="resume-header">
          <div>
            <div class="resume-title">
              {{ r.parsed_name || r.file_name }}
              <el-tag v-if="r.parsed_job_title" size="small" type="primary" class="ml-8">{{ r.parsed_job_title }}</el-tag>
              <el-tag v-if="adviceCount(r)" size="small" type="success" class="ml-8">
                {{ adviceCount(r) }} 条建议
              </el-tag>
              <el-tag v-if="r.parse_status === 'pending'" size="small" type="warning" class="ml-8">
                <el-icon class="is-loading" style="vertical-align:-2px;margin-right:2px"><Loading /></el-icon>
                AI 解析中
              </el-tag>
              <el-tag
                v-else-if="r.parse_status === 'failed'"
                size="small"
                type="danger"
                class="ml-8"
                style="cursor:pointer"
                @click="onReparse(r)"
              >解析失败，点击重试</el-tag>
            </div>
            <div class="text-muted">
              文件：{{ r.file_name }} · 上传于 {{ formatDate(r.created_at) }}
            </div>
          </div>
          <div class="resume-actions">
            <el-button v-if="r.pdf_url" plain @click="openPdf(r)">查看原PDF</el-button>
            <el-button type="primary" plain :disabled="r.parse_status !== 'completed'" :loading="advisingId === r.id" @click="openAdvice(r)">AI 优化建议</el-button>
            <el-button type="danger" plain @click="onDelete(r)">删除</el-button>
          </div>
        </div>

        <div v-if="r.suggestions" class="advice-toggle" @click="toggleExpand(r)">
          <span>{{ expandedId === r.id ? '收起优化建议 ▴' : '查看优化建议 ▾' }}</span>
        </div>
        <div v-if="r.suggestions && expandedId === r.id" class="advice-panel">
          <div class="advice-head">
            <span class="advice-score">{{ suggestions(r).overall_score }} 分</span>
            <span class="advice-summary">{{ suggestions(r).summary }}</span>
            <span class="advice-time">生成于 {{ formatDate(r.suggestions_at) }}</span>
          </div>
          <div v-if="suggestions(r).dimension_ratings?.length" class="dim-ratings">
            <el-tooltip
              v-for="d in suggestions(r).dimension_ratings"
              :key="d.name"
              :content="d.evidence"
              placement="top"
            >
              <el-tag size="small" :type="ratingTagType(d.rating)" effect="plain" class="dim-tag">
                {{ d.name }} · {{ d.rating }}
              </el-tag>
            </el-tooltip>
          </div>
          <div v-for="(it, idx) in suggestions(r).items" :key="idx" class="advice-item">
            <div class="advice-item-head">
              <el-tag size="small" effect="plain">{{ it.module }}</el-tag>
              <el-tag size="small" :type="priorityTagType(it.priority)">{{ priorityLabel(it.priority) }}</el-tag>
            </div>
            <div class="advice-issue">{{ it.issue }}</div>
            <div class="advice-advice">{{ it.advice }}</div>
          </div>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="adviceDialog" title="AI 优化建议" width="520px">
      <p class="tips">AI 只诊断不改写：给出哪里可以优化、具体怎么改。可粘贴目标岗位要求做定向分析；留空则通用诊断。</p>
      <el-input v-model="adviceJobReq" type="textarea" :rows="3" placeholder="岗位要求（可选）" class="mt-8" />
      <template #footer>
        <el-button @click="adviceDialog = false">取消</el-button>
        <el-button type="primary" :loading="advising" @click="doAdvice">生成建议</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentAdd } from '@element-plus/icons-vue'
import { uploadResume, myResumes, deleteResume, generateAdvice, reparseResume } from '@/api/resume'

const resumes = ref([])
const loading = ref(false)
const uploading = ref(false)
const deletingId = ref(null)

const adviceDialog = ref(false)
const adviceTarget = ref(null)
const adviceJobReq = ref('')
const advising = ref(false)
const advisingId = ref(null)
const expandedId = ref(null)

const suggestions = (r) => r.suggestions || { overall_score: 0, summary: '', items: [] }
const adviceCount = (r) => suggestions(r).items?.length || 0

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const priorityTagType = (p) => ({ high: 'danger', medium: 'warning', low: 'info' }[p] || 'info')
const priorityLabel = (p) => ({ high: '高优先级', medium: '中优先级', low: '低优先级' }[p] || p)

const ratingTagType = (rating) => ({ 强: 'success', 中: 'warning', 弱: 'danger' }[rating] || 'info')

function beforeUpload(file) {
  const isPDF = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  if (!isPDF) {
    ElMessage.error('只能上传 PDF 文件！')
    return false
  }
  uploading.value = true
  return true
}
async function onUpload({ file }) {
  try {
    await uploadResume(file)
    ElMessage.success('已上传，AI 解析完成后可生成优化建议')
    await load()
  } catch (e) {
    console.error('上传失败：', e)
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message || '未知错误'))
  } finally {
    uploading.value = false
  }
}
let pollTimer = null
let polling = false
function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
async function load() {
  loading.value = true
  try {
    const res = await myResumes()
    resumes.value = res.data
    // 存在解析中的卡片时每 2s 轮询，全部落定后停止
    stopPoll()
    if (res.data.some((r) => r.parse_status === 'pending')) {
      pollTimer = setInterval(async () => {
        if (polling) return
        polling = true
        try {
          const r2 = await myResumes()
          resumes.value = r2.data
          if (!r2.data.some((x) => x.parse_status === 'pending')) stopPoll()
        } catch {
          // 轮询失败静默：下一轮自愈
        } finally {
          polling = false
        }
      }, 2000)
    }
  } finally {
    loading.value = false
  }
}
onUnmounted(stopPoll)
async function onReparse(row) {
  try {
    await reparseResume(row.id)
    ElMessage.success('已重新提交 AI 解析')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '重试失败')
  }
}
async function onDelete(row) {
  await ElMessageBox.confirm('删除后该简历无法用于岗位匹配，确定删除？', '提示', { type: 'warning' })
  deletingId.value = row.id
  try {
    await deleteResume(row.id)
    ElMessage.success('已删除')
    if (expandedId.value === row.id) expandedId.value = null
    load()
  } finally {
    deletingId.value = null
  }
}

function openPdf(r) {
  window.open(r.pdf_url, '_blank')
}

function toggleExpand(r) {
  expandedId.value = expandedId.value === r.id ? null : r.id
}

function openAdvice(row) {
  adviceTarget.value = row
  adviceJobReq.value = ''
  adviceDialog.value = true
}

async function doAdvice() {
  if (!adviceTarget.value) return
  advising.value = true
  advisingId.value = adviceTarget.value.id
  try {
    await generateAdvice(adviceTarget.value.id, adviceJobReq.value.trim() || null)
    adviceDialog.value = false
    ElMessage.success('优化建议已生成并保存')
    expandedId.value = adviceTarget.value.id
    await load()
  } catch (e) {
    console.error('生成建议失败：', e)
  } finally {
    advising.value = false
    advisingId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.resume-manage-page { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.tips { color: #606266; font-size: 13px; line-height: 1.7; }
.resume-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; }
.resume-title { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
.ml-8 { margin-left: 8px; }
.mt-8 { margin-top: 8px; }
.resume-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.advice-toggle { margin-top: 12px; color: var(--el-color-primary); font-size: 13px; cursor: pointer; user-select: none; }
.advice-toggle:hover { opacity: 0.8; }
.advice-panel { margin-top: 10px; background: #f7f8fa; border-radius: 6px; padding: 14px 16px; }
.advice-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; padding-bottom: 10px; border-bottom: 1px solid #e8e8e8; }
.advice-score { font-size: 22px; font-weight: 700; color: var(--el-color-primary); }
.advice-summary { color: #303133; font-size: 14px; flex: 1; }
.advice-time { color: #909399; font-size: 12px; }
.dim-ratings { display: flex; gap: 6px; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid #e8e8e8; }
.dim-tag { cursor: default; }
.advice-item { padding: 12px 0; border-bottom: 1px dashed #e2e2e2; }
.advice-item:last-child { border-bottom: none; }
.advice-item-head { display: flex; gap: 8px; margin-bottom: 6px; }
.advice-issue { font-size: 13.5px; color: #303133; line-height: 1.6; }
.advice-advice { margin-top: 6px; font-size: 13.5px; color: #4a6b3a; background: #f0f5ec; border-radius: 4px; padding: 8px 10px; line-height: 1.7; }
</style>
