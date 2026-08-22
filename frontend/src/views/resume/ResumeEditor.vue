<template>
  <div class="resume-editor">
    <!-- 顶部工具栏 -->
    <div class="editor-header">
      <div class="header-left">
        <el-button @click="goBack" text>
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <span class="resume-title">{{ resume?.file_name || '简历编辑' }}</span>
        <el-tag size="small" type="success" v-if="isFromImprove">AI 改良模式</el-tag>
      </div>
      <div class="header-right">
        <el-button @click="previewMode = previewMode === 'edit' ? 'pdf' : 'edit'">
          <el-icon><Files /></el-icon>
          {{ previewMode === 'edit' ? '查看原PDF' : '返回编辑' }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="saveResume">
          <el-icon><Check /></el-icon>
          保存
        </el-button>
      </div>
    </div>

    <!-- 两栏布局：左侧模块导航 + 右侧可编辑预览 -->
    <div class="editor-body">
      <!-- 左侧：模块导航 -->
      <div class="sidebar-left">
        <div class="sidebar-title">
          <el-icon><Menu /></el-icon>
          内容模块
        </div>
        <div class="module-list">
          <div
            class="module-item"
            :class="{ active: activeModule === 'basic' }"
            @click="scrollTo('basic')"
          >
            <el-icon><User /></el-icon>
            <span>基本信息</span>
          </div>
          <div
            v-for="(sec, si) in formData.sections"
            :key="sec.id || si"
            class="module-item"
            :class="{ active: activeModule === String(si) }"
            @click="scrollTo(String(si))"
          >
            <el-icon><component :is="sectionIcon(sec.type)" /></el-icon>
            <span class="module-label">{{ sec.title || sectionTitle(sec.type) }}</span>
            <el-dropdown trigger="click" @command="(cmd) => handleSectionCmd(cmd, si)" @click.stop>
              <el-icon class="module-more" @click.stop><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="up" :disabled="si === 0"><el-icon><Top /></el-icon> 上移</el-dropdown-item>
                  <el-dropdown-item command="down" :disabled="si === formData.sections.length - 1"><el-icon><Bottom /></el-icon> 下移</el-dropdown-item>
                  <el-dropdown-item command="delete" divided><el-icon><Delete /></el-icon> 删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div class="sidebar-add">
          <el-dropdown trigger="click" @command="addSection">
            <el-button size="small" type="primary" plain style="width:100%">
              <el-icon><Plus /></el-icon> 添加模块
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="opt in addableSections" :key="opt.value" :command="opt.value">
                  {{ opt.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="sidebar-tip">
          <p>💡 <b>操作提示</b></p>
          <p>• 点击简历中的文字即可直接编辑</p>
          <p>• 鼠标悬停模块标题可添加/删除</p>
          <p>• 以 • 开头会自动渲染为项目符号</p>
        </div>
      </div>

      <!-- 右侧：可编辑预览区 -->
      <div class="preview-area">
        <!-- 编辑预览：所见即所得 -->
        <div v-show="previewMode === 'edit'" class="preview-container" ref="previewContainerRef">
          <div class="resume-preview-shell">
            <div id="section-basic" class="section-anchor"></div>
            <EditableResumePreview
              :basic="formData.basic"
              :sections="formData.sections"
              :photo="photoUrl"
              @section-added="onSectionAdded"
            />
          </div>
        </div>

        <!-- PDF预览 -->
        <div v-show="previewMode === 'pdf'" class="pdf-preview-wrapper">
          <div class="pdf-toolbar">
            <span class="pdf-toolbar-title">
              <el-icon><Files /></el-icon>
              原始PDF简历
            </span>
            <a v-if="pdfUrl" :href="pdfUrl" target="_blank" class="open-pdf-new">
              <el-icon><Link /></el-icon> 新窗口打开
            </a>
          </div>
          <iframe
            v-if="pdfUrl"
            :src="pdfUrl"
            class="pdf-iframe"
            frameborder="0"
          ></iframe>
          <el-empty v-else description="无原PDF" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Check, User, Reading, Briefcase, Document,
  Plus, Delete, MagicStick, Files, Link, Trophy, Medal,
  Promotion, Clock, Collection, Menu, MoreFilled, Top, Bottom
} from '@element-plus/icons-vue'
import { getResume, updateResume } from '@/api/resume'
import EditableResumePreview from './EditableResumePreview.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const resume = ref(null)
const previewMode = ref('edit')
const activeModule = ref('basic')
const previewContainerRef = ref(null)
const isFromImprove = computed(() => route.query?.improved === '1' || route.query?.from === 'improve')

const sectionMeta = {
  basic: { label: '基本信息', icon: User },
  education: { label: '教育背景', icon: Reading },
  skills: { label: '专业技能', icon: MagicStick },
  experience: { label: '实习/工作经历', icon: Briefcase },
  projects: { label: '项目经历', icon: Promotion },
  awards: { label: '获奖荣誉', icon: Trophy },
  certificates: { label: '证书资格', icon: Medal },
  summary: { label: '自我评价', icon: Document },
  interests: { label: '兴趣爱好', icon: Clock },
  other: { label: '其它', icon: Collection }
}
const addableSections = [
  { value: 'education', label: '教育背景' },
  { value: 'experience', label: '实习/工作经历' },
  { value: 'projects', label: '项目经历' },
  { value: 'skills', label: '专业技能' },
  { value: 'awards', label: '获奖荣誉' },
  { value: 'certificates', label: '证书资格' },
  { value: 'summary', label: '自我评价' },
  { value: 'interests', label: '兴趣爱好' },
  { value: 'other', label: '其它' }
]
const sectionIcon = (type) => sectionMeta[type]?.icon || Collection
const sectionTitle = (type) => sectionMeta[type]?.label || '其它'

const defaultFormData = () => ({
  basic: { name: '', title: '', phone: '', email: '', location: '', github: '', links: '', photo: '' },
  sections: []
})

const formData = reactive(defaultFormData())

const pdfUrl = computed(() => {
  if (resume.value?.pdf_url) return `http://localhost:8000${resume.value.pdf_url}`
  return ''
})

const photoUrl = computed(() => {
  if (formData.basic.photo) {
    if (formData.basic.photo.startsWith('http')) return formData.basic.photo
    return `http://localhost:8000${formData.basic.photo}`
  }
  if (resume.value?.photo_url) return `http://localhost:8000${resume.value.photo_url}`
  return ''
})

let idCounter = 0
const createItem = () => ({ heading: '', subheading: '', date: '', description: '' })
const createSection = (type) => ({
  id: `e_${++idCounter}`,
  type,
  title: sectionTitle(type) || '其它',
  items: (type === 'summary' || type === 'skills') ? [createItem()] : []
})

const addSection = (type) => {
  formData.sections.push(createSection(type))
  nextTick(() => scrollTo(String(formData.sections.length - 1)))
}

const onSectionAdded = () => {}

const handleSectionCmd = (cmd, si) => {
  if (cmd === 'up' && si > 0) {
    const t = formData.sections[si - 1]
    formData.sections[si - 1] = formData.sections[si]
    formData.sections[si] = t
  } else if (cmd === 'down' && si < formData.sections.length - 1) {
    const t = formData.sections[si + 1]
    formData.sections[si + 1] = formData.sections[si]
    formData.sections[si] = t
  } else if (cmd === 'delete') {
    ElMessageBox.confirm('确定删除该模块？', '提示', { type: 'warning' }).then(() => {
      formData.sections.splice(si, 1)
    }).catch(() => {})
  }
}

const scrollTo = (key) => {
  activeModule.value = key
  if (previewMode.value !== 'edit') previewMode.value = 'edit'
  nextTick(() => {
    let el
    if (key === 'basic') {
      el = document.getElementById('section-basic')
    } else {
      // 第 key 个 section（从 basic 后开始）
      const shell = document.querySelector('.resume-preview-shell')
      if (shell) {
        const sections = shell.querySelectorAll('.pdf-section')
        el = sections[Number(key)]
      }
    }
    if (el && previewContainerRef.value) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
}

const initFormDataFromResume = (resumeData) => {
  const data = defaultFormData()
  data.basic = {
    name: resumeData.parsed_name || '',
    title: resumeData.parsed_job_title || '',
    phone: resumeData.parsed_phone || '',
    email: resumeData.parsed_email || '',
    location: resumeData.parsed_location || '',
    github: resumeData.parsed_github || '',
    links: resumeData.parsed_links || '',
    photo: resumeData.photo_url || ''
  }
  if (Array.isArray(resumeData.parsed_sections) && resumeData.parsed_sections.length) {
    data.sections = resumeData.parsed_sections.map(sec => {
      const section = {
        id: `p_${++idCounter}`,
        type: sec.type || 'other',
        title: sec.title || sectionTitle(sec.type),
        items: []
      }
      if (sec.type === 'skills') {
        // 技能模块：优先使用 items 中的 description 文本
        if (Array.isArray(sec.items) && sec.items.length) {
          section.items = sec.items.map(it => ({
            heading: it.heading || '',
            subheading: it.subheading || '',
            date: it.date || '',
            description: it.description || (it.heading ? it.heading : '')
          }))
          // 如果所有 description 都为空但有 heading，说明是旧的标签格式，合并为文本
          const allEmptyDesc = section.items.every(it => !it.description)
          if (allEmptyDesc) {
            const skillsText = section.items.map(it => it.heading).filter(Boolean).join('、')
            section.items = [{ heading: '', subheading: '', date: '', description: skillsText }]
          }
        } else if (Array.isArray(sec.skills) && sec.skills.length) {
          // 旧格式 skills 数组
          section.items = [{ heading: '', subheading: '', date: '', description: sec.skills.join('、') }]
        } else {
          section.items = [createItem()]
        }
      } else if (Array.isArray(sec.items)) {
        section.items = sec.items.map(it => ({
          heading: it.heading || '',
          subheading: it.subheading || '',
          date: it.date || '',
          description: it.description || ''
        }))
      }
      return section
    })
  } else {
    const secs = []
    if (resumeData.parsed_education?.length) {
      const a = createSection('education')
      a.items = resumeData.parsed_education.map(e => ({
        heading: e.school || '', subheading: [e.major, e.degree].filter(Boolean).join(' · '),
        date: [e.start_date, e.end_date].filter(Boolean).join(' - '), description: e.description || ''
      }))
      secs.push(a)
    }
    if (resumeData.parsed_skills?.length) {
      const a = createSection('skills')
      const skillsText = resumeData.parsed_skills.map(s => typeof s === 'string' ? s : (s.name || '')).filter(Boolean).join('、')
      a.items = [{ heading: '', subheading: '', date: '', description: skillsText }]
      secs.push(a)
    }
    if (resumeData.parsed_experience?.length) {
      const a = createSection('experience')
      a.items = resumeData.parsed_experience.map(e => ({
        heading: e.company || '', subheading: [e.title, e.type].filter(Boolean).join(' · '),
        date: [e.start_date, e.end_date].filter(Boolean).join(' - '), description: e.content || ''
      }))
      secs.push(a)
    }
    if (resumeData.parsed_summary) {
      const a = createSection('summary')
      a.items = [{ heading: '', subheading: '', date: '', description: resumeData.parsed_summary }]
      secs.push(a)
    }
    data.sections = secs
  }
  if (resumeData.edited_data) {
    const edited = resumeData.edited_data
    if (edited.basic) data.basic = { ...data.basic, ...edited.basic }
    if (Array.isArray(edited.sections) && edited.sections.length) {
      data.sections = edited.sections.map(s => {
        const section = {
          id: `e_${++idCounter}`,
          type: s.type || 'other',
          title: s.title || sectionTitle(s.type),
          items: []
        }
        if (s.type === 'skills') {
          if (Array.isArray(s.items) && s.items.length) {
            section.items = s.items.map(it => ({
              heading: it.heading || '',
              subheading: it.subheading || '',
              date: it.date || '',
              description: it.description || (it.heading ? it.heading : '')
            }))
            const allEmptyDesc = section.items.every(it => !it.description)
            if (allEmptyDesc) {
              const skillsText = section.items.map(it => it.heading).filter(Boolean).join('、')
              section.items = [{ heading: '', subheading: '', date: '', description: skillsText }]
            }
          } else if (Array.isArray(s.skills)) {
            section.items = [{ heading: '', subheading: '', date: '', description: s.skills.join('、') }]
          } else {
            section.items = [createItem()]
          }
        } else if (Array.isArray(s.items)) {
          section.items = s.items.map(it => ({
            heading: it.heading || '', subheading: it.subheading || '', date: it.date || '', description: it.description || ''
          }))
        }
        return section
      })
    }
  }
  return data
}

const initFormDataFromProject = (project) => {
  const data = defaultFormData()
  const b = project.basic || {}
  data.basic = {
    name: b.name || '', title: b.title || '', phone: b.phone || '',
    email: b.email || '', location: b.location || '',
    github: b.github || '', links: b.links || '',
    photo: b.photo || ''
  }
  if (Array.isArray(project.sections)) {
    data.sections = project.sections.map(sec => {
      const section = {
        id: `i_${++idCounter}`,
        type: sec.type || 'other',
        title: sec.title || sectionTitle(sec.type) || '其它',
        items: []
      }
      if (sec.type === 'skills') {
        if (Array.isArray(sec.skills) && (!sec.items || !sec.items.length)) {
          section.items = [{ heading: '', subheading: '', date: '', description: sec.skills.join('、') }]
        } else if (Array.isArray(sec.items)) {
          section.items = sec.items.map(it => ({
            heading: it.heading || it.h || '',
            subheading: it.subheading || it.s || '',
            date: it.date || it.d || '',
            description: it.description || it.c || (it.heading ? it.heading : '')
          }))
          const allEmptyDesc = section.items.every(it => !it.description)
          if (allEmptyDesc) {
            const skillsText = section.items.map(it => it.heading).filter(Boolean).join('、')
            section.items = [{ heading: '', subheading: '', date: '', description: skillsText }]
          }
        } else {
          section.items = [createItem()]
        }
      } else if (Array.isArray(sec.items)) {
        section.items = sec.items.map(it => ({
          heading: it.heading || it.h || '',
          subheading: it.subheading || it.s || '',
          date: it.date || it.d || '',
          description: it.description || it.c || ''
        }))
      }
      return section
    })
  }
  return data
}

const loadResume = async () => {
  const id = route.params.id
  if (!id) return
  loading.value = true
  try {
    const res = await getResume(id)
    resume.value = res.data
    // 改良结果已在点击"应用到编辑器"时保存到后端（edited_data），直接从后端加载即可
    const initData = initFormDataFromResume(res.data)
    Object.assign(formData, initData)
    activeModule.value = 'basic'
    if (isFromImprove.value) {
      ElMessage.success('AI 改良内容已载入，点击任意文字即可编辑')
    }
  } catch (e) {
    console.error('加载简历失败：', e)
    ElMessage.error('加载简历失败')
  } finally {
    loading.value = false
  }
}

const saveResume = async () => {
  const id = route.params.id
  if (!id) return
  saving.value = true
  try {
    // api层已包装 { edited_data: ... }，直接传内容即可
    const editedData = {
      basic: formData.basic,
      sections: formData.sections.map(({ id: _id, ...rest }) => rest)
    }
    await updateResume(id, editedData)
    ElMessage.success('保存成功')
    router.push('/resume')
  } catch (e) {
    console.error('保存失败：', e)
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

const goBack = () => router.push('/resume')

onMounted(() => {
  loadResume()
})
</script>

<style scoped>
.resume-editor {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #525659;
}

.editor-header {
  height: 56px;
  background: #2f3033;
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  z-index: 10;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left :deep(.el-button) { color: #fff; }
.header-left :deep(.el-button:hover) { color: #409eff; }
.resume-title { font-size: 16px; font-weight: 600; }
.header-right { display: flex; align-items: center; gap: 8px; }

.editor-body { flex: 1; display: flex; overflow: hidden; }

.sidebar-left {
  width: 230px;
  background: #f3f4f6;
  border-right: 1px solid #dcdfe6;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.sidebar-title {
  padding: 14px 16px;
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 6px;
  border-bottom: 1px solid #e4e7ed;
}

.module-list { padding: 8px; flex: 1; }

.module-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  color: #606266;
  font-size: 13.5px;
  margin-bottom: 2px;
  transition: all 0.15s;
  position: relative;
}
.module-item:hover { background: #e6e8eb; color: #303133; }
.module-item.active { background: #409eff; color: #fff; }
.module-item.active .module-more { color: #fff; }
.module-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.module-more {
  opacity: 0;
  font-size: 14px;
  color: #909399;
}
.module-item:hover .module-more { opacity: 0.7; }
.module-more:hover { opacity: 1 !important; }

.sidebar-add { padding: 8px 12px 12px; border-top: 1px solid #e4e7ed; }
.sidebar-tip {
  padding: 12px 16px;
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
  border-top: 1px solid #e4e7ed;
  background: #fafbfc;
}
.sidebar-tip p { margin: 0; }
.sidebar-tip b { color: #606266; }

.preview-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #525659;
}

.preview-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px 0;
  background: #525659;
}
.section-anchor { height: 0; }

.resume-preview-shell {
  max-width: 820px;
  margin: 0 auto;
  background: #525659;
  padding: 0 20px;
}
.resume-preview-shell :deep(.resume-pdf) {
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  min-height: calc(100vh - 160px);
}

.pdf-preview-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #525659;
  padding: 12px;
}
.pdf-toolbar {
  background: #2f3033;
  color: #fff;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-radius: 4px 4px 0 0;
  font-size: 14px;
}
.pdf-toolbar-title { display: flex; align-items: center; gap: 6px; }
.open-pdf-new { color: #79bbff; font-size: 13px; display: flex; align-items: center; gap: 4px; }
.open-pdf-new:hover { color: #a0cfff; }
.pdf-iframe {
  width: 100%;
  flex: 1;
  border: none;
  border-radius: 0 0 4px 4px;
  background: white;
}
</style>