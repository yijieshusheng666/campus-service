<template>
  <span
    ref="elRef"
    class="editable-text"
    :class="{ editing: isEditing, placeholder: !displayValue }"
    :style="{ fontSize: size ? size + 'px' : undefined, fontWeight: bold ? 'bold' : undefined }"
    @click="startEdit"
  >{{ displayValue || placeholder }}</span>
  <Teleport to="body" v-if="isEditing">
    <input
      ref="inputRef"
      v-model="draft"
      class="editable-inline-input"
      :style="{
        fontSize: size ? size + 'px' : undefined,
        fontWeight: bold ? 'bold' : undefined,
        left: rect.left + 'px',
        top: rect.top + 'px',
        width: Math.max(rect.width, 120) + 'px',
        fontFamily: 'inherit'
      }"
      @blur="commit"
      @keydown.enter.prevent="commit"
      @keydown.esc="cancel"
    />
  </Teleport>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'

const props = defineProps({
  value: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  bold: { type: Boolean, default: false },
  size: { type: Number, default: 0 }
})
const emit = defineEmits(['update'])

const elRef = ref(null)
const inputRef = ref(null)
const isEditing = ref(false)
const draft = ref('')
const rect = ref({ left: 0, top: 0, width: 100, height: 30 })

const displayValue = computed(() => (props.value ?? '').toString())

function startEdit() {
  if (!elRef.value) return
  const r = elRef.value.getBoundingClientRect()
  rect.value = { left: r.left, top: r.top, width: r.width, height: r.height }
  draft.value = props.value ?? ''
  isEditing.value = true
  nextTick(() => {
    inputRef.value?.focus()
    inputRef.value?.select()
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
  if (inputRef.value && !inputRef.value.contains(e.target) && elRef.value && !elRef.value.contains(e.target)) {
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
.editable-inline-input {
  position: fixed;
  z-index: 9999;
  margin: 0;
  padding: 1px 4px;
  border: 1px solid #409eff;
  border-radius: 3px;
  background: #fff;
  outline: none;
  color: #111;
  line-height: 1.4;
  box-shadow: 0 0 0 2px rgba(64,158,255,0.15);
}
</style>