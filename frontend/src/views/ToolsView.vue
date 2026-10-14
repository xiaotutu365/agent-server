<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>工具列表</h2>
        <p class="hint">
          系统已注册的全部工具，按能力分组；点击工具行可展开查看
          <b>提示词、参数定义与 JSON Schema</b>。共 <b>{{ total }}</b> 个内置工具。
        </p>
      </div>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <!-- 内置工具目录 -->
    <div v-for="g in groups" :key="g.key" class="group-card">
      <div class="group-head">
        <span class="g-label">{{ g.label }}</span>
        <span class="g-count">{{ g.tools.length }} 个</span>
      </div>
      <div v-for="t in g.tools" :key="t.name" class="tool-row">
        <div class="tool-main" @click="toggle(t)">
          <span class="chev" :class="{ open: open[t.name] }">▸</span>
          <span class="name mono">{{ t.name }}</span>
          <span class="desc-short">{{ t.description || '—' }}</span>
        </div>

        <div v-if="open[t.name] && details[t.name]" class="tool-detail">
          <div class="dt-block">
            <div class="dt-label">所属分组</div>
            <span class="tag">{{ details[t.name].group_label }}</span>
          </div>
          <div class="dt-block">
            <div class="dt-label">提示词（给模型的工具描述）</div>
            <pre class="dt-pre">{{ details[t.name].prompt }}</pre>
          </div>
          <div class="dt-block">
            <div class="dt-label">参数定义</div>
            <table v-if="details[t.name].params && details[t.name].params.length" class="sub-tbl">
              <thead>
                <tr><th>参数</th><th>类型</th><th>必填</th><th>默认</th><th>说明</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in details[t.name].params" :key="p.name">
                  <td class="mono">{{ p.name }}</td>
                  <td>{{ p.type }}</td>
                  <td>{{ p.required ? '是' : '否' }}</td>
                  <td>{{ p.default === null || p.default === undefined ? '—' : p.default }}</td>
                  <td>{{ p.description || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="muted">该工具无参数。</div>
          </div>
          <div class="dt-block" v-if="details[t.name].schema">
            <details>
              <summary>JSON Schema 原文</summary>
              <pre class="dt-pre json">{{ JSON.stringify(details[t.name].schema, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- MCP 服务器（可切换 Agent） -->
    <section class="mcp">
      <p class="hint mcp-hint">
        下方 MCP 服务器绑定到<b>所选 Agent</b>，保存后该 Agent 热重建生效（默认 Agent 即聊天使用的 Agent）。
      </p>
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
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiFetch } from '../auth'
import McpServers from '../components/McpServers.vue'

// ---------------- 内置工具 ----------------
const groups = ref([])
const total = ref(0)
const error = ref('')
const open = reactive({})
const details = reactive({})

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

onMounted(loadAll)

async function loadAll() {
  await loadTools()
  await loadAgents()
}

async function loadTools() {
  error.value = ''
  try {
    const r = await apiFetch('/api/admin/tools')
    if (!r.ok) throw new Error('加载失败')
    const data = await r.json()
    groups.value = data.groups || []
    total.value = data.total || 0
  } catch (e) {
    error.value = e.message || String(e)
  }
}

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

// ---------------- 内置工具展开 ----------------
async function toggle(t) {
  if (open[t.name]) { open[t.name] = false; return }
  if (!details[t.name]) {
    try {
      const r = await apiFetch(`/api/admin/tools/${encodeURIComponent(t.name)}`)
      if (r.ok) details[t.name] = await r.json()
    } catch (e) { /* 详情失败仍展开 */ }
  }
  open[t.name] = true
}

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

.group-card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 16px; }
.group-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--code-bg); }
.g-label { font-weight: 600; font-size: 14px; color: var(--text); }
.g-count { font-size: 12px; color: var(--muted); }

.tool-row { border-bottom: 1px solid var(--border); }
.tool-row:last-child { border-bottom: none; }
.tool-main { display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; }
.tool-main:hover { background: var(--panel-hover); }
.chev { color: var(--muted); transition: transform 0.15s; flex: none; }
.chev.open { transform: rotate(90deg); }
.name { font-weight: 600; white-space: nowrap; }
.mono { font-family: var(--mono); font-size: 12px; color: var(--accent); }
.desc-short { color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tool-detail { padding: 4px 16px 18px; background: var(--code-bg); border-top: 1px dashed var(--border); }
.dt-block { margin-top: 14px; }
.dt-label { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.dt-pre { font-family: var(--mono); font-size: 12px; line-height: 1.55; white-space: pre-wrap; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin: 0; max-height: 320px; overflow: auto; word-break: break-word; }
.tag { display: inline-block; font-size: 11px; padding: 3px 10px; border-radius: 20px; background: var(--accent); color: #fff; }
.muted { color: var(--muted); font-size: 13px; }
.sub-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.sub-tbl th, .sub-tbl td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
.sub-tbl th { font-weight: 600; color: var(--muted); background: var(--bg); }
.sub-tbl tr:last-child td { border-bottom: none; }

/* MCP 区 */
.mcp { margin-top: 28px; border-top: 1px solid var(--border); padding-top: 22px; }
.mcp-hint { max-width: 100%; margin-bottom: 12px; }
.agent-pick { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 13px; color: var(--text); }
.agent-pick select { border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-family: inherit; font-size: 13px; background: var(--panel); color: var(--text); }
.savebar { display: flex; align-items: center; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
.changed { color: #b45309; font-size: 13px; }
.save { border: none; background: var(--accent); color: #fff; padding: 9px 18px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600; }
.save:disabled { opacity: 0.55; cursor: not-allowed; }
.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); padding: 9px 14px; border-radius: 9px; cursor: pointer; font-size: 13px; }
.saved { color: #22a06b; font-size: 13px; }
.spacer { flex: 1; }
</style>
