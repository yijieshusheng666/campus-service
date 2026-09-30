<template>
  <div class="ann-admin-page">
    <div class="page-header">
      <h2>公告管理</h2>
      <el-button type="primary" @click="openEdit(null)">发布公告</el-button>
    </div>

    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="标题" min-width="200">
        <template #default="{ row }">
          <el-tag v-if="row.is_pinned" type="danger" size="small" effect="dark" class="pin-tag">置顶</el-tag>
          {{ row.title }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_online ? 'success' : 'info'" size="small">
            {{ row.is_online ? '已上架' : '已下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发布时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" :type="row.is_online ? 'warning' : 'success'" @click="onToggleOnline(row)">
            {{ row.is_online ? '下架' : '上架' }}
          </el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="editVisible" :title="editForm.id ? '编辑公告' : '发布公告'" width="640px">
      <el-form label-width="70px">
        <el-form-item label="标题" required>
          <el-input v-model="editForm.title" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="正文" required>
          <el-input v-model="editForm.content" type="textarea" :rows="8" maxlength="10000" show-word-limit />
        </el-form-item>
        <el-form-item label="置顶">
          <el-switch v-model="editForm.is_pinned" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  manageAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement
} from '@/api/announcement'

const items = ref([])
const loading = ref(false)
const saving = ref(false)
const editVisible = ref(false)
const editForm = reactive({ id: null, title: '', content: '', is_pinned: false })

function fmtTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : ''
}

// 管理端走 /manage 接口：含已下架公告和正文，与用户端列表（仅已上架、无正文）分开
async function fetchList() {
  loading.value = true
  try {
    const res = await manageAnnouncements()
    items.value = res.data
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  if (row) {
    Object.assign(editForm, {
      id: row.id,
      title: row.title,
      content: row.content || '',
      is_pinned: row.is_pinned
    })
  } else {
    Object.assign(editForm, { id: null, title: '', content: '', is_pinned: false })
  }
  editVisible.value = true
}

async function onSave() {
  if (!editForm.title.trim() || !editForm.content.trim()) {
    ElMessage.warning('标题和正文不能为空')
    return
  }
  saving.value = true
  try {
    if (editForm.id) {
      await updateAnnouncement(editForm.id, {
        title: editForm.title,
        content: editForm.content,
        is_pinned: editForm.is_pinned
      })
      ElMessage.success('已保存')
    } else {
      await createAnnouncement({ title: editForm.title, content: editForm.content, is_pinned: editForm.is_pinned })
      ElMessage.success('已发布')
    }
    editVisible.value = false
    fetchList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onToggleOnline(row) {
  await updateAnnouncement(row.id, { is_online: !row.is_online })
  ElMessage.success(row.is_online ? '已下架' : '已上架')
  fetchList()
}

async function onDelete(row) {
  ElMessageBox.confirm(`确定删除公告「${row.title}」吗？`, '提示', {
    type: 'warning',
    confirmButtonClass: 'el-button--danger'
  }).then(async () => {
    await deleteAnnouncement(row.id)
    ElMessage.success('已删除')
    fetchList()
  }).catch(() => {})
}

onMounted(fetchList)
</script>

<style scoped>
.ann-admin-page { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; color: #1d2129; }
.pin-tag { margin-right: 6px; }
</style>
