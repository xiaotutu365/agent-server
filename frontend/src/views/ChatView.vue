<template>
  <div class="main-row">
    <ThreadList
      :threads="threads"
      :current-id="threadId"
      :busy="streaming"
      @new="newThread"
      @select="switchThread"
      @remove="removeThread"
    />

    <div class="chat-col">
      <div class="chat-head">
        <span class="chat-title" :title="currentThreadTitle">{{ currentThreadTitle }}</span>
        <span v-if="streaming" class="running-badge" role="status" aria-label="会话运行中">
          <span class="dot" aria-hidden="true"></span>Running
        </span>
        <span class="head-spacer"></span>
        <label class="head-agent">
          <span class="head-agent-label">Agent</span>
          <select v-model="selectedAgentId" @change="onAgentChange">
            <option v-for="a in agents" :key="a.id" :value="a.id">
              {{ a.name }}{{ a.is_default ? '（默认）' : '' }}
            </option>
          </select>
          <span v-if="!agents.length" class="muted">（加载中…）</span>
        </label>
        <!-- 会话级模型选择（SPEC-session-model-select）：切换仅影响本会话后续消息 -->
        <label class="head-agent">
          <span class="head-agent-label">模型</span>
          <select v-model="selectedModelId">
            <option value="">默认（跟随全局）</option>
            <option v-for="m in chatModels" :key="m.id" :value="m.id">
              {{ m.name }}{{ m.is_default ? '（默认）' : '' }}
            </option>
          </select>
          <span v-if="!chatModels.length" class="muted">（加载中…）</span>
        </label>
      </div>
      <main class="chat" ref="chatEl">
        <div v-if="!messages.length && !restoring" class="empty">
          <div class="empty-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h2>开始与 DeepAgent 对话</h2>
          <p>它具备任务规划、虚拟文件系统、联网搜索、自定义工具与知识库检索能力。</p>
          <div class="suggestions">
            <button v-for="s in suggestions" :key="s" @click="send(s)">{{ s }}</button>
          </div>
        </div>

        <ChatMessage v-for="(m, i) in messages" :key="i" :msg="m" @retry="retryFrom(m)" />
      </main>

      <div v-if="pendingInterrupt" class="hitl-panel">
        <div class="hitl-head">⏸ 需要你的确认 / 回复</div>
        <div v-for="(req, ri) in pendingInterrupt.requests" :key="ri" class="hitl-req-group">
          <div v-for="(ar, ai) in (req.action_requests || [])" :key="ai" class="hitl-req">
            <div class="hitl-q" v-if="ar.args && ar.args.question">{{ ar.args.question }}</div>
            <div class="hitl-tool" v-else>{{ toolLabel(ar.name) }}</div>
            <table class="hitl-args" v-if="ar.args && !ar.args.question">
              <tbody>
                <tr v-for="(item, idx) in argEntries(ar.args)" :key="idx">
                  <th>{{ argLabel(item[0]) }}</th>
                  <td>{{ formatVal(item[0], item[1]) }}</td>
                </tr>
              </tbody>
            </table>
            <div class="hitl-actions">
              <template v-if="req.review_configs && req.review_configs[ai] && req.review_configs[ai].allowed_decisions.includes('respond')">
                <textarea v-model="pendingInterrupt.choices[choiceIndex(ri, ai)].message" class="hitl-input" placeholder="输入你的回答…" rows="2"></textarea>
                <button class="hitl-btn" :class="{active: choiceType(ri,ai)==='respond'}" @click="setType(ri, ai, 'respond')">回答并继续</button>
              </template>
              <template v-if="req.review_configs && req.review_configs[ai] && req.review_configs[ai].allowed_decisions.includes('approve')">
                <button class="hitl-btn" :class="{active: choiceType(ri,ai)==='approve'}" @click="setType(ri, ai, 'approve')">批准执行</button>
              </template>
              <template v-if="req.review_configs && req.review_configs[ai] && req.review_configs[ai].allowed_decisions.includes('reject')">
                <input v-if="choiceType(ri,ai)==='reject'" v-model="pendingInterrupt.choices[choiceIndex(ri, ai)].message" class="hitl-input" placeholder="拒绝理由（可选）" />
                <button class="hitl-btn" :class="{active: choiceType(ri,ai)==='reject'}" @click="setType(ri, ai, 'reject')">拒绝</button>
              </template>
            </div>
          </div>
        </div>
        <button class="hitl-submit" @click="respondInterrupt">提交决策</button>
      </div>

      <footer class="composer">
        <div class="composer-card" :class="{ disabled: !!pendingInterrupt }">
          <div v-if="uploadError" class="upload-error" role="alert">⚠ {{ uploadError }}</div>
          <div v-if="uploadedFiles.length" class="upload-chips" aria-label="已上传文件">
            <span v-for="(f, i) in uploadedFiles" :key="f.path" class="upload-chip" :title="f.path">
              <span class="chip-name">{{ f.name }}</span>
              <span class="chip-size">{{ formatSize(f.size) }}</span>
              <button class="chip-remove" aria-label="移除文件" @click="removeFile(i)">×</button>
            </span>
          </div>
          <textarea
            v-model="input"
            ref="inputEl"
            rows="3"
            :disabled="!!pendingInterrupt"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            @keydown="onKeydown"
            @input="autoResize"
          ></textarea>
          <div class="composer-bar">
            <button
              class="icon-btn"
              title="上传文件到工作区"
              aria-label="上传文件"
              :disabled="!!pendingInterrupt"
              @click="fileInput && fileInput.click()"
            >+</button>
            <input ref="fileInput" type="file" hidden @change="onFilePicked" />
            <!-- 占位按钮：不随请求发送任何字段（SPEC C3.2），后续接入模型 reasoning 能力 -->
            <button
              class="pill"
              :class="{ active: deepThinking }"
              title="即将上线"
              :aria-pressed="deepThinking"
              @click="deepThinking = !deepThinking"
            >♾ 深度思考</button>
            <span class="bar-spacer"></span>
            <button v-if="!streaming && !pendingInterrupt" class="send" @click="send()" :disabled="!canSend">发送</button>
            <button v-else-if="streaming && !pendingInterrupt" class="send stop" @click="stop">停止</button>
            <div v-else class="pending-hint">⏸ 请先处理上方的待确认事项</div>
          </div>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, computed } from 'vue'
