<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>用户管理</h2>
        <p class="hint">仅管理员可访问。可创建普通用户（用于前台聊天）或更多管理员，并关联角色与部门。</p>
      </div>
      <button class="btn btn-primary" @click="openAdd">+ 新建用户</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="showForm" class="card form">
      <label class="field">
        <span>用户名 *</span>
        <input v-model="form.username" placeholder="2–32 位字母、数字、下划线或连字符" />
        <span v-if="fieldErrors.username" class="field-err">{{ fieldErrors.username }}</span>
      </label>
      <label class="field">
        <span>密码 *</span>
        <input v-model="form.password" type="password" placeholder="6–64 位，需同时包含字母和数字" />
        <span v-if="fieldErrors.password" class="field-err">{{ fieldErrors.password }}</span>
      </label>
      <label class="field">
        <span>姓名</span>
        <input v-model="form.full_name" placeholder="真实姓名（选填，≤50 字）" />
        <span v-if="fieldErrors.full_name" class="field-err">{{ fieldErrors.full_name }}</span>
      </label>
      <label class="field">
        <span>邮箱</span>
        <input v-model="form.email" type="email" placeholder="user@example.com（选填，需唯一）" />
        <span v-if="fieldErrors.email" class="field-err">{{ fieldErrors.email }}</span>
      </label>
      <label class="field">
        <span>电话</span>
        <input v-model="form.phone" placeholder="13800138000（选填）" />
        <span v-if="fieldErrors.phone" class="field-err">{{ fieldErrors.phone }}</span>
      </label>
      <label class="field">
        <span>角色</span>
        <select v-model="form.role_id">
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}（{{ r.key }}）</option>
        </select>
      </label>
      <label class="field">
        <span>部门</span>
        <select v-model="form.department_id">
          <option :value="null">— 无 —</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </label>
      <div class="actions">
        <button class="btn btn-primary" :disabled="creating" @click="create">{{ creating ? '创建中…' : '创建' }}</button>
        <button class="btn btn-ghost" @click="showForm = false">取消</button>
      </div>
    </div>

    <div v-if="editing" class="card form">
      <div class="edit-title">编辑：{{ editing.username }}</div>
      <label class="field">
        <span>姓名</span>
        <input v-model="editForm.full_name" placeholder="留空则清空" />
        <span v-if="editErrors.full_name" class="field-err">{{ editErrors.full_name }}</span>
      </label>
      <label class="field">
        <span>邮箱</span>
        <input v-model="editForm.email" type="email" placeholder="留空则清空" />
        <span v-if="editErrors.email" class="field-err">{{ editErrors.email }}</span>
      </label>
      <label class="field">
        <span>电话</span>
        <input v-model="editForm.phone" placeholder="留空则清空" />
        <span v-if="editErrors.phone" class="field-err">{{ editErrors.phone }}</span>
      </label>
      <label class="field">
        <span>角色</span>
        <select v-model="editForm.role_id">
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}（{{ r.key }}）</option>
        </select>
      </label>
      <label class="field">
        <span>部门</span>
        <select v-model="editForm.department_id">
          <option :value="null">— 无 —</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </label>
      <label class="field">
        <span>重置密码（留空则不修改）</span>
        <input v-model="editForm.password" type="password" placeholder="留空保持不变" />
        <span v-if="editErrors.password" class="field-err">{{ editErrors.password }}</span>
      </label>
      <div class="actions">
        <button class="btn btn-primary" :disabled="saving" @click="saveEdit">{{ saving ? '保存中…' : '保存' }}</button>
        <button class="btn btn-ghost" @click="editing = null">取消</button>
      </div>
    </div>

    <div class="card tbl-card">
      <table class="tbl">
        <thead>
          <tr><th>用户名</th><th>姓名</th><th>邮箱</th><th>角色</th><th>部门</th><th>创建时间</th><th class="op">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="name">{{ u.username }}</td>
            <td class="muted">{{ u.full_name || '—' }}</td>
            <td class="muted">{{ u.email || '—' }}</td>
            <td>
              <span class="tag" :class="{ on: u.role === 'admin' }">
                {{ u.role_name || (u.role === 'admin' ? '管理员' : '普通用户') }}
              </span>
            </td>
            <td class="muted">{{ u.department_name || '—' }}</td>
            <td class="muted">{{ fmt(u.created_at) }}</td>
            <td class="op">
              <button class="link" @click="openEdit(u)">编辑</button>
              <button v-if="u.id !== meId" class="link link-danger" @click="remove(u)">删除</button>
              <span v-else class="muted">当前账号</span>
            </td>
          </tr>
          <tr v-if="loading"><td colspan="7" class="empty" role="status">加载中…</td></tr>
          <tr v-else-if="!users.length"><td colspan="7" class="empty" role="status">暂无用户</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch, getUser } from '../auth'

