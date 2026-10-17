<template>
  <div class="memory-page">
    <header class="page-head">
      <div>
        <h2>记忆</h2>
        <p class="desc">跨会话记住用户：对话后自动抽取，对话前检索注入。停用的记忆不再注入，删除即遗忘。</p>
      </div>
      <button class="btn" @click="showAdd = !showAdd">{{ showAdd ? '收起' : '手动添加' }}</button>
    </header>

    <div v-if="showAdd" class="card add-card">
      <textarea v-model="draft" rows="2" placeholder="例如：用户偏好简洁的回答（第三人称陈述句）"></textarea>
      <div class="add-actions">
        <span v-if="error" class="error">{{ error }}</span>
        <button class="btn primary" :disabled="!draft.trim() || adding" @click="submitAdd">添加</button>
      </div>
    </div>

    <div class="toolbar">
      <select v-model="filterUser" @change="load">
        <option value="">全部用户</option>
        <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
      </select>
      <select v-model="filterEnabled" @change="load">
        <option value="">全部状态</option>
        <option value="true">启用</option>
        <option value="false">停用</option>
      </select>
      <button class="btn" @click="load">刷新</button>
      <span class="count">共 {{ memories.length }} 条</span>
    </div>

    <p v-if="!memories.length" class="empty">暂无记忆。与智能体对话后，值得记住的信息会自动出现在这里。</p>

    <ul class="list">
      <li v-for="m in memories" :key="m.id" class="card item" :class="{ disabled: !m.enabled }">
        <div class="item-main">
          <p class="content">{{ m.content }}</p>
          <p class="meta">
            <span class="badge">{{ m.memory_type }}</span>
            <span>{{ fmtTime(m.created_at) }}</span>
            <span>来源：{{ m.source_thread === 'manual' ? '手动添加' : m.source_thread }}</span>
            <span>用户：{{ userName(m.user_id) }}</span>
          </p>
        </div>
        <div class="item-actions">
          <label class="switch-label">
            <input type="checkbox" :checked="m.enabled" @change="toggle(m)" />
            {{ m.enabled ? '启用' : '停用' }}
          </label>
          <button class="btn danger sm" @click="remove(m)">删除</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../auth'
import { addMemory, forgetMemory, listMemories, setMemoryEnabled } from '../api/memory'

const memories = ref([])
const users = ref([])
const filterUser = ref('')
const filterEnabled = ref('')
const showAdd = ref(false)
const draft = ref('')
const adding = ref(false)
const error = ref('')

function fmtTime(ts) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString()
}

function userName(id) {
  const u = users.value.find(u => u.id === id)
  return u ? u.username : id
}

async function load() {
  error.value = ''
  try {
    memories.value = await listMemories(filterUser.value, filterEnabled.value)
  } catch (e) {
    error.value = e.message
  }
}

async function loadUsers() {
  try {
    const r = await apiFetch('/api/admin/users')
    const data = await r.json().catch(() => ({}))
    if (r.ok) users.value = data.users || []
  } catch { /* 过滤下拉失败不阻塞列表 */ }
}

async function submitAdd() {
  adding.value = true
  error.value = ''
  try {
    await addMemory(draft.value.trim())
    draft.value = ''
    showAdd.value = false
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    adding.value = false
  }
}

async function toggle(m) {
  try {
    await setMemoryEnabled(m.id, !m.enabled)
    m.enabled = !m.enabled
  } catch (e) {
    error.value = e.message
  }
}

async function remove(m) {
  if (!confirm('确定遗忘这条记忆？删除后不可恢复。')) return
  try {
    await forgetMemory(m.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(() => { load(); loadUsers() })
</script>

<style scoped>
.memory-page { display: flex; flex-direction: column; gap: 14px; max-width: 900px; margin: 0 auto; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.page-head h2 { margin: 0 0 4px; }
.desc { margin: 0; color: var(--muted); font-size: 13px; }

.card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 16px;
}
.add-card { display: flex; flex-direction: column; gap: 10px; }
.add-card textarea { width: 100%; resize: vertical; }
.add-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.error { color: var(--danger, #e5484d); font-size: 13px; }

.toolbar { display: flex; align-items: center; gap: 10px; }
.count { color: var(--muted); font-size: 13px; margin-left: auto; }
.empty { color: var(--muted); text-align: center; padding: 40px 0; }

.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.item { display: flex; align-items: center; gap: 14px; }
.item.disabled .content { color: var(--muted); text-decoration: line-through; }
.item-main { flex: 1; min-width: 0; }
.content { margin: 0 0 6px; word-break: break-word; }
.meta { margin: 0; display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 12px; align-items: center; }
.badge {
  background: color-mix(in srgb, var(--primary) 14%, transparent);
  color: var(--primary-strong); border-radius: 999px; padding: 1px 8px; font-size: 11px;
}
.item-actions { display: flex; align-items: center; gap: 12px; flex: none; }
.switch-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-2); cursor: pointer; }
.switch-label input { accent-color: var(--primary-strong); }

.btn {
  border: 1px solid var(--border); background: var(--panel-hover, var(--panel));
  color: var(--text); border-radius: var(--radius-sm); padding: 7px 14px;
  font-family: inherit; font-size: 13px; cursor: pointer;
}
.btn:hover { border-color: var(--primary-strong); }
.btn.primary { background: var(--primary-strong); border-color: var(--primary-strong); color: #fff; }
.btn.danger { color: var(--danger, #e5484d); border-color: var(--danger, #e5484d); }
.btn.sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }

select, textarea { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: var(--radius-sm); padding: 7px 10px; font-family: inherit; font-size: 13px; }
</style>