import ChatMessage from '../components/MessageBubble.vue'
import ThreadList from '../components/ThreadList.vue'
import { streamChat } from '../api/chat'
import { listChatModels } from '../api/models'
import { apiFetch } from '../auth'

const messages = reactive([])
const threads = ref([])
const input = ref('')
const streaming = ref(false)
const chatEl = ref(null)
const inputEl = ref(null)
const threadId = ref(localStorage.getItem('lastThreadId') || '')

// 可选 Agent（聊天页指定使用某个 Agent，含其 MCP 配置）
const agents = ref([])
const selectedAgentId = ref('')

// 会话级模型选择（SPEC-session-model-select）：''=跟随全局默认；切换仅影响后续消息
const chatModels = ref([])
const selectedModelId = ref('')

// 待用户处理的中断（HITL）：非空时表示图已挂起，等待用户决策/回复
const pendingInterrupt = ref(null)

// 顶部标题栏：当前会话标题
const currentThreadTitle = computed(() => {
  const t = threads.value.find((x) => x.id === threadId.value)
  return (t && t.title) || '新对话'
})

// 输入区功能位（SPEC C3）：文件上传 chip + 深度思考占位
const uploadedFiles = reactive([]) // {name, path, size}
const uploadError = ref('')
const deepThinking = ref(false) // 纯占位，不随请求发送
const fileInput = ref(null)
const canSend = computed(() => !!input.value.trim() || uploadedFiles.length > 0)

function formatSize(n) {
  if (n == null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function removeFile(i) {
  uploadedFiles.splice(i, 1)
}

async function onFilePicked(e) {
  const f = e.target.files && e.target.files[0]
  e.target.value = ''
  if (!f) return
  uploadError.value = ''
  const fd = new FormData()
  fd.append('file', f)
  try {
    const r = await apiFetch('/api/chat/upload', { method: 'POST', body: fd })
    if (!r.ok) {
      const body = await r.json().catch(() => ({}))
      throw new Error(body.detail || `上传失败（${r.status}）`)
    }
    uploadedFiles.push(await r.json())
  } catch (err) {
    uploadError.value = err.message || '上传失败'
  }
}

let controller = null

const suggestions = [
  '帮我规划一个三天的杭州旅行行程，并写入 travel.md 文件',
  '用 web_search 查一下 deepagents 框架是什么',
  '结合知识库，回答我们公司的退货政策是什么？'
]

function genId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

function autoResize() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const el = chatEl.value
    if (!el) return
    // 流式输出时仅当用户停在底部附近才跟随，避免上翻看历史被拽回
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (force || nearBottom) el.scrollTop = el.scrollHeight
  })
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

