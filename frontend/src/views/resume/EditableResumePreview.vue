<template>
  <div class="resume-pdf">
    <!-- 头部 -->
    <div class="pdf-header">
      <div class="avatar-box">
        <img v-if="photo" :src="photo" class="avatar-img" alt="照片" />
        <div v-else class="avatar-placeholder">
          <el-icon :size="42" color="#fff"><User /></el-icon>
        </div>
      </div>
      <div class="header-main">
        <div class="name-row">
          <span class="name-label">姓名：</span>
          <EditableText
            :value="basic.name"
            placeholder="你的姓名"
            :bold="true"
            :size="28"
            @update="basic.name = $event"
          />
        </div>
        <div class="job-title">
          <EditableText
            :value="basic.title"
            placeholder="求职意向"
            :size="18"
            @update="basic.title = $event"
          />
        </div>
      </div>
      <div class="header-contact">
        <div class="contact-item">
          <span class="contact-icon"><el-icon><Message /></el-icon></span>
          <EditableText :value="basic.email" placeholder="邮箱" @update="basic.email = $event" />
        </div>
        <div class="contact-item">
          <span class="contact-icon"><el-icon><Phone /></el-icon></span>
          <EditableText :value="basic.phone" placeholder="电话" @update="basic.phone = $event" />
        </div>
        <div class="contact-item">
          <span class="contact-icon"><el-icon><Link /></el-icon></span>
          <EditableText :value="basic.github" placeholder="GitHub/个人主页" @update="basic.github = $event" />
        </div>
        <div class="contact-item">
          <span class="contact-icon"><el-icon><Location /></el-icon></span>
          <EditableText :value="basic.location" placeholder="所在地" @update="basic.location = $event" />
        </div>
      </div>
    </div>

    <!-- 动态模块 -->
    <div v-for="(sec, sIdx) in sections" :key="sec.id || sIdx" class="pdf-section">
      <div class="section-header">
        <h3 class="section-title">
          <EditableText
            :value="sec.title || sectionTitle(sec.type)"
            placeholder="模块标题"
            :bold="true"
            :size="20"
            @update="sec.title = $event"
          />
        </h3>
        <div class="section-actions">
          <el-dropdown trigger="click" @command="(t) => addItemWithType(sIdx, t)">
            <el-button size="small" text type="primary">
              <el-icon><Plus /></el-icon> 添加
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="sec.type === 'skills'" command="skill">添加技能分类</el-dropdown-item>
                <el-dropdown-item v-else command="item">添加条目</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-popconfirm title="确定删除该模块？" @confirm="removeSection(sIdx)">
            <template #reference>
              <el-button size="small" text type="danger"><el-icon><Delete /></el-icon></el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
      <div class="section-divider"></div>

      <!-- 技能模块：文本编辑形式 -->
      <template v-if="sec.type === 'skills'">
        <div v-for="(item, idx) in sec.items" :key="idx" class="entry-block">
          <div class="item-toolbar">
            <el-popconfirm title="删除此段？" @confirm="removeItem(sIdx, idx)">
              <template #reference>
                <el-button size="small" text type="danger"><el-icon><Delete /></el-icon></el-button>
              </template>
            </el-popconfirm>
          </div>
          <div class="skill-heading-edit" v-if="sec.items.length > 1 || item.heading">
            <EditableText
              :value="item.heading"
              placeholder="技能分类（如：编程语言，可留空）"
              :bold="true"
              :size="15.5"
              @update="item.heading = $event"
            />
          </div>
          <EditableTextarea
            :value="item.description"
            placeholder="熟练掌握Java、Python、C++等编程语言，熟悉Spring Boot、Django等开发框架..."
            @update="item.description = $event"
          />
        </div>
      </template>

      <!-- 自我评价 -->
      <template v-else-if="sec.type === 'summary'">
        <div v-for="(item, idx) in sec.items" :key="idx" class="entry-block">
          <div class="item-toolbar">
            <el-popconfirm title="删除此段？" @confirm="removeItem(sIdx, idx)">
              <template #reference>
                <el-button size="small" text type="danger"><el-icon><Delete /></el-icon></el-button>
              </template>
            </el-popconfirm>
          </div>
          <EditableTextarea
            :value="item.description"
            placeholder="自我评价..."
            @update="item.description = $event"
          />
        </div>
      </template>

      <!-- 其他条目类模块 -->
      <template v-else>
        <div v-for="(item, idx) in sec.items" :key="idx" class="entry-block">
          <div class="entry-row" v-if="true">
            <EditableText
              :value="item.heading"
              placeholder="学校/公司/项目名称"
              :bold="true"
              :size="17"
              class="entry-heading-edit"
              @update="item.heading = $event"
            />
            <EditableText
              :value="item.subheading"
              placeholder="专业·学历 / 职位"
              :size="15.5"
              class="entry-sub-edit"
              @update="item.subheading = $event"
            />
            <div class="entry-right">
              <EditableText
                :value="item.date"
                placeholder="2023/09 - 2027/06"
                :size="15"
                class="entry-date-edit"
                @update="item.date = $event"
              />
              <el-popconfirm title="删除此条目？" @confirm="removeItem(sIdx, idx)">
                <template #reference>
                  <el-button size="small" text type="danger" class="item-del-btn"><el-icon><Delete /></el-icon></el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
          <div class="entry-body" v-if="sec.type !== 'summary'">
            <EditableTextarea
              :value="item.description"
              placeholder="详细描述，可用 • 开头表示项目符号"
              @update="item.description = $event"
            />
          </div>
        </div>
      </template>
    </div>

    <!-- 添加模块按钮 -->
    <div class="add-section-btn">
      <el-dropdown trigger="click" @command="addSection">
        <el-button type="primary" plain size="default">
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
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { User, Message, Phone, Link, Location, Plus, Delete, Close } from '@element-plus/icons-vue'
import EditableText from './EditableText.vue'
import EditableTextarea from './EditableTextarea.vue'

