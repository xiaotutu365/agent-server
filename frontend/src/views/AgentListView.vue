<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>Agent 管理</h2>
        <p class="hint">管理多个 Agent 配置；聊天固定使用「默认」标记的那个。新增/编辑可配置基本信息、工具关联与 HITL。</p>
      </div>
      <button class="btn btn-primary" @click="goNew">+ 新建 Agent</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="card tbl-card">
      <table class="tbl">
        <thead>
          <tr>
            <th>名称</th>
            <th>模型</th>
            <th>温度</th>
            <th>工具数</th>
            <th>记忆/知识库</th>
            <th>默认</th>
            <th>更新时间</th>
            <th class="op">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id">
            <td class="name">{{ a.name }}</td>
            <td class="mono">{{ a.model_name }}</td>
            <td>{{ a.temperature }}</td>
            <td>{{ (a.tools_enabled || []).length }}</td>
            <td>
              <span class="tag" :class="{ on: a.memory_enabled }">记忆 {{ a.memory_enabled ? '开' : '关' }}</span>
              <span class="tag" :class="{ on: a.kb_enabled }">知识库 {{ a.kb_enabled ? '开' : '关' }}</span>
            </td>
            <td>
              <span v-if="a.is_default" class="badge badge-primary">默认</span>
              <span v-else class="muted">—</span>
            </td>
            <td class="muted">{{ fmt(a.updated_at) }}</td>
            <td class="op">
              <button class="link" @click="goEdit(a.id)">编辑</button>
              <button v-if="!a.is_default" class="link" @click="setDefault(a.id)">设为默认</button>
              <button class="link link-danger" @click="remove(a)">删除</button>
            </td>
          </tr>
          <tr v-if="loading"><td colspan="8" class="empty" role="status">加载中…</td></tr>
          <tr v-else-if="!agents.length">
            <td colspan="8" class="empty" role="status">暂无 Agent，点击右上角「新建 Agent」。</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../auth'

const router = useRouter()
const agents = ref([])
const error = ref('')
const loading = ref(false)

onMounted(load)

async function load() {
  error.value = ''
  loading.value = true
  try {
    const r = await apiFetch('/api/admin/agents')
    if (!r.ok) throw new Error('加载失败')
    const data = await r.json()
    agents.value = data.agents || []
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

function goNew() {
  router.push('/admin/agents/new')
}
function goEdit(id) {
  router.push(`/admin/agents/${id}`)
}
async function setDefault(id) {
  if (!confirm('将该 Agent 设为默认？此后台对话将使用它。')) return
  try {
    const r = await apiFetch(`/api/admin/agents/${id}/set-default`, { method: 'POST' })
    if (!r.ok) throw new Error('操作失败')
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  }
}
async function remove(a) {
  if (!confirm(`确定删除「${a.name}」？此操作不可恢复。`)) return
  error.value = ''
  try {
    const r = await apiFetch(`/api/admin/agents/${a.id}`, { method: 'DELETE' })
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
.tag { margin-right: 6px; }
.tag.on { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }
.op { display: flex; align-items: center; gap: 10px; }
</style>
