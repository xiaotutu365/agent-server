<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>部门管理</h2>
        <p class="hint">管理部门；用户可归属于某个部门，便于组织结构管理。</p>
      </div>
      <button class="btn btn-primary" @click="openAdd">+ 新建部门</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="showForm" class="card form">
      <label class="field">
        <span>部门名称</span>
        <input v-model="form.name" placeholder="如 研发部" />
      </label>
      <label class="field">
        <span>描述</span>
        <input v-model="form.description" placeholder="可选" />
      </label>
      <div class="actions">
        <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        <button class="btn btn-ghost" @click="showForm = false">取消</button>
      </div>
    </div>

    <div class="card tbl-card">
      <table class="tbl">
        <thead>
          <tr><th>名称</th><th>描述</th><th>用户数</th><th class="op">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in departments" :key="d.id">
            <td class="name">{{ d.name }}</td>
            <td class="muted">{{ d.description || '—' }}</td>
            <td class="muted">{{ countByDept(d.id) }}</td>
            <td class="op">
              <button class="link link-danger" @click="remove(d)">删除</button>
            </td>
          </tr>
          <tr v-if="loading"><td colspan="4" class="empty" role="status">加载中…</td></tr>
          <tr v-else-if="!departments.length"><td colspan="4" class="empty" role="status">暂无部门</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../auth'

const departments = ref([])
const users = ref([])
const error = ref('')
const loading = ref(false)
const showForm = ref(false)
const saving = ref(false)
const form = ref({ name: '', description: '' })

onMounted(load)

async function load() {
  error.value = ''
  loading.value = true
  try {
    const [r1, r2] = await Promise.all([
      apiFetch('/api/admin/departments'),
      apiFetch('/api/admin/users'),
    ])
    departments.value = (await r1.json()).departments || []
    users.value = (await r2.json()).users || []
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}
function countByDept(did) {
  return users.value.filter((u) => u.department_id === did).length
}

function openAdd() {
  showForm.value = true
}

async function save() {
  if (!form.value.name.trim()) {
    error.value = '部门名称必填'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/departments', {
      method: 'POST',
      body: JSON.stringify({
        name: form.value.name.trim(),
        description: form.value.description.trim(),
      }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '创建失败')
    }
    showForm.value = false
    form.value = { name: '', description: '' }
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

async function remove(d) {
  if (!confirm(`确定删除部门「${d.name}」？其下用户将解除部门关联。`)) return
  error.value = ''
  try {
    const resp = await apiFetch(`/api/admin/departments/${d.id}`, { method: 'DELETE' })
    if (!resp.ok) {
      const d2 = await resp.json().catch(() => ({}))
      throw new Error(d2.detail || '删除失败')
    }
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  }
}
</script>

<style scoped>
.form { padding: 16px 18px; margin-top: 16px; }
.actions { display: flex; gap: 12px; }
</style>