const users = ref([])
const roles = ref([])
const departments = ref([])
const error = ref('')
const loading = ref(false)
const showForm = ref(false)
const creating = ref(false)
const form = ref({ username: '', password: '', full_name: '', email: '', phone: '', role_id: '', department_id: null })
const fieldErrors = ref({})
const editing = ref(null)
const saving = ref(false)
const editForm = ref({ full_name: '', email: '', phone: '', role_id: '', department_id: null, password: '' })
const editErrors = ref({})
const meId = ref((getUser() || {}).id)

// 与后端 agent/auth.py 的校验规则保持一致
const USERNAME_RE = /^[a-zA-Z0-9_-]{2,32}$/
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const PHONE_RE = /^\+?[\d\-() ]{5,20}$/

function validateFields(values, { requireIdentity = false } = {}) {
  const errs = {}
  if (requireIdentity) {
    const name = (values.username || '').trim()
    if (!name) errs.username = '用户名必填'
    else if (!USERNAME_RE.test(name)) errs.username = '用户名需为 2–32 位字母、数字、下划线或连字符'
    const pw = values.password || ''
    if (!pw) errs.password = '密码必填'
    else if (pw.length < 6 || pw.length > 64) errs.password = '密码长度需为 6–64 位'
    else if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) errs.password = '密码需同时包含字母和数字'
  } else if (values.password) {
    const pw = values.password
    if (pw.length < 6 || pw.length > 64) errs.password = '密码长度需为 6–64 位'
    else if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) errs.password = '密码需同时包含字母和数字'
  }
  const email = (values.email || '').trim()
  if (email && (email.length > 254 || !EMAIL_RE.test(email))) errs.email = '邮箱格式不正确'
  const phone = (values.phone || '').trim()
  if (phone && !PHONE_RE.test(phone)) errs.phone = '电话格式不正确（可含 +、数字、空格、连字符、括号）'
  const fn = (values.full_name || '').trim()
  if (fn.length > 50) errs.full_name = '姓名不能超过 50 个字符'
  return errs
}

onMounted(() => {
  load()
  form.value.role_id = defaultRoleId()
})

async function load() {
  error.value = ''
  loading.value = true
  try {
    const [ru, rr, rd] = await Promise.all([
      apiFetch('/api/admin/users'),
      apiFetch('/api/admin/roles'),
      apiFetch('/api/admin/departments'),
    ])
    users.value = (await ru.json()).users || []
    roles.value = (await rr.json()).roles || []
    departments.value = (await rd.json()).departments || []
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

function defaultRoleId() {
  const admin = roles.value.find((r) => r.key === 'user') || roles.value[0]
  return admin ? admin.id : ''
}

async function create() {
  fieldErrors.value = validateFields(form.value, { requireIdentity: true })
  if (Object.keys(fieldErrors.value).length) return
  creating.value = true
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({
        username: form.value.username.trim(),
        password: form.value.password,
        role_id: form.value.role_id || null,
        department_id: form.value.department_id || null,
        email: form.value.email.trim() || null,
        phone: form.value.phone.trim() || null,
        full_name: form.value.full_name.trim() || null,
      }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '创建失败')
    }
    showForm.value = false
    form.value = { username: '', password: '', full_name: '', email: '', phone: '', role_id: defaultRoleId(), department_id: null }
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

function openAdd() {
  showForm.value = true
  fieldErrors.value = {}
  form.value.role_id = defaultRoleId()
}

function openEdit(u) {
  editing.value = u
  editErrors.value = {}
  editForm.value = {
    full_name: u.full_name || '',
    email: u.email || '',
    phone: u.phone || '',
    role_id: u.role_id || defaultRoleId(),
    department_id: u.department_id || null,
    password: '',
  }
}

async function saveEdit() {
  if (!editing.value) return
  editErrors.value = validateFields(editForm.value)
  if (Object.keys(editErrors.value).length) return
  saving.value = true
  error.value = ''
  try {
    const body = {
      role_id: editForm.value.role_id || null,
      department_id: editForm.value.department_id || null,
      email: (editForm.value.email || '').trim(),
      phone: (editForm.value.phone || '').trim(),
      full_name: (editForm.value.full_name || '').trim(),
    }
    if (editForm.value.password) body.password = editForm.value.password
    const r = await apiFetch(`/api/admin/users/${editing.value.id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '保存失败')
    }
    editing.value = null
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
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
.form { padding: 16px 18px; margin-top: 16px; }
.edit-title { font-weight: 600; margin-bottom: 12px; font-size: 14px; }
.actions { display: flex; gap: 12px; }
.tag.on { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }
.op { display: flex; align-items: center; gap: 10px; }
.field-err { color: var(--destructive); font-size: 12px; }
</style>
