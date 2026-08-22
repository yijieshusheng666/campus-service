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
      <p class="tips">上传 PDF 简历后，点击「AI 改良」可对简历进行智能优化并在线编辑预览。</p>
    </el-card>

    <el-empty v-if="!loading && !resumes.length" description="暂无简历，请先上传" />

    <div v-for="r in resumes" :key="r.id" class="resume-card-wrapper">
      <el-card class="resume-card mb-16" v-loading="deletingId === r.id">
        <div class="resume-header">
          <div>
            <div class="resume-title">
              {{ r.parsed_name || r.file_name }}
              <el-tag v-if="r.parsed_job_title" size="small" type="primary" class="ml-8">{{ r.parsed_job_title }}</el-tag>
              <el-tag v-if="r.edited_data" size="small" type="success" class="ml-8">
                已改良
              </el-tag>
            </div>
            <div class="text-muted">
              文件：{{ r.file_name }} · 上传于 {{ formatDate(r.created_at) }}
            </div>
          </div>
          <div class="resume-actions">
            <el-button v-if="r.edited_data" type="success" @click="openEditor(r)">
              <el-icon style="margin-right:4px"><Edit /></el-icon>
              在线编辑
            </el-button>
            <el-button type="primary" plain @click="openImprove(r)">AI 改良</el-button>
            <el-button type="danger" plain @click="onDelete(r)">删除</el-button>
          </div>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="improveDialog" title="AI 改良简历" width="960px" top="5vh">
      <p class="tips">可选择粘贴目标岗位要求做定向改良；留空则对简历做通用优化。</p>
      <div style="display:flex;gap:12px;align-items:flex-start">
        <el-input v-model="improveJobReq" type="textarea" :rows="3" placeholder="岗位要求（可选）" style="flex:1" />
        <el-button type="primary" :loading="improving" @click="doImprove" style="margin-top:4px">开始改良</el-button>
      </div>
      <div v-if="improvedProject" class="improved-box">
        <el-divider content-position="left">改良结果（PDF 样式预览）</el-divider>
        <div class="improved-preview">
          <ResumePreviewCard
            :basic="improvedProject.basic"
            :sections="improvedProject.sections"
            :photo="improveTarget?.photo_url ? `http://localhost:8000${improveTarget.photo_url}` : ''"
          />
        </div>
        <div class="mt-12" style="text-align: right">
          <el-button type="primary" :loading="applying" @click="applyImprovement">应用到编辑器</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentAdd, Edit } from '@element-plus/icons-vue'
import { uploadResume, myResumes, deleteResume, improveResume, updateResume } from '@/api/resume'
import ResumePreviewCard from './ResumePreviewCard.vue'

const router = useRouter()
const resumes = ref([])
const loading = ref(false)
const uploading = ref(false)
const deletingId = ref(null)

const improveDialog = ref(false)
const improveTarget = ref(null)
const improveJobReq = ref('')
const improving = ref(false)
const improvedProject = ref(null)

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

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
    const res = await uploadResume(file)
    ElMessage.success('简历上传并解析成功！请点击「AI 改良」开始优化简历')
    await load()
  } catch (e) {
    console.error('上传失败：', e)
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message || '未知错误'))
  } finally {
    uploading.value = false
  }
}
async function load() {
  loading.value = true
  try {
    const res = await myResumes()
    resumes.value = res.data
  } finally {
    loading.value = false
  }
}
async function onDelete(row) {
  await ElMessageBox.confirm('删除后该简历无法用于岗位匹配，确定删除？', '提示', { type: 'warning' })
  deletingId.value = row.id
  try {
    await deleteResume(row.id)
    ElMessage.success('已删除')
    load()
  } finally {
    deletingId.value = null
  }
}

function openEditor(row) {
  router.push({ name: 'ResumeEditor', params: { id: row.id } })
}

function openImprove(row) {
  improveTarget.value = row
  improveJobReq.value = ''
  improvedProject.value = null
  improveDialog.value = true
}

async function doImprove() {
  if (!improveTarget.value) return
  improving.value = true
  improvedProject.value = null
  try {
    const res = await improveResume(improveTarget.value.id, improveJobReq.value.trim() || null)
    const d = res.data
    if (d.improved_project) {
      improvedProject.value = d.improved_project
    } else {
      ElMessage.error('改良结果格式异常，请重试')
    }
    ElMessage.success('AI 改良完成')
  } catch (e) {
    ElMessage.error('AI 改良失败，请稍后重试')
  } finally {
    improving.value = false
  }
}

const applying = ref(false)

async function applyImprovement() {
  if (!improveTarget.value || !improvedProject.value) return
  applying.value = true
  try {
    // 1. 先把改良结果保存到后端（edited_data）
    const editedData = {
      basic: { ...improvedProject.value.basic, photo: improveTarget.value.photo_url || '' },
      sections: (improvedProject.value.sections || []).map(sec => {
        // 兼容旧的 skills 数组格式
        if (sec.type === 'skills' && Array.isArray(sec.skills) && (!sec.items || !sec.items.length)) {
          return { ...sec, items: [{ heading: '', subheading: '', date: '', description: sec.skills.join('、') }] }
        }
        // 确保 skills 模块的 items 中 description 是文本
        if (sec.type === 'skills' && Array.isArray(sec.items)) {
          return {
            ...sec,
            items: sec.items.map(it => ({
              heading: it.heading || it.h || '',
              subheading: it.subheading || it.s || '',
              date: it.date || it.d || '',
              description: it.description || it.c || (it.heading ? it.heading : '')
            }))
          }
        }
        return sec
      })
    }
    await updateResume(improveTarget.value.id, editedData)
    // 2. 关闭弹窗，刷新列表（显示"已改良"标签和"在线编辑"按钮）
    improveDialog.value = false
    ElMessage.success('改良结果已保存，正在进入在线编辑器...')
    await load()
    // 3. 跳转到在线编辑器
    router.push({ name: 'ResumeEditor', params: { id: improveTarget.value.id }, query: { improved: '1' } })
  } catch (e) {
    console.error('应用改良失败：', e)
    ElMessage.error('应用失败：' + (e.response?.data?.detail || e.message))
  } finally {
    applying.value = false
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
.resume-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.mt-12 { margin-top: 12px; }
.improved-box { margin-top: 16px; }
.improved-preview {
  background: #e8e8e8;
  padding: 20px;
  border-radius: 6px;
  max-height: 60vh;
  overflow-y: auto;
}
.improved-preview :deep(.resume-preview) { padding: 32px 36px; min-height: 300px; }
.improved-text { white-space: pre-wrap; background: #f5f7fa; padding: 12px; border-radius: 6px; line-height: 1.7; }
</style>
