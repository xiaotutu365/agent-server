<template>
  <div class="mcp">
    <div class="mcp-head">
      <div>
        <h3>MCP 服务器</h3>
        <p class="hint">
          挂载外部 MCP 服务器即可把其工具并入本 Agent（无需改代码）。
          可对每个服务器设 <b>allow_roles</b> 做越权闸（如仅 admin 可调）。
        </p>
      </div>
      <button class="add" @click="openAdd">+ 新增服务器</button>
    </div>

    <div v-if="!list.length" class="muted empty">
      尚未挂载任何 MCP 服务器。点击「+ 新增服务器」添加 stdio / SSE / Streamable HTTP 服务器。
    </div>

    <div v-for="(s, i) in list" :key="i" class="srv-card">
      <div class="srv-top">
        <span class="srv-name mono">{{ s.name }}</span>
        <span class="badge" :class="s.transport">{{ s.transport }}</span>
        <span v-if="s.enabled !== false" class="badge ok">已启用</span>
        <span v-else class="badge off">已停用</span>
        <span v-if="s.allow_roles && s.allow_roles.length" class="badge role">
          限角色: {{ s.allow_roles.join(', ') }}
        </span>
        <span class="spacer"></span>
        <button class="link" @click="testServer(i)">
          {{ testing === i ? '连接中…' : '测试连接' }}
        </button>
        <button class="link" @click="openEdit(i)">编辑</button>
        <button class="link danger" @click="removeServer(i)">删除</button>
      </div>
      <div class="srv-meta mono">
        <template v-if="s.transport === 'stdio'">
          cmd: {{ s.command }} <span v-if="s.args && s.args.length">args: {{ s.args.join(' ') }}</span>
          <span v-if="s.env && Object.keys(s.env).length">env: {{ Object.keys(s.env).join(',') }}</span>
        </template>
        <template v-else>
          url: {{ s.url }}
          <span v-if="s.headers && Object.keys(s.headers).length">headers: {{ Object.keys(s.headers).join(',') }}</span>
        </template>
      </div>
      <div v-if="previews[i] !== undefined" class="srv-preview">
        <template v-if="Array.isArray(previews[i])">
          暴露工具 ({{ previews[i].length }})：
          <span v-for="p in previews[i]" :key="p.name" class="chip mono">{{ p.name }}</span>
          <span v-if="!previews[i].length" class="muted">无</span>
        </template>
        <span v-else class="err-inline">{{ previews[i] }}</span>
      </div>
    </div>

    <!-- 新增 / 编辑 弹窗 -->
    <div v-if="showForm" class="modal-mask" @click.self="showForm = false">
      <div class="modal">
        <h3>{{ editingIndex >= 0 ? '编辑 MCP 服务器' : '新增 MCP 服务器' }}</h3>
        <div v-if="formError" class="err">{{ formError }}</div>

        <label class="field">
          <span>名称（唯一标识）</span>
          <input v-model="form.name" placeholder="如 demo / crm-mcp" />
        </label>

        <label class="field">
          <span>传输方式</span>
          <select v-model="form.transport">
            <option value="stdio">stdio（本地子进程）</option>
            <option value="sse">SSE</option>
            <option value="streamable_http">Streamable HTTP</option>
          </select>
        </label>

        <template v-if="form.transport === 'stdio'">
          <label class="field">
            <span>启动命令</span>
            <input v-model="form.command" placeholder="如 ./venv/bin/python" />
          </label>
          <label class="field col">
            <span>参数（每行一个）</span>
            <textarea v-model="form.args" rows="3" placeholder="tests/mcp_demo_server.py"></textarea>
          </label>
          <label class="field col">
            <span>环境变量（每行 K=V，可选）</span>
            <textarea v-model="form.env" rows="2" placeholder="API_KEY=xxx"></textarea>
          </label>
        </template>
        <template v-else>
          <label class="field col">
            <span>服务器地址 URL</span>
            <input v-model="form.url" placeholder="http://localhost:8001/mcp" />
          </label>
          <label class="field col">
            <span>请求头（每行 K: V，可选）</span>
            <textarea v-model="form.headers" rows="2" placeholder="Authorization: Bearer xxx"></textarea>
          </label>
        </template>

        <label class="field col">
          <span>allow_roles（逗号分隔，可选；空=不限制）</span>
          <input v-model="form.allow_roles" placeholder="如 admin 或 admin,user" />
          <span class="sub">命中列表外的角色调用该服务器的工具时会被拒绝。</span>
        </label>

        <label class="field check">
          <input type="checkbox" v-model="form.enabled" />
          <span>启用此服务器</span>
        </label>

        <div class="modal-actions">
          <button class="link" @click="testForm">测试连接</button>
          <span v-if="formTest" class="form-test" :class="formTestOk ? 'ok' : 'bad'">{{ formTest }}</span>
          <span class="spacer"></span>
          <button class="ghost" @click="showForm = false">取消</button>
          <button class="save" @click="saveForm">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { apiFetch } from '../auth'

