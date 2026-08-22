<template>
  <div class="resume-pdf">
    <!-- 头部 -->
    <div class="pdf-header">
      <!-- 左侧头像 -->
      <div class="avatar-box">
        <img v-if="photo" :src="photo" class="avatar-img" alt="照片" />
        <div v-else class="avatar-placeholder">
          <el-icon :size="42" color="#3478f6"><User /></el-icon>
        </div>
      </div>

      <!-- 中间：姓名+职位 -->
      <div class="header-main">
        <div class="name-row">
          <span class="name-label">姓名：</span>
          <span class="name-value">{{ basic.name || '你的姓名' }}</span>
        </div>
        <div class="job-title">{{ basic.title || '' }}</div>
      </div>

      <!-- 右侧：联系方式 -->
      <div class="header-contact">
        <div v-if="basic.email" class="contact-item">
          <span class="contact-icon"><el-icon><Message /></el-icon></span>
          <span>{{ basic.email }}</span>
        </div>
        <div v-if="basic.phone" class="contact-item">
          <span class="contact-icon"><el-icon><Phone /></el-icon></span>
          <span>{{ basic.phone }}</span>
        </div>
        <div v-if="basic.github || basic.links" class="contact-item">
          <span class="contact-icon"><el-icon><Link /></el-icon></span>
          <span class="contact-links">
            <template v-if="basic.github">{{ basic.github }}</template>
            <template v-if="basic.github && basic.links"><br/></template>
            <template v-if="basic.links">{{ basic.links }}</template>
          </span>
        </div>
        <div v-if="basic.location" class="contact-item">
          <span class="contact-icon"><el-icon><Location /></el-icon></span>
          <span>{{ basic.location }}</span>
        </div>
      </div>
    </div>

    <!-- 动态模块 -->
    <div v-for="(sec, sIdx) in sections" :key="sec.id || sIdx" class="pdf-section">
      <h3 class="section-title">{{ sec.title || sectionTitle(sec.type) }}</h3>
      <div class="section-divider"></div>

      <!-- 技能模块：文本描述形式 -->
      <template v-if="sec.type === 'skills'">
        <div v-for="(item, idx) in sec.items" :key="idx" class="entry-block">
          <div class="entry-row" v-if="item.heading">
            <div class="entry-heading">{{ item.heading || '' }}</div>
          </div>
          <div v-if="item.description" class="entry-body">
            <template v-for="(block, bi) in parseContent(item.description)" :key="bi">
              <p v-if="block.lead" class="entry-lead">{{ block.lead }}</p>
              <ul v-if="block.bullets && block.bullets.length" class="bullet-list">
                <li v-for="(b, li) in block.bullets" :key="li">{{ b }}</li>
              </ul>
            </template>
          </div>
        </div>
      </template>

      <!-- 自我评价模块：普通段落 -->
      <template v-else-if="sec.type === 'summary'">
        <p class="plain-text" style="white-space:pre-wrap">{{ firstDesc(sec.items) }}</p>
      </template>

      <!-- 其它模块：条目列表 -->
      <template v-else>
        <div v-for="(item, idx) in sec.items" :key="idx" class="entry-block">
          <!-- 条目头部：三列布局 -->
          <div class="entry-row" v-if="item.heading || item.subheading || item.date">
            <div class="entry-heading">{{ item.heading || '' }}</div>
            <div class="entry-sub">{{ item.subheading || '' }}</div>
            <div class="entry-date">{{ item.date || '' }}</div>
          </div>
          <!-- 描述：自动拆分段落 + 圆点列表 -->
          <div v-if="item.description" class="entry-body">
            <template v-for="(block, bi) in parseContent(item.description)" :key="bi">
              <p v-if="block.lead" class="entry-lead">{{ block.lead }}</p>
              <ul v-if="block.bullets && block.bullets.length" class="bullet-list">
                <li v-for="(b, li) in block.bullets" :key="li">{{ b }}</li>
              </ul>
            </template>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { User, Message, Phone, Link, Location } from '@element-plus/icons-vue'

defineProps({
  basic: { type: Object, default: () => ({}) },
  sections: { type: Array, default: () => [] },
  photo: { type: String, default: '' }
})

