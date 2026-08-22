<template>
  <div class="editable-textarea-wrap">
    <div
      v-if="!isEditing"
      ref="displayRef"
      class="editable-textarea-display"
      :class="{ placeholder: !displayValue }"
      @click="startEdit"
    >
      <template v-if="displayValue">
        <template v-for="(block, bi) in parsedContent" :key="bi">
          <div v-if="block.lead" class="lead-line">{{ block.lead }}</div>
          <div v-for="(b, li) in block.bullets" :key="li" class="bullet-line">{{ b }}</div>
        </template>
      </template>
      <template v-else>{{ placeholder }}</template>
    </div>
    <Teleport to="body" v-if="isEditing">
      <textarea
        ref="inputRef"
        v-model="draft"
        class="editable-textarea-input-global"
        :style="{
          left: rect.left + 'px',
          top: rect.top + 'px',
          width: rect.width + 'px',
          minHeight: Math.max(rect.height, 100) + 'px',
          fontFamily: 'inherit'
        }"
        @blur="commit"
        @keydown.esc="cancel"
      ></textarea>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'

const props = defineProps({
  value: { type: String, default: '' },
  placeholder: { type: String, default: '' }
})
const emit = defineEmits(['update'])

const displayRef = ref(null)
const inputRef = ref(null)
const isEditing = ref(false)
const draft = ref('')
const rect = ref({ left: 0, top: 0, width: 500, height: 100 })

const displayValue = computed(() => (props.value ?? '').toString())

const parsedContent = computed(() => parseContent(displayValue.value))

function parseContent(text) {
  if (!text) return []
  const blocks = []
  const paragraphs = String(text).split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
  for (const para of paragraphs) {
    const lines = para.split('\n').map(l => l.trim()).filter(Boolean)
    if (!lines.length) continue
    let bullets = []
    let lead = ''
    let seenBullet = false
    for (const line of lines) {
      const stripped = line.replace(/^[•·●\-\*\d+\.)\s]+/, '').trim()
      const isBullet = /^[•·●\-\*]/.test(line)
      if (isBullet || seenBullet) {
        seenBullet = true
        if (stripped) bullets.push(stripped)
      } else {
        lead = (lead ? lead + ' ' : '') + stripped
      }
    }
    if (!lead && !bullets.length) {
      lead = lines.join(' ')
    }
    blocks.push({ lead, bullets })
  }
  return blocks
}

function startEdit() {
  if (!displayRef.value) return
  const r = displayRef.value.getBoundingClientRect()
  rect.value = { left: r.left, top: r.top, width: Math.max(r.width, 500), height: r.height }
  draft.value = props.value ?? ''
  isEditing.value = true
  nextTick(() => {
    inputRef.value?.focus()
    const len = draft.value.length
    inputRef.value?.setSelectionRange(len, len)
  })
}

function commit() {
  if (!isEditing.value) return
  isEditing.value = false
  emit('update', draft.value)
}

function cancel() {
  isEditing.value = false
}

function onDocClick(e) {
  if (!isEditing.value) return
  if (inputRef.value && !inputRef.value.contains(e.target) && displayRef.value && !displayRef.value.contains(e.target)) {
    commit()
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('mousedown', onDocClick)
}
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('mousedown', onDocClick)
  }
})
</script>

<style>
.editable-textarea-input-global {
  position: fixed;
  z-index: 9999;
  padding: 6px 8px;
  border: 1px solid #409eff;
  border-radius: 4px;
  background: #fff;
  outline: none;
  color: #111;
  font-size: 14.5px;
  line-height: 1.7;
  resize: vertical;
  box-sizing: border-box;
  box-shadow: 0 0 0 2px rgba(64,158,255,0.15);
}
</style>