const props = defineProps({ modelValue: { type: Array, default: () => [] } })
const emit = defineEmits(['update:modelValue'])

const list = computed(() => props.modelValue || [])
const testing = ref(-1)
const previews = reactive({})

const showForm = ref(false)
const editingIndex = ref(-1)
const form = reactive({
  name: '', transport: 'stdio', command: '', args: '', env: '',
  url: '', headers: '', allow_roles: '', enabled: true,
})
const formError = ref('')
const formTest = ref('')
const formTestOk = ref(false)

function commit(arr) { emit('update:modelValue', arr) }

// ---------- 解析 / 构造 ----------
function parseLines(text) {
  return (text || '').split('\n').map((s) => s.trim()).filter(Boolean)
}
function parseKV(text, sep) {
  const obj = {}
  for (const line of parseLines(text)) {
    const i = line.indexOf(sep)
    if (i > 0) obj[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return obj
}
function buildPayload(s) {
  const p = { name: s.name.trim(), transport: s.transport, enabled: s.enabled !== false }
  const roles = parseLines((s.allow_roles || '').replace(/,/g, '\n'))
  if (roles.length) p.allow_roles = roles
  if (s.transport === 'stdio') {
    p.command = s.command.trim()
    const a = parseLines(s.args)
    if (a.length) p.args = a
    const e = parseKV(s.env, '=')
    if (Object.keys(e).length) p.env = e
  } else {
    p.url = s.url.trim()
    const h = parseKV(s.headers, ':')
    if (Object.keys(h).length) p.headers = h
  }
  return p
}
function serverToForm(s) {
  return {
    name: s.name || '',
    transport: s.transport || 'stdio',
    command: s.command || '',
    args: (s.args || []).join('\n'),
    env: Object.entries(s.env || {}).map(([k, v]) => `${k}=${v}`).join('\n'),
    url: s.url || '',
    headers: Object.entries(s.headers || {}).map(([k, v]) => `${k}: ${v}`).join('\n'),
    allow_roles: (s.allow_roles || []).join(', '),
    enabled: s.enabled !== false,
  }
}

// ---------- 弹窗 ----------
function openAdd() {
  Object.assign(form, {
    name: '', transport: 'stdio', command: '', args: '', env: '',
    url: '', headers: '', allow_roles: '', enabled: true,
  })
  editingIndex.value = -1
  formError.value = ''
  formTest.value = ''
  showForm.value = true
}
function openEdit(i) {
  Object.assign(form, serverToForm(list.value[i]))
  editingIndex.value = i
  formError.value = ''
  formTest.value = ''
  showForm.value = true
}
function validateForm() {
  if (!form.name.trim()) return '名称不能为空'
  if (form.transport === 'stdio') {
    if (!form.command.trim()) return 'stdio 方式需要启动命令'
  } else if (!form.url.trim()) return '需要服务器 URL'
  const dup = list.value.some(
    (s, idx) => s.name === form.name.trim() && idx !== editingIndex.value,
  )
  if (dup) return '服务器名称已存在'
  return ''
}
function saveForm() {
  const err = validateForm()
  if (err) { formError.value = err; return }
  const payload = buildPayload(form)
  const next = list.value.slice()
  if (editingIndex.value >= 0) next[editingIndex.value] = payload
  else next.push(payload)
  commit(next)
  showForm.value = false
}

// ---------- 测试连接 ----------
async function discover(serversList) {
  const r = await apiFetch('/api/admin/mcp/discover', {
    method: 'POST',
    body: JSON.stringify(serversList),
  })
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new Error(d.detail || 'MCP 连接失败')
  }
  const data = await r.json()
  return data.tools || []
}
async function testServer(i) {
  testing.value = i
  try {
    previews[i] = await discover([list.value[i]])
  } catch (e) {
    previews[i] = e.message || String(e)
  } finally {
    testing.value = -1
  }
}
async function testForm() {
  const err = validateForm()
  if (err) { formError.value = err; return }
  formTest.value = '连接中…'
  try {
    const tools = await discover([buildPayload(form)])
    formTestOk.value = true
    formTest.value = `连接成功，暴露 ${tools.length} 个工具`
  } catch (e) {
    formTestOk.value = false
    formTest.value = e.message || String(e)
  }
}

function removeServer(i) {
  if (!confirm(`确定删除 MCP 服务器「${list.value[i].name}」？`)) return
  const next = list.value.slice()
  next.splice(i, 1)
  commit(next)
  delete previews[i]
}
</script>

<style scoped>
.mcp-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.mcp-head h3 { margin: 0 0 4px; font-size: 15px; }
.hint { color: var(--muted); font-size: 13px; margin: 0; max-width: 640px; }
.hint b { color: var(--text); }
.add { border: none; background: var(--accent); color: #fff; padding: 9px 16px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap; }
.empty { margin: 12px 0; }
.srv-card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; margin-bottom: 12px; }
.srv-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.srv-name { font-weight: 600; font-size: 13px; }
.spacer { flex: 1; }
.badge { font-size: 11px; padding: 2px 9px; border-radius: 20px; background: var(--code-bg); color: var(--muted); border: 1px solid var(--border); }
.badge.stdio { color: var(--primary); }
.badge.sse, .badge.streamable_http { color: var(--cta); }
.badge.ok { color: var(--success); border-color: var(--success); }
.badge.off { color: var(--destructive); border-color: var(--destructive); }
.badge.role { color: #b45309; border-color: #b45309; }
.link { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 13px; padding: 2px 4px; }
.link.danger { color: var(--destructive); }
.srv-meta { color: var(--muted); font-size: 12px; margin-top: 6px; }
.srv-preview { margin-top: 8px; font-size: 12px; color: var(--text); display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.chip { background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px; padding: 1px 7px; }
.err-inline { color: var(--destructive); }
.muted { color: var(--muted); font-size: 13px; }

.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--bg); border: 1px solid var(--border); border-radius: 14px; padding: 22px 24px; width: 560px; max-width: 92vw; max-height: 90vh; overflow: auto; }
.modal h3 { margin: 0 0 12px; font-size: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; font-size: 13px; color: var(--muted); }
.field.col textarea { min-height: 60px; }
.field .sub { font-size: 12px; color: var(--muted); }
.field.check { flex-direction: row; align-items: center; gap: 8px; color: var(--text); }
.field input, .field textarea, .field select { border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; font-family: inherit; font-size: 14px; background: var(--panel); color: var(--text); }
.field input:focus, .field textarea:focus, .field select:focus { border-color: var(--accent); outline: none; }
.modal-actions { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.form-test { font-size: 12px; }
.form-test.ok { color: var(--success); }
.form-test.bad { color: var(--destructive); }
.save { border: none; background: var(--accent); color: #fff; padding: 9px 18px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600; }
.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); padding: 9px 14px; border-radius: 9px; cursor: pointer; font-size: 13px; }
</style>