const sectionMeta = {
  education: '教育背景', skills: '专业技能', experience: '实习经历',
  projects: '项目经历', awards: '获奖荣誉', certificates: '证书资格',
  summary: '自我评价', interests: '兴趣爱好', other: '其它', basic: '基本信息'
}
const sectionTitle = (t) => sectionMeta[t] || '其它'
const firstDesc = (items) => (items && items[0] && items[0].description) || ''

// 解析内容：自动识别以 •/-/* 开头的项目符号，拆分引导句+列表
function parseContent(text) {
  if (!text) return []
  const blocks = []
  // 先按空行分段
  const paragraphs = String(text).split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
  for (const para of paragraphs) {
    const lines = para.split('\n').map(l => l.trim()).filter(Boolean)
    if (!lines.length) continue
    // 判断是否整段都是项目符号行
    let bullets = []
    let lead = ''
    let seenBullet = false
    for (const line of lines) {
      const stripped = line.replace(/^[•·●\-\*\d\.\s]+/, '').trim()
      const isBullet = /^[•·●\-\*]/.test(line)
      if (isBullet || seenBullet) {
        seenBullet = true
        if (stripped) bullets.push(stripped)
      } else {
        lead = (lead ? lead + ' ' : '') + stripped
      }
    }
    // 如果整段都是带数字或项目符号的，但首行没匹配上，回退：首行作为 lead
    if (!lead && !bullets.length) {
      lead = lines.join(' ')
    }
    blocks.push({ lead, bullets })
  }
  return blocks
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
}

/* ===== 头部 ===== */
.pdf-header {
  display: flex;
  align-items: flex-start;
  gap: 22px;
  margin-bottom: 22px;
  padding-bottom: 10px;
}
.avatar-box { flex-shrink: 0; }
.avatar-placeholder {
  width: 92px; height: 116px;
  background: #2669c9;
  display: flex; align-items: center; justify-content: center;
}
.avatar-placeholder :deep(svg) { opacity: 0.8; }
.avatar-img {
  width: 92px;
  height: 116px;
  object-fit: cover;
  display: block;
}
.header-main { flex: 1; padding-top: 6px; }
.name-row { font-size: 28px; font-weight: bold; color: #111; letter-spacing: 1px; }
.name-label { font-weight: bold; }
.name-value { font-weight: bold; }
.job-title { font-size: 18px; color: #222; margin-top: 10px; font-weight: 500; }

.header-contact {
  flex-shrink: 0;
  padding-top: 10px;
  font-size: 15px;
  line-height: 1.95;
  color: #222;
  min-width: 260px;
}
.contact-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.contact-icon {
  color: #222;
  width: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding-top: 2px;
}
.contact-icon :deep(svg) { width: 18px; height: 18px; }
.contact-links a { color: #0b57d0; text-decoration: underline; }

/* ===== 模块标题 ===== */
.pdf-section { margin-bottom: 18px; }
.section-title {
  font-size: 20px;
  font-weight: bold;
  color: #111;
  margin: 14px 0 4px 0;
  padding: 0;
}
.section-divider {
  height: 2px;
  background: #222;
  margin-bottom: 10px;
}

/* ===== 条目 ===== */
.entry-block { margin-bottom: 12px; }
.entry-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: baseline;
  gap: 24px;
  margin-bottom: 4px;
}
.entry-heading { font-size: 17px; font-weight: bold; color: #111; }
.entry-sub { font-size: 15.5px; color: #222; }
.entry-date { font-size: 15px; color: #222; white-space: nowrap; text-align: right; }

.entry-body { margin-top: 4px; font-size: 14.5px; line-height: 1.7; color: #222; }
.entry-lead { margin: 4px 0; font-weight: 600; }

/* 圆点列表 */
.bullet-list {
  list-style: none;
  padding-left: 0;
  margin: 4px 0;
}
.bullet-list li {
  position: relative;
  padding-left: 18px;
  margin-bottom: 4px;
  line-height: 1.7;
}
.bullet-list li::before {
  content: "•";
  position: absolute;
  left: 4px;
  top: 0;
  font-size: 16px;
  line-height: 1.7;
  font-weight: bold;
}

.plain-text { margin: 4px 0; line-height: 1.8; font-size: 14.5px; }
</style>
