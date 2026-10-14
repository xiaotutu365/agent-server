<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>MCP 服务器</h2>
        <p class="hint">
          挂载外部 MCP 服务器即可把其工具并入<b>所选 Agent</b>（无需改代码）。可对每个服务器设
          <b>allow_roles</b> 做越权闸（如仅 admin 可调）。保存后该 Agent 热重建生效
          （默认 Agent 即聊天使用的 Agent）。
        </p>
      </div>
    </div>

    <div class="agent-pick">
      <span>选择 Agent：</span>
      <select v-model="selectedAgentId" @change="onAgentChange">
        <option v-for="a in agents" :key="a.id" :value="a.id">
          {{ a.name }}{{ a.is_default ? '（默认）' : '' }}
        </option>
      </select>
      <span v-if="loadingAgent" class="muted">加载中…</span>
    </div>

    <div v-if="mcpError" class="err">{{ mcpError }}</div>

    <McpServers v-if="selectedAgentId" v-model="servers" />

    <div v-if="selectedAgentId && changed" class="savebar">
      <span class="changed">{{ changedCount }} 项改动未保存（{{ currentName }}）</span>
      <span class="spacer"></span>
      <button class="ghost" @click="revert">撤销</button>
      <button class="save" :disabled="saving" @click="saveServers">
        {{ saving ? '保存中…' : '保存并热重建' }}
      </button>
      <span v-if="savedMsg" class="saved">{{ savedMsg }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '../auth'
import McpServers from '../components/McpServers.vue'

// ---------------- MCP 服务器（可切换 Agent） ----------------
const agents = ref([])
const selectedAgentId = ref('')
const agentConfig = ref(null)
const servers = ref([])
const originalServers = ref('')
const mcpError = ref('')
const loadingAgent = ref(false)
const saving = ref(false)
const savedMsg = ref('')

onMounted(loadAgents)

async function loadAgents() {
  mcpError.value = ''
  try {
    const r = await apiFetch('/api/admin/agents')
    if (!r.ok) throw new Error('加载 Agent 列表失败')
    const { agents: list } = await r.json()
    agents.value = list || []
    const def = agents.value.find((a) => a.is_default) || agents.value[0]
    if (!def) throw new Error('未找到任何 Agent')
    await loadAgent(def.id)
  } catch (e) {
    mcpError.value = e.message || String(e)
  }
}

async function loadAgent(id) {
  loadingAgent.value = true
  try {
    const r = await apiFetch(`/api/admin/agents/${id}`)
    if (!r.ok) throw new Error('加载 Agent 失败')
    const data = await r.json()
    agentConfig.value = data.agent
    servers.value = JSON.parse(JSON.stringify(agentConfig.value.mcp_servers || []))
    originalServers.value = JSON.stringify(servers.value)
    selectedAgentId.value = id
    mcpError.value = ''
  } catch (e) {
    mcpError.value = e.message || String(e)
  } finally {
    loadingAgent.value = false
  }
}

function onAgentChange() {
  if (selectedAgentId.value) loadAgent(selectedAgentId.value)
}

const currentName = computed(() => {
  const a = agents.value.find((x) => x.id === selectedAgentId.value)
  return a ? a.name : ''
})

// ---------------- 保存（写入所选 Agent 并热重建） ----------------
const changed = computed(() => JSON.stringify(servers.value) !== originalServers.value)
const changedCount = computed(() => {
  const o = JSON.parse(originalServers.value || '[]')
  const c = servers.value
  if (o.length !== c.length) return Math.abs(o.length - c.length)
  let n = 0
  for (let i = 0; i < c.length; i++) {
    if (JSON.stringify(o[i]) !== JSON.stringify(c[i])) n++
  }
  return n
})
function revert() {
  servers.value = JSON.parse(originalServers.value || '[]')
}
async function saveServers() {
  if (!agentConfig.value || !selectedAgentId.value) return
  saving.value = true
  savedMsg.value = ''
  mcpError.value = ''
  try {
    const cfg = agentConfig.value
    const payload = {
      name: cfg.name,
      system_prompt: cfg.system_prompt,
      model_name: cfg.model_name,
      temperature: cfg.temperature,
      tools_enabled: cfg.tools_enabled,
      hitl: cfg.hitl,
      memory_enabled: cfg.memory_enabled,
      kb_enabled: cfg.kb_enabled,
      mcp_servers: servers.value,
      is_default: !!cfg.is_default,
    }
    const r = await apiFetch(`/api/admin/agents/${selectedAgentId.value}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '保存失败')
    }
    originalServers.value = JSON.stringify(servers.value)
    savedMsg.value = '已保存并热重建 ✓'
  } catch (e) {
    mcpError.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.list-page { padding: 24px 28px; max-width: 1000px; margin: 0 auto; width: 100%; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.hint { color: var(--muted); font-size: 13px; margin: 0; max-width: 720px; }
.hint b { color: var(--text); }
.err { background: #fde8e8; color: #d93025; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }

.agent-pick { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 13px; color: var(--text); }
.agent-pick select { border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-family: inherit; font-size: 13px; background: var(--panel); color: var(--text); }
.savebar { display: flex; align-items: center; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
.changed { color: #b45309; font-size: 13px; }
.save { border: none; background: var(--accent); color: #fff; padding: 9px 18px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600; }
.save:disabled { opacity: 0.55; cursor: not-allowed; }
.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); padding: 9px 14px; border-radius: 9px; cursor: pointer; font-size: 13px; }
.saved { color: #22a06b; font-size: 13px; }
.spacer { flex: 1; }
.muted { color: var(--muted); font-size: 13px; }
</style>