async function loadThreads() {
  try {
    const r = await apiFetch('/api/threads')
    if (r.ok) threads.value = (await r.json()).threads || []
  } catch { /* 忽略 */ }
}

const restoring = ref(false) // 切换会话加载历史中：避免消息清空后空状态图标闪现

async function restoreThread(id) {
  restoring.value = true
  messages.splice(0, messages.length)
  if (!id) {
    restoring.value = false
    return
  }
  try {
    const r = await apiFetch(`/api/threads/${id}/messages`)
    if (r.ok) {
      const { messages: ms } = await r.json()
      ms.forEach((m) => messages.push(reactive({
        role: m.role, content: m.content, steps: [], plan: [], citations: [], streaming: false, error: ''
      })))
    }
  } catch { /* 忽略 */ } finally {
    restoring.value = false
  }
}

function newThread() {
  const id = genId()
  threadId.value = id
  localStorage.setItem('lastThreadId', id)
  messages.splice(0, messages.length)
  selectedModelId.value = '' // 新会话跟随全局默认
}

async function loadChatModels() {
  try {
    chatModels.value = await listChatModels()
  } catch { /* 忽略：下拉保留「默认」一项 */ }
}

async function loadAgents() {
  try {
    const r = await apiFetch('/api/agents')
    if (r.ok) {
      const { agents: list } = await r.json()
      agents.value = list || []
      const saved = localStorage.getItem('lastAgentId')
      const def = agents.value.find((a) => a.is_default) || agents.value[0]
      selectedAgentId.value = (saved && agents.value.some((a) => a.id === saved))
        ? saved
        : (def ? def.id : '')
    }
  } catch { /* 忽略 */ }
}

function onAgentChange() {
  localStorage.setItem('lastAgentId', selectedAgentId.value)
  newThread() // 切换 Agent 时开新会话，避免不同 Agent 的上下文混用
}

async function switchThread(id) {
  if (streaming.value || id === threadId.value) return
  threadId.value = id
  localStorage.setItem('lastThreadId', id)
  // 回显该会话的模型覆盖（未选过的会话为「默认」）
  const t = threads.value.find((x) => x.thread_id === id)
  selectedModelId.value = (t && t.model_id) || ''
  await restoreThread(id)
  scrollToBottom(true)
}

async function removeThread(id) {
  try {
    await apiFetch(`/api/threads/${id}`, { method: 'DELETE' })
    if (id === threadId.value) newThread()
    await loadThreads()
  } catch { /* 忽略 */ }
}

function stop() {
  controller?.abort()
  controller = null
  streaming.value = false
  const last = messages[messages.length - 1]
  if (last && last.role === 'assistant') last.streaming = false
}

function makeHandlers(assistant) {
  return {
    onToken(t) {
      assistant.content += t
      scrollToBottom()
    },
    onToolStart(d) {
      assistant.steps.push({
        tool: d.tool,
        input: d.input,
        output: '',
        status: 'running',
        open: false
      })
      scrollToBottom()
    },
    onToolEnd(d) {
      for (let i = assistant.steps.length - 1; i >= 0; i--) {
        const s = assistant.steps[i]
        if (s.tool === d.tool && s.status === 'running') {
          s.status = 'done'
          s.output = d.output
          break
        }
      }
      // kb 检索的引用来源并入本条回答（按 file+chunk_idx 去重）
      if (Array.isArray(d.citations) && d.citations.length) {
        const seen = new Set(assistant.citations.map((c) => `${c.file}:${c.chunk_idx}`))
        for (const c of d.citations) {
          const k = `${c.file}:${c.chunk_idx}`
          if (!seen.has(k)) {
            seen.add(k)
            assistant.citations.push(c)
          }
        }
      }
      scrollToBottom()
    },
    onPlan(d) {
      assistant.plan = (d.todos || []).map((t) => ({
        content: t.content || '',
        status: t.status || 'pending'
      }))
      scrollToBottom()
    },
    onInterrupt(d) {
      // 图挂起，保存待处理中断；每个 action_request 对应一个用户决策
      const reqs = d.requests || []
      const choices = []
      for (const r of reqs) {
        const ars = r.action_requests || []
        const rcs = r.review_configs || []
        ars.forEach((ar, i) => {
          const allowed = (rcs[i] && rcs[i].allowed_decisions) || []
          choices.push({
            type: allowed[0] || 'approve',
            message: '',
            editedAction: { name: ar.name || '', args: ar.args || {} }
          })
        })
      }
      pendingInterrupt.value = { requests: reqs, choices }
    },
    onError(m) {
      assistant.error = m || '未知错误'
    },
    onDone() {
      assistant.streaming = false
    }
  }
}

