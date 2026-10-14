<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>Agent 管理</h2>
        <p class="hint">管理多个 Agent 配置；聊天固定使用「默认」标记的那个。新增/编辑可配置基本信息、工具关联与 HITL。</p>
      </div>
      <button class="primary" @click="goNew">+ 新建 Agent</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="card">
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
              <span v-if="a.is_default" class="badge-def">默认</span>
              <span v-else class="muted">—</span>
            </td>
            <td class="muted">{{ fmt(a.updated_at) }}</td>
            <td class="op">
              <button class="link" @click="goEdit(a.id)">编辑</button>
              <button v-if="!a.is_default" class="link" @click="setDefault(a.id)">设为默认</button>
              <button class="link danger" @click="remove(a)">删除</button>
            </td>
          </tr>
          <tr v-if="!agents.length">
            <td colspan="8" class="empty">暂无 Agent，点击右上角「新建 Agent」。</td>
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

onMounted(load)

async function load() {
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/agents')
    if (!r.ok) throw new Error('加载失败')
    const data = await r.json()
    agents.value = data.agents || []
  } catch (e) {
    error.value = e.message || String(e)
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
.list-page { padding: 24px 28px; max-width: 100%; margin: 0 auto; width: 100%; }
.page-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 18px;
}
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.hint { color: var(--muted); font-size: 13px; margin: 0; max-width: 640px; }
.primary {
  flex: none; border: none; background: var(--accent); color: #fff;
  padding: 10px 18px; border-radius: 9px; cursor: pointer; font-size: 14px; font-weight: 600;
}
.err { background: #fde8e8; color: #d93025; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--border); }
.tbl th { background: var(--code-bg); font-weight: 600; color: var(--muted); font-size: 12px; }
.tbl tr:last-child td { border-bottom: none; }
.name { font-weight: 600; }
.mono { font-family: var(--mono); font-size: 12px; color: var(--accent); }
.muted { color: var(--muted); }
.tag {
  display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 20px;
  background: var(--code-bg); color: var(--muted); margin-right: 6px;
}
.tag.on { background: #e6f4ec; color: #22a06b; }
.badge-def {
  display: inline-block; font-size: 11px; padding: 2px 10px; border-radius: 20px;
  background: var(--accent); color: #fff;
}
.op { white-space: nowrap; }
.link {
  border: none; background: transparent; color: var(--accent); cursor: pointer;
  font-size: 13px; padding: 0 8px 0 0; margin-right: 4px;
}
.link.danger { color: #d93025; }
.empty { text-align: center; color: var(--muted); padding: 30px 0; }
</style>