const props = defineProps({
  basic: { type: Object, required: true },
  sections: { type: Array, required: true },
  photo: { type: String, default: '' }
})

const emit = defineEmits(['update:basic', 'update:sections'])

const sectionMeta = {
  education: '教育背景', skills: '专业技能', experience: '实习经历',
  projects: '项目经历', awards: '获奖荣誉', certificates: '证书资格',
  summary: '自我评价', interests: '兴趣爱好', other: '其它'
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
const sectionTitle = (type) => sectionMeta[type] || '其它'

let idCounter = 0
const createItem = (type) => {
  if (type === 'skills') {
    return { heading: '', subheading: '', date: '', description: '' }
  }
  return { heading: '', subheading: '', date: '', description: '' }
}
const createSection = (type) => ({
  id: `e_${++idCounter}`,
  type,
  title: sectionMeta[type] || '其它',
  items: type === 'summary' ? [createItem(type)] : (type === 'skills' ? [createItem(type)] : [])
})

const addItem = (si) => {
  if (props.sections[si]) props.sections[si].items.push(createItem(props.sections[si].type))
}
const addItemWithType = (si, type) => addItem(si)
const removeItem = (si, idx) => {
  props.sections[si].items.splice(idx, 1)
}
const removeSection = (si) => {
  props.sections.splice(si, 1)
}
const addSection = (type) => {
  props.sections.push(createSection(type))
}
</script>

<style scoped>
.resume-pdf {
  background: #fff;
  padding: 36px 44px;
  color: #111;
  font-family: "Microsoft YaHei", "SimSun", "PingFang SC", sans-serif;
  font-size: 14px;
  line-height: 1.6;
  font-weight: 400;
  min-height: calc(100vh - 140px);
}

.pdf-header { display: flex; align-items: flex-start; gap: 22px; margin-bottom: 22px; padding-bottom: 10px; }
.avatar-box { flex-shrink: 0; }
.avatar-placeholder {
  width: 92px; height: 116px;
  background: #2669c9;
  display: flex; align-items: center; justify-content: center;
}
.avatar-img {
  width: 92px;
  height: 116px;
  object-fit: cover;
  display: block;
}
.header-main { flex: 1; padding-top: 6px; }
.name-row { font-size: 28px; font-weight: bold; color: #111; letter-spacing: 1px; display: flex; align-items: center; }
.name-label { font-weight: bold; margin-right: 2px; flex-shrink: 0; }
.job-title { font-size: 18px; color: #222; margin-top: 10px; font-weight: 500; min-height: 24px; }

.header-contact {
  flex-shrink: 0;
  padding-top: 10px;
  font-size: 15px;
  line-height: 1.95;
  color: #222;
  min-width: 260px;
}
.contact-item { display: flex; align-items: flex-start; gap: 8px; min-height: 28px; }
.contact-icon { color: #222; width: 20px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; padding-top: 2px; }
.contact-icon :deep(svg) { width: 18px; height: 18px; }

.pdf-section { margin-bottom: 18px; position: relative; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title {
  font-size: 20px; font-weight: bold; color: #111;
  margin: 14px 0 4px 0; padding: 0; display: flex; align-items: center;
}
.section-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s; }
.pdf-section:hover .section-actions { opacity: 1; }
.section-divider { height: 2px; background: #222; margin-bottom: 10px; }

.entry-block { margin-bottom: 12px; position: relative; padding-right: 40px; }
.item-toolbar { position: absolute; right: 0; top: 0; opacity: 0; transition: opacity 0.15s; }
.entry-block:hover .item-toolbar, .entry-block:hover .item-del-btn { opacity: 1; }
.entry-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: baseline;
  gap: 24px;
  margin-bottom: 4px;
}
.entry-heading-edit { font-weight: bold; font-size: 17px; color: #111; word-break: break-word; min-width: 0; display: block; }
.entry-sub-edit { font-size: 15.5px; color: #222; min-width: 0; display: block; }
.entry-right { display: flex; align-items: center; gap: 8px; }
.entry-date-edit { font-size: 15px; color: #222; white-space: nowrap; text-align: right; display: block; }
.item-del-btn { opacity: 0; transition: opacity 0.15s; padding: 4px; }

.entry-body { margin-top: 4px; font-size: 14.5px; line-height: 1.7; color: #222; }

.skill-heading-edit { margin-bottom: 4px; }

.add-section-btn { text-align: center; padding: 20px 0; }

/* 可编辑字段通用样式 */
:deep(.editable-text) {
  outline: none;
  border-bottom: 1px dashed transparent;
  min-width: 40px;
  cursor: text;
  transition: border-color 0.15s, background 0.15s;
  border-radius: 2px;
}
:deep(.editable-text:hover) { border-bottom-color: #c0c4cc; background: rgba(64,158,255,0.04); }
:deep(.editable-text.editing) {
  border-bottom-color: #409eff; background: #fff;
  box-shadow: 0 0 0 2px rgba(64,158,255,0.15);
  padding: 1px 4px;
}
:deep(.editable-text.placeholder) { color: #c0c4cc; }

:deep(.editable-textarea-wrap) { position: relative; }
:deep(.editable-textarea-display) {
  white-space: pre-wrap; outline: none;
  border-bottom: 1px dashed transparent;
  border-radius: 3px; padding: 2px 4px; min-height: 22px;
  cursor: text; line-height: 1.75;
  transition: border-color 0.15s, background 0.15s;
}
:deep(.editable-textarea-display:hover) { border-bottom-color: #c0c4cc; background: rgba(64,158,255,0.04); }
:deep(.editable-textarea-display.editing) {
  border-bottom-color: #409eff; background: #fff;
  box-shadow: 0 0 0 2px rgba(64,158,255,0.15);
}
:deep(.editable-textarea-display.placeholder) { color: #c0c4cc; }
:deep(.editable-textarea-display .bullet-line) { display: block; padding-left: 16px; position: relative; }
:deep(.editable-textarea-display .bullet-line::before) {
  content: "•"; position: absolute; left: 4px; font-weight: bold;
}
:deep(.editable-textarea-input) {
  width: 100%; font-family: inherit; font-size: inherit; line-height: 1.75;
  border: 1px solid #409eff; border-radius: 4px; padding: 6px 8px;
  outline: none; resize: vertical; min-height: 80px;
  box-shadow: 0 0 0 2px rgba(64,158,255,0.15);
}
</style>