// 统一的流式调用：send / 重试 / HITL resume 共用，收敛 loading 与错误处理
async function runStream(content, assistant, resume = null) {
  streaming.value = true
  controller = new AbortController()
  try {
    await streamChat(content, threadId.value, makeHandlers(assistant), controller.signal, resume, null, selectedAgentId.value, selectedModelId.value)
  } catch (err) {
    if (err.name !== 'AbortError') {
      assistant.error = err.message || String(err)
    }
  } finally {
    assistant.streaming = false
    streaming.value = false
    controller = null
    scrollToBottom()
    loadThreads()
  }
}

async function send(text) {
  let content = (text ?? input.value).trim()
  // 附带已上传文件路径，agent 经 read_file 读取（SPEC C3.1）
  // FilesystemBackend root=backend/workspace，工具内相对路径即 uploads/xxx
  if (!text && uploadedFiles.length) {
    const paths = uploadedFiles.map((f) => f.path).join('、')
    content = content
      ? `${content}\n\n（随消息附带工作区文件：${paths}）`
      : `（随消息附带工作区文件：${paths}）`
  }
  if (!content || streaming.value || pendingInterrupt.value) return

  if (!threadId.value) newThread()

  input.value = ''
  uploadedFiles.splice(0)
  uploadError.value = ''
  await nextTick()
  if (inputEl.value) inputEl.value.style.height = 'auto'

  messages.push({ role: 'user', content })
  const assistant = reactive({
    role: 'assistant',
    content: '',
    steps: [],
    plan: [],
    citations: [],
    streaming: true,
    error: ''
  })
  messages.push(assistant)
  scrollToBottom(true)

  await runStream(content, assistant)
}

// 失败重试：取该条回复前最近的一条用户消息重新发起，不重复插入用户气泡
async function retryFrom(msg) {
  if (streaming.value || pendingInterrupt.value) return
  const idx = messages.indexOf(msg)
  if (idx < 1) return
  let userIdx = -1
  for (let i = idx - 1; i >= 0; i--) {
    if (messages[i].role === 'user') { userIdx = i; break }
  }
  if (userIdx === -1) return
  const content = messages[userIdx].content
  messages.splice(idx) // 移除失败回复及其后内容
  if (!threadId.value) newThread()
  const assistant = reactive({
    role: 'assistant',
    content: '',
    steps: [],
    plan: [],
    citations: [],
    streaming: true,
    error: ''
  })
  messages.push(assistant)
  scrollToBottom(true)
  await runStream(content, assistant)
}

// 累计索引：将 (request, action) 双层下标映射到扁平 decisions/choices
function choiceIndex(ri, ai) {
  const reqs = pendingInterrupt.value?.requests || []
  let idx = 0
  for (let r = 0; r < ri; r++) idx += (reqs[r].action_requests || []).length
  return idx + ai
}
function choiceType(ri, ai) {
  const c = pendingInterrupt.value?.choices[choiceIndex(ri, ai)]
  return c ? c.type : ''
}
function setType(ri, ai, type) {
  const c = pendingInterrupt.value?.choices[choiceIndex(ri, ai)]
  if (c) c.type = type
}
// 工具名 → 面向用户的中文名
const TOOL_LABELS = {
  create_work_order: '创建工单',
  ask_human: '向你提问',
  query_customer: '查询客户档案',
}
function toolLabel(name) {
  return TOOL_LABELS[name] || (name ? `调用工具：${name}` : '待确认操作')
}

