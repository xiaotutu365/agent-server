<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>用户管理</h2>
        <p class="hint">仅管理员可访问。可创建普通用户（用于前台聊天）或更多管理员。</p>
      </div>
      <button class="primary" @click="showForm = !showForm">+ 新建用户</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="showForm" class="card form">
      <label class="field">
        <span>用户名</span>
        <input v-model="form.username" placeholder="登录用户名" />
      </label>
      <label class="field">
        <span>密码</span>
        <input v-model="form.password" type="password" placeholder="登录密码" />
      </label>
      <label class="field">
        <span>角色</span>
        <select v-model="form.role">
          <option value="user">普通用户（仅前台聊天）</option>
          <option value="admin">管理员（含后台）</option>
        </select>
      </label>
      <div class="actions">
        <button class="save" :disabled="creating" @click="create">{{ creating ? '创建中…' : '创建' }}</button>
        <button class="ghost" @click="showForm = false">取消</button>
      </div>
    </div>

    <div class="card">
      <table class="tbl">
        <thead>
          <tr><th>用户名</th><th>角色</th><th>创建时间</th><th class="op">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="name">{{ u.username }}</td>
            <td>
              <span class="tag" :class="{ on: u.role === 'admin' }">
                {{ u.role === 'admin' ? '管理员' : '普通用户' }}
              </span>
            </td>
            <td class="muted">{{ fmt(u.created_at) }}</td>
            <td class="op">
              <button v-if="u.id !== meId" class="link danger" @click="remove(u)">删除</button>
              <span v-else class="muted">当前账号</span>
            </td>
          </tr>
          <tr v-if="!users.length"><td colspan="4" class="empty">暂无用户</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch, getUser } from '../auth'

const users = ref([])
const error = ref('')
const showForm = ref(false)
const creating = ref(false)
const form = ref({ username: '', password: '', role: 'user' })
const meId = ref((getUser() || {}).id)

onMounted(load)

async function load() {
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/users')
    const d = await r.json()
    users.value = d.users || []
  } catch (e) {
    error.value = e.message || String(e)
  }
}

async function create() {
  if (!form.value.username.trim() || !form.value.password) {
    error.value = '用户名和密码必填'
    return
  }
  creating.value = true
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ ...form.value, username: form.value.username.trim() }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '创建失败')
    }
    showForm.value = false
    form.value = { username: '', password: '', role: 'user' }
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

async function remove(u) {
  if (!confirm(`确定删除用户「${u.username}」？`)) return
  error.value = ''
  try {
    const r = await apiFetch(`/api/admin/users/${u.id}`, { method: 'DELETE' })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '删除失败')
    }
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  }
}

function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.list-page { padding: 24px 28px; max-width: 100%; margin: 0 auto; width: 100%; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.hint { color: var(--muted); font-size: 13px; margin: 0; }
.primary { flex: none; border: none; background: var(--accent); color: #fff; padding: 10px 18px; border-radius: 9px; cursor: pointer; font-size: 14px; font-weight: 600; }
.err { background: #fde8e8; color: #d93025; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-top: 16px; }
.form .field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; font-size: 13px; color: var(--muted); }
.form .field input, .form .field select { border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; font-family: inherit; font-size: 14px; background: var(--bg); color: var(--text); }
.form .field input:focus, .form .field select:focus { border-color: var(--accent); outline: none; }
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
.tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 20px; background: var(--code-bg); color: var(--muted); }
.tag.on { background: #e6f4ec; color: #22a06b; }
.op { white-space: nowrap; }
.link { border: none; background: transparent; color: var(--accent); cursor: pointer; font-size: 13px; }
.link.danger { color: #d93025; }
.empty { text-align: center; color: var(--muted); padding: 24px 0; }
</style>
