<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>角色管理</h2>
        <p class="hint">管理系统角色。key 为权限标识（如 admin 可进后台）；用户通过角色关联使用对应权限。</p>
      </div>
      <button class="btn btn-primary" @click="openAdd">+ 新建角色</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="showForm" class="card form">
      <label class="field">
        <span>角色名称</span>
        <input v-model="form.name" placeholder="如 经理" />
      </label>
      <label class="field">
        <span>角色 key（唯一标识，字母/数字/下划线）</span>
        <input v-model="form.key" placeholder="如 manager" />
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
          <tr><th>名称</th><th>key</th><th>描述</th><th>用户数</th><th class="op">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in roles" :key="r.id">
            <td class="name">{{ r.name }}</td>
            <td class="mono">{{ r.key }}</td>
            <td class="muted">{{ r.description || '—' }}</td>
            <td class="muted">{{ countByRole(r.id) }}</td>
            <td class="op">
              <button v-if="!builtin(r.key)" class="link link-danger" @click="remove(r)">删除</button>
              <span v-else class="muted">内置</span>
            </td>
          </tr>
          <tr v-if="loading"><td colspan="5" class="empty" role="status">加载中…</td></tr>
          <tr v-else-if="!roles.length"><td colspan="5" class="empty" role="status">暂无角色</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../auth'

const roles = ref([])
const users = ref([])
const error = ref('')
const loading = ref(false)
const showForm = ref(false)
const saving = ref(false)
const form = ref({ name: '', key: '', description: '' })

onMounted(load)

async function load() {
  error.value = ''
  loading.value = true
  try {
    const [r1, r2] = await Promise.all([
      apiFetch('/api/admin/roles'),
      apiFetch('/api/admin/users'),
    ])
    roles.value = (await r1.json()).roles || []
    users.value = (await r2.json()).users || []
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}
function countByRole(rid) {
  return users.value.filter((u) => u.role_id === rid).length
}
function builtin(key) {
  return key === 'admin' || key === 'user'
}

function openAdd() {
  showForm.value = true
}

async function save() {
  if (!form.value.name.trim() || !form.value.key.trim()) {
    error.value = '名称和 key 必填'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/roles', {
      method: 'POST',
      body: JSON.stringify({
        name: form.value.name.trim(),
        key: form.value.key.trim(),
        description: form.value.description.trim(),
      }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '创建失败')
    }
    showForm.value = false
    form.value = { name: '', key: '', description: '' }
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

async function remove(r) {
  if (!confirm(`确定删除角色「${r.name}」？其下用户将回退为普通用户。`)) return
  error.value = ''
  try {
    const resp = await apiFetch(`/api/admin/roles/${r.id}`, { method: 'DELETE' })
    if (!resp.ok) {
      const d = await resp.json().catch(() => ({}))
      throw new Error(d.detail || '删除失败')
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