// 字段名 → 面向用户的中文列名
const ARG_LABELS = {
  phone: '客户手机号',
  customer_phone: '客户手机号',
  customer_id: '客户 ID',
  title: '工单标题',
  priority: '优先级',
  description: '问题描述',
  name: '名称',
  query: '查询内容',
  search: '查询内容',
  order_id: '工单 ID',
  reason: '原因',
}
function argLabel(key) {
  return ARG_LABELS[key] || key.replace(/_/g, ' ')
}

// 字段值 → 人性化展示（枚举值翻译成中文）
const VALUE_LABELS = {
  priority: { urgent: '紧急', high: '高', medium: '中', low: '低' },
}
function argEntries(args) {
  return Object.entries(args).filter(([k]) => k !== 'question')
}
function formatVal(key, v) {
  if (v === null || v === undefined) return '—'
  if (VALUE_LABELS[key] && VALUE_LABELS[key][v]) return VALUE_LABELS[key][v]
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  try { return JSON.stringify(v) } catch { return String(v) }
}

// 提交中断决策：构造 HITLResponse 并以 resume 恢复图
async function respondInterrupt() {
  const pi = pendingInterrupt.value
  if (!pi || streaming.value) return

  const decisions = pi.choices.map((c) => {
    if (c.type === 'edit') return { type: 'edit', edited_action: c.editedAction }
    if (c.type === 'respond') return { type: 'respond', message: c.message }
    if (c.type === 'reject') return { type: 'reject', message: c.message || undefined }
    return { type: c.type } // approve
  })
  const resume = { decisions }

  pendingInterrupt.value = null
  const assistant = messages[messages.length - 1]
  if (!assistant) return
  assistant.streaming = true
  await runStream('', assistant, resume)
}

onMounted(async () => {
  await loadAgents()
  loadChatModels()
  await loadThreads()
  if (threadId.value) {
    // 恢复上次会话时同步回显其模型覆盖
    const t = threads.value.find((x) => x.thread_id === threadId.value)
    selectedModelId.value = (t && t.model_id) || ''
    await restoreThread(threadId.value)
    scrollToBottom(true)
  } else if (threads.value.length) {
    await switchThread(threads.value[0].thread_id)
  }
})
</script>

<style scoped>
.main-row {
  height: 100%;
  display: flex;
  min-height: 0;
  max-width: 1360px;
  margin: 0 auto;
}
.chat-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  font-size: 13px;
  color: var(--text);
}
/* 会话标题 + Running 状态（SPEC C2） */
.chat-title {
  font-weight: 600;
  font-size: 14px;
  max-width: 40%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.running-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--warning) 35%, transparent);
  border-radius: 999px;
  padding: 2px 10px;
}
.running-badge .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--warning);
  animation: run-blink 1.1s ease-in-out infinite;
}
@keyframes run-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
.head-spacer { flex: 1; }
.head-agent {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}
.head-agent-label { color: var(--muted); }
.chat-head select {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  font-family: inherit;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
}
.chat-head .muted { color: var(--muted); }

.chat {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
}
.empty { text-align: center; color: var(--muted); padding: 60px 20px; }
.empty-icon {
  width: 56px; height: 56px; margin: 0 auto 16px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--panel-2); color: var(--primary);
  border: 1px solid var(--border);
}
.empty-icon svg { width: 26px; height: 26px; }
.empty h2 { color: var(--text); margin-bottom: 8px; font-size: 20px; }
.empty p { font-size: 14px; margin-bottom: 24px; }
.suggestions { display: flex; flex-direction: column; gap: 10px; align-items: center; }
.suggestions button {
  max-width: 520px; width: 100%;
  border: 1px solid var(--border); background: var(--panel); color: var(--text);
  padding: 12px 16px; border-radius: 12px; cursor: pointer; font-size: 13px;
  text-align: left; transition: all 0.15s;
}
.suggestions button:hover { border-color: var(--accent); background: var(--panel-hover); }

