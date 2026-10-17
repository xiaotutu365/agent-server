<template>
  <div class="admin">
    <div class="admin-head">
      <h2>{{ isNew ? '新建 Agent' : '编辑 Agent' }}</h2>
      <p class="hint">修改后点击「保存并生效」，若该 Agent 为默认则后端会热重建（无需重启服务）。</p>
    </div>

    <div v-if="loadError" class="err">{{ loadError }}</div>
    <div v-else-if="loading" class="empty" role="status">加载中…</div>

    <section class="card">
      <h3>基本信息</h3>
      <label class="field">
        <span>名称</span>
        <input v-model="config.name" placeholder="Agent 名称" />
      </label>
      <label class="field">
        <span>模型名称</span>
        <input v-model="config.model_name" placeholder="如 deepseek-flash" />
      </label>
      <label class="field">
        <span>温度 (Temperature，0–1)</span>
        <input v-model.number="config.temperature" type="number" step="0.1" min="0" max="1" />
      </label>
      <label class="field col">
        <span>系统提示词 (System Prompt)</span>
        <textarea v-model="config.system_prompt" rows="10"></textarea>
      </label>
      <label class="field check">
        <input type="checkbox" v-model="config.is_default" />
        <span>设为默认 Agent（聊天固定使用此 Agent）</span>
      </label>
      <ul v-if="validationErrors.length" class="val-err">
        <li v-for="(e, i) in validationErrors" :key="i">{{ e }}</li>
      </ul>
    </section>

    <section class="card">
      <h3>工具关联</h3>
      <p class="hint">点击分组标题可折叠；记忆与知识库另有总开关。</p>

      <div v-for="g in toolGroups" :key="g.key" class="group" :class="{ collapsed: isCollapsed('tool-' + g.key) }">
        <div class="group-head">
          <button
            class="group-toggle"
            :aria-expanded="!isCollapsed('tool-' + g.key)"
            :aria-controls="'tools-' + g.key"
            @click="toggleCollapse('tool-' + g.key)"
          >
            <span class="caret" aria-hidden="true">{{ isCollapsed('tool-' + g.key) ? '▸' : '▾' }}</span>
            <span class="group-label">{{ g.label }}</span>
            <span class="count">{{ g.tools.length }}</span>
          </button>
          <label v-if="g.key === 'memory' || g.key === 'kb'" class="master">
            <input type="checkbox" :checked="config[g.key + '_enabled']"
                   @change="toggleGroup(g.key, $event.target.checked)" />
            启用该组
          </label>
        </div>
        <div :id="'tools-' + g.key" class="tools" v-show="!isCollapsed('tool-' + g.key)">
          <label v-for="t in g.tools" :key="t.name" class="tool"
                 :class="{ disabled: isGroupDisabled(g.key) }">
            <input type="checkbox"
                   :checked="isToolChecked(t.name)"
                   :disabled="isGroupDisabled(g.key)"
                   @change="toggleTool(t.name, $event.target.checked)" />
            <span class="tool-name">{{ t.name }}</span>
            <span class="tool-desc">{{ t.description }}</span>
          </label>
        </div>
      </div>
    </section>

    <section class="card">
      <h3>人机交互（HITL）中断配置</h3>
      <p class="hint">点击分组标题可折叠；勾选「执行前需确认」的工具并选择允许的决策类型。</p>
      <div v-for="g in toolGroups" :key="'h' + g.key" class="group" :class="{ collapsed: isCollapsed('hitl-' + g.key) }">
        <div class="group-head">
          <button
            class="group-toggle"
            :aria-expanded="!isCollapsed('hitl-' + g.key)"
            :aria-controls="'hitl-' + g.key"
            @click="toggleCollapse('hitl-' + g.key)"
          >
            <span class="caret" aria-hidden="true">{{ isCollapsed('hitl-' + g.key) ? '▸' : '▾' }}</span>
            <span class="group-label">{{ g.label }}</span>
          </button>
        </div>
        <div :id="'hitl-' + g.key" class="tools" v-show="!isCollapsed('hitl-' + g.key)">
          <div v-for="t in g.tools" :key="'h' + t.name" class="hitl-row">
            <label class="tool">
              <input type="checkbox" :checked="isHitl(t.name)"
                     @change="toggleHitl(t.name, $event.target.checked)" />
              <span class="tool-name">{{ t.name }}</span>
            </label>
            <div v-if="isHitl(t.name)" class="decisions">
              <label v-for="d in decisionOptions" :key="d.key" class="dec">
                <input type="checkbox" :checked="hitlDecisions(t.name).includes(d.key)"
                       @change="toggleDecision(t.name, d.key, $event.target.checked)" />
                {{ d.label }}
              </label>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <h3>MCP 服务器</h3>
      <p class="hint">挂载外部 MCP 服务器，把其工具并入<b>本 Agent</b>（无需改代码）。可对每个服务器设 allow_roles 做越权闸。</p>
      <McpServers v-model="config.mcp_servers" />
    </section>

    <section class="card">
      <h3>知识库挂载</h3>
      <p class="hint">勾选本 Agent 可检索的知识库（对话时相关片段自动注入并附引用来源）；<b>不勾选 = 检索所有库</b>（旧行为）。</p>
      <div v-if="loadingKbs" class="empty" role="status">加载中…</div>
      <div v-else-if="!kbList.length" class="empty" role="status">暂无知识库，先到「知识库管理」创建。</div>
      <div v-else class="tools">
        <label v-for="k in kbList" :key="k.kb_id" class="tool">
          <input type="checkbox" :checked="config.kb_ids.includes(k.kb_id)"
                 @change="toggleKb(k.kb_id, $event.target.checked)" />
          <span class="tool-name">{{ k.kb_id }}</span>
          <span class="tool-desc">{{ k.points_count }} 个片段</span>
        </label>
      </div>
    </section>

    <section v-if="changes.length" class="card preview">
      <h3>保存前预览（{{ changes.length }} 项改动）</h3>
      <ul>
        <li v-for="(ch, i) in changes" :key="i">{{ ch }}</li>
      </ul>
    </section>

    <div class="actions">
      <button class="btn btn-primary" :disabled="saving || validationErrors.length" @click="save">
        {{ saving ? '保存中…' : '保存并生效' }}
      </button>
      <button v-if="!isNew" class="btn btn-danger" :disabled="saving" @click="remove">删除</button>
      <button class="btn btn-ghost" @click="back">返回列表</button>
      <span v-if="validationErrors.length" class="blocked">请先修正上方校验项</span>
      <span v-else-if="!changes.length && !isNew" class="noop">没有改动</span>
      <span v-else-if="savedMsg" class="saved">{{ savedMsg }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../auth'
import { listKbs } from '../api/kb'
import McpServers from '../components/McpServers.vue'

const route = useRoute()
const router = useRouter()
const isNew = computed(() => !route.params.id || route.params.id === 'new')
const agentId = computed(() => route.params.id)

const config = reactive({
  name: '',
  system_prompt: '',
  model_name: '',
  temperature: 0.3,
  tools_enabled: [],
  hitl: {},
  memory_enabled: true,
  kb_enabled: true,
  kb_ids: [],
  mcp_servers: [],
  is_default: false,
})
const original = ref(null)
const toolGroups = ref([])
const kbList = ref([])
const loadingKbs = ref(false)
const loading = ref(false)
const saving = ref(false)
const savedMsg = ref('')
const loadError = ref('')
const error = ref('')
const collapsed = reactive({})

const decisionOptions = [
  { key: 'approve', label: '批准' },
  { key: 'reject', label: '拒绝' },
  { key: 'respond', label: '回答' },
  { key: 'edit', label: '修改参数' },
]

onMounted(load)

async function load() {
  loadError.value = ''
  loading.value = true
  loadingKbs.value = true
  try {
    const url = isNew.value ? '/api/admin/agents/template' : `/api/admin/agents/${agentId.value}`
    const r = await apiFetch(url)
    if (!r.ok) throw new Error('加载失败')
    const data = await r.json()
    Object.assign(config, data.agent)
    if (typeof config.hitl !== 'object' || config.hitl === null) config.hitl = {}
    if (!Array.isArray(config.kb_ids)) config.kb_ids = []
    toolGroups.value = data.tool_groups || []
    original.value = JSON.parse(JSON.stringify(config))
    kbList.value = await listKbs().catch(() => [])
  } catch (e) {
    loadError.value = e.message || String(e)
  } finally {
    loading.value = false
    loadingKbs.value = false
  }
}

function toggleKb(kbId, val) {
  if (val && !config.kb_ids.includes(kbId)) config.kb_ids.push(kbId)
  if (!val) config.kb_ids = config.kb_ids.filter((k) => k !== kbId)
}

// ---------- 折叠 ----------
function isCollapsed(key) { return !!collapsed[key] }
function toggleCollapse(key) { collapsed[key] = !collapsed[key] }

// ---------- 工具 / 分组开关 ----------
function isGroupDisabled(key) {
  if (key === 'memory') return !config.memory_enabled
  if (key === 'kb') return !config.kb_enabled
  return false
}
function toggleGroup(key, val) {
  if (key === 'memory') config.memory_enabled = val
  if (key === 'kb') config.kb_enabled = val
  if (!val) {
    const names = (toolGroups.value.find((g) => g.key === key)?.tools || []).map((t) => t.name)
    config.tools_enabled = config.tools_enabled.filter((n) => !names.includes(n))
  }
}
function isToolChecked(name) { return config.tools_enabled.includes(name) }
function toggleTool(name, val) {
  if (val && !config.tools_enabled.includes(name)) config.tools_enabled.push(name)
  if (!val) config.tools_enabled = config.tools_enabled.filter((n) => n !== name)
}

// ---------- HITL ----------
function isHitl(name) { return Object.prototype.hasOwnProperty.call(config.hitl, name) }
function hitlDecisions(name) { return config.hitl[name] || [] }
function toggleHitl(name, val) {
  if (val) {
    if (!config.hitl[name]) config.hitl[name] = ['approve', 'reject']
  } else {
    delete config.hitl[name]
  }
}
function toggleDecision(name, dec, val) {
  const list = config.hitl[name] || []
  if (val && !list.includes(dec)) list.push(dec)
  if (!val) {
    const i = list.indexOf(dec)
    if (i >= 0) list.splice(i, 1)
  }
  config.hitl[name] = list
}

// ---------- 校验 ----------
const validationErrors = computed(() => {
  const errs = []
  if (!config.name.trim()) errs.push('名称不能为空')
  const t = Number(config.temperature)
  if (config.temperature === '' || isNaN(t) || t < 0 || t > 1) errs.push('温度需在 0–1 之间')
  if (!config.system_prompt.trim()) errs.push('系统提示词不能为空')
  return errs
})

// ---------- 保存前预览 ----------
const changes = computed(() => {
  const o = original.value
  const c = config
  const list = []
  if (!o) return list

  if (o.name !== c.name) list.push(`名称：${o.name || '（空）'} → ${c.name || '（空）'}`)
  if (o.model_name !== c.model_name) list.push(`模型：${o.model_name || '（空）'} → ${c.model_name || '（空）'}`)
  if (Number(o.temperature) !== Number(c.temperature)) list.push(`温度：${o.temperature} → ${c.temperature}`)
  if (o.system_prompt !== c.system_prompt) list.push(`系统提示词：${c.system_prompt.trim() ? '已修改' : '已清空'}`)
  if (o.memory_enabled !== c.memory_enabled) list.push(`长期记忆：${o.memory_enabled ? '开启' : '关闭'} → ${c.memory_enabled ? '开启' : '关闭'}`)
  if (o.kb_enabled !== c.kb_enabled) list.push(`知识库：${o.kb_enabled ? '开启' : '关闭'} → ${c.kb_enabled ? '开启' : '关闭'}`)
  const oKb = (o.kb_ids || []).slice().sort()
  const cKb = (c.kb_ids || []).slice().sort()
  if (JSON.stringify(oKb) !== JSON.stringify(cKb)) {
    list.push(cKb.length
      ? `知识库挂载：${cKb.length} 个（${cKb.join('、')}）`
      : '知识库挂载：清空（检索所有库）')
  }
  if (!!o.is_default !== !!c.is_default) list.push(`默认 Agent：${o.is_default ? '是' : '否'} → ${c.is_default ? '是' : '否'}`)

  const oTools = new Set(o.tools_enabled)
  const cTools = new Set(c.tools_enabled)
  const added = [...cTools].filter((t) => !oTools.has(t))
  const removed = [...oTools].filter((t) => !cTools.has(t))
  if (added.length) list.push(`新增工具：${added.join('、')}`)
  if (removed.length) list.push(`移除工具：${removed.join('、')}`)

  const oHitl = o.hitl || {}
  const cHitl = c.hitl || {}
  for (const t of Object.keys(cHitl)) {
    if (!(t in oHitl)) list.push(`HITL 新增确认：${t}（${cHitl[t].join('/')}）`)
    else if (JSON.stringify(oHitl[t]) !== JSON.stringify(cHitl[t])) {
      list.push(`HITL 调整：${t}（${oHitl[t].join('/')} → ${cHitl[t].join('/')}）`)
    }
  }
  for (const t of Object.keys(oHitl)) {
    if (!(t in cHitl)) list.push(`HITL 取消：${t}`)
  }

  const oMcp = o.mcp_servers || []
  const cMcp = c.mcp_servers || []
  if (JSON.stringify(oMcp) !== JSON.stringify(cMcp)) {
    list.push(oMcp.length === cMcp.length
      ? 'MCP 服务器：配置已调整'
      : `MCP 服务器：${oMcp.length} → ${cMcp.length} 个`)
  }
  return list
})

async function save() {
  if (validationErrors.value.length) return
  saving.value = true
  savedMsg.value = ''
  error.value = ''
  try {
    const payload = {
      name: config.name,
      system_prompt: config.system_prompt,
      model_name: config.model_name,
      temperature: config.temperature,
      tools_enabled: config.tools_enabled,
      hitl: config.hitl,
      memory_enabled: config.memory_enabled,
      kb_enabled: config.kb_enabled,
      kb_ids: config.kb_ids,
      mcp_servers: config.mcp_servers,
      is_default: !!config.is_default,
    }
    const url = isNew.value ? '/api/admin/agents' : `/api/admin/agents/${agentId.value}`
    const method = isNew.value ? 'POST' : 'PUT'
    const r = await apiFetch(url, {
      method,
      body: JSON.stringify(payload),
    })
    if (!r.ok) throw new Error('保存失败')
    if (isNew.value) {
      router.push('/admin/agents')
      return
    }
    savedMsg.value = '已保存并生效 ✓'
    original.value = JSON.parse(JSON.stringify(config))
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!confirm(`确定删除「${config.name}」？此操作不可恢复。`)) return
  saving.value = true
  try {
    const r = await apiFetch(`/api/admin/agents/${agentId.value}`, { method: 'DELETE' })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error(d.detail || '删除失败')
    }
    router.push('/admin/agents')
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

function back() {
  router.push('/admin/agents')
}
</script>

<style scoped>
.admin {
  flex: 1; min-height: 0; width: 100%; max-width: 860px; margin: 0 auto;
  overflow-y: auto; padding: 24px 28px;
}
.admin-head h2 { margin: 0 0 4px; font-size: 18px; }
.card { padding: 16px 18px; margin-top: 16px; }
.card h3 { margin: 0 0 10px; font-size: 15px; }
.field.col textarea { min-height: 160px; }
.val-err { margin: 4px 0 0; padding-left: 18px; color: var(--destructive); font-size: 13px; }
.val-err li { margin: 2px 0; }
.group { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }
.group:first-of-type { border-top: none; padding-top: 0; margin-top: 0; }
.group-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.group.collapsed .group-head { margin-bottom: 0; }
.group-toggle {
  display: flex; align-items: center; gap: 8px; flex: 1; min-height: 32px;
  background: transparent; border: none; padding: 2px 4px; margin: -2px -4px;
  border-radius: var(--radius-sm); font-family: inherit; text-align: left;
}
.group-toggle:hover { background: var(--panel-hover); }
.group-label { font-weight: 600; font-size: 14px; }
.caret { display: inline-block; width: 12px; color: var(--muted); font-size: 11px; }
.count { font-size: 11px; color: var(--muted); background: var(--code-bg); border-radius: 10px; padding: 1px 8px; font-weight: 400; }
.master { font-size: 13px; color: var(--text); display: flex; align-items: center; gap: 6px; cursor: pointer; flex: none; }
.tools { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.tool { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 5px 0; }
.tool input[type="checkbox"] { width: 15px; height: 15px; margin: 0; flex: none; }
.tool.disabled { opacity: 0.45; }
.tool-name { font-family: var(--mono); font-size: 12px; color: var(--primary); flex: none; width: 170px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tool-desc { color: var(--muted); flex: 1; min-width: 0; }
.hitl-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; flex-wrap: wrap; }
.decisions { display: flex; gap: 12px; flex-wrap: wrap; }
.dec { font-size: 12px; color: var(--text); display: flex; align-items: center; gap: 4px; }
.preview ul { margin: 0; padding-left: 18px; font-size: 13px; }
.preview li { margin: 4px 0; color: var(--text); }
.actions { margin: 20px 0; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.saved { color: var(--success); font-size: 13px; }
.blocked { color: var(--destructive); font-size: 13px; }
.noop { color: var(--muted); font-size: 13px; }
</style>
