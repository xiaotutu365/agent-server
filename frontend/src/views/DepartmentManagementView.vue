<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>部门管理</h2>
        <p class="hint">管理部门；用户可归属于某个部门，便于组织结构管理。</p>
      </div>
      <button class="primary" @click="openAdd">+ 新建部门</button>
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
        <button class="save" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        <button class="ghost" @click="showForm = false">取消</button>
      </div>
    </div>

    <div class="card">
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
              <button class="link danger" @click="remove(d)">删除</button>
            </td>
          </tr>
          <tr v-if="!departments.length"><td colspan="4" class="empty">暂无部门</td></tr>
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
const showForm = ref(false)
const saving = ref(false)
const form = ref({ name: '', description: '' })

onMounted(load)

async function load() {
  error.value = ''
  try {
    const [r1, r2] = await Promise.all([
      apiFetch('/api/admin/departments'),
      apiFetch('/api/admin/users'),
    ])
    departments.value = (await r1.json()).departments || []
    users.value = (await r2.json()).users || []
  } catch (e) {
    error.value = e.message || String(e)
  }
}
function countByDept(did) {
  return users.value.filter((u) => u.department_id === did).length
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
.list-page { padding: 24px 28px; max-width: 100%; margin: 0 auto; width: 100%; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.hint { color: var(--muted); font-size: 13px; margin: 0; max-width: 720px; }
.primary { flex: none; border: none; background: var(--accent); color: #fff; padding: 10px 18px; border-radius: 9px; cursor: pointer; font-size: 14px; font-weight: 600; }
.err { background: #fde8e8; color: #d93025; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-top: 16px; }
.form .field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; font-size: 13px; color: var(--muted); }
.form .field input { border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; font-family: inherit; font-size: 14px; background: var(--bg); color: var(--text); }
.form .field input:focus { border-color: var(--accent); outline: none; }
.actions { display: flex; gap: 12px; }
.save { border: none; background: var(--accent); color: #fff; padding: 10px 20px; border-radius: 9px; cursor: pointer; font-size: 14px; font-weight: 600; }
.save:disabled { opacity: 0.55; cursor: not-allowed; }
.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); padding: 10px 18px; border-radius: 9px; cursor: pointer; font-size: 14px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--border); }
.tbl th { background: var(--code-bg); font-weight: 600; color: var(--muted); font-size: 12px; }
.tbl tr:last-child td { border-bottom: none; }
.name { font-weight: 600; }
.muted { color: var(--muted); }
.op { white-space: nowrap; }
.link { border: none; background: transparent; color: var(--accent); cursor: pointer; font-size: 13px; }
.link.danger { color: #d93025; }
.empty { text-align: center; color: var(--muted); padding: 24px 0; }
</style>