.composer {
  flex: none;
  padding: 10px 20px 14px;
  border-top: 1px solid var(--border);
  background: var(--panel);
}
/* EvoFlow 式大圆角输入卡（SPEC C3.3）：内含 chips / textarea / 功能条 */
.composer-card {
  max-width: 900px;
  margin: 0 auto;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--bg);
  padding: 10px 12px 8px;
  transition: border-color .15s ease;
}
.composer-card:focus-within { border-color: var(--accent); }
.composer-card.disabled { opacity: 0.6; }
.composer textarea {
  display: block;
  width: 100%;
  resize: none;
  border: none;
  padding: 4px 6px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  background: transparent;
  color: var(--text);
  max-height: 160px;
  outline: none;
}
.composer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.bar-spacer { flex: 1; }
.icon-btn {
  flex: none;
  width: 32px; height: 32px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: transparent;
  color: var(--muted);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: all .15s ease;
}
.icon-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
/* 深度思考占位 pill：仅视觉切换，不随请求发送（SPEC C3.2） */
.pill {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  padding: 6px 12px;
  cursor: pointer;
  transition: all .15s ease;
}
.pill:hover { color: var(--text); border-color: var(--border-strong, var(--border)); }
.pill.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
/* 已上传文件 chips */
.upload-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 2px 2px 8px; }
.upload-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  padding: 3px 8px;
  font-size: 12px;
  color: var(--text);
  max-width: 260px;
}
.chip-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-size { color: var(--muted); flex: none; }
.chip-remove {
  border: none; background: transparent; color: var(--muted);
  cursor: pointer; font-size: 14px; line-height: 1; padding: 0 2px;
  border-radius: 4px;
}
.chip-remove:hover { color: var(--destructive); }
.upload-error {
  color: var(--destructive);
  font-size: 12px;
  padding: 2px 2px 6px;
}
.pending-hint { color: var(--muted); font-size: 12px; }
.send {
  flex: none;
  border: none;
  background: var(--cta-strong);
  color: var(--on-cta);
  padding: 8px 20px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: background-color .15s ease;
}
.send:hover:not(:disabled) { background: var(--cta); }
.send:disabled { opacity: 0.5; cursor: not-allowed; }
.send.stop { background: var(--destructive); }

.hitl-panel {
  flex: none;
  margin: 0 20px 10px;
  padding: 14px 16px;
  border: 1px solid var(--accent);
  border-radius: 12px;
  background: var(--panel);

}
.hitl-head { font-weight: 600; color: var(--text); margin-bottom: 10px; font-size: 14px; }
.hitl-req-group { display: flex; flex-direction: column; gap: 10px; }
.hitl-req {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--bg);
}
.hitl-q { color: var(--text); font-size: 14px; line-height: 1.5; margin-bottom: 8px; }
.hitl-tool { color: var(--accent); font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.hitl-args {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 8px;
  font-size: 13px;
}
.hitl-args th {
  text-align: left;
  color: var(--muted);
  font-weight: 500;
  padding: 4px 12px 4px 0;
  white-space: nowrap;
  vertical-align: top;
  width: 92px;
}
.hitl-args td {
  color: var(--text);
  padding: 4px 0;
  word-break: break-word;
  line-height: 1.5;
}
.hitl-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.hitl-input {
  flex: 1 1 100%; resize: none; min-height: 38px;
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  font-family: inherit; font-size: 13px; background: var(--bg); color: var(--text);
}
.hitl-input:focus { border-color: var(--accent); outline: none; }
.hitl-btn {
  border: 1px solid var(--border); background: var(--panel); color: var(--text);
  padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px;
}
.hitl-btn:hover { border-color: var(--accent); }
.hitl-btn.active { background: var(--accent); color: var(--on-primary); border-color: var(--accent); }
.hitl-submit {
  margin-top: 12px; width: 100%; border: none; background: var(--accent); color: var(--on-primary);
  padding: 10px; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 600;
}
.pending-hint { color: var(--muted); font-size: 13px; padding: 11px 0; }

@media (max-width: 760px) {
  .main-row { flex-direction: column; width: 100%; }
  .chat-head, .chat, .composer { padding-left: 14px; padding-right: 14px; }
  .chat { padding-top: 18px; }
  .empty { padding: 32px 4px; }
  .composer { align-items: stretch; flex-direction: column; }
  .send { width: 100%; min-height: 44px; }
  .hitl-panel { margin-left: 14px; margin-right: 14px; }
}
</style>
