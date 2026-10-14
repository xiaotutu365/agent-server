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
        <span class="chat-head-label">Agent：</span>
        <select v-model="selectedAgentId" @change="onAgentChange">
          <option v-for="a in agents" :key="a.id" :value="a.id">
            {{ a.name }}{{ a.is_default ? '（默认）' : '' }}
          </option>
        </select>
        <span v-if="!agents.length" class="muted">（加载中…）</span>
        <button class="head-btn" @click="showTasks = !showTasks" :aria-pressed="showTasks">
          任务清单
          <span v-if="currentPlan.length" class="badge">{{ doneCount }}/{{ currentPlan.length }}</span>
        </button>
      </div>
      <main class="chat" ref="chatEl">
        <div v-if="!messages.length" class="empty">
          <h2>开始与 DeepAgent 对话</h2>
          <p>它具备任务规划、虚拟文件系统、联网搜索、自定义工具与知识库检索能力。</p>
          <div class="suggestions">
            <button v-for="s in suggestions" :key="s" @click="send(s)">{{ s }}</button>
          </div>
        </div>

        <ChatMessage v-for="(m, i) in messages" :key="i" :msg="m" />
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
        <textarea
          v-model="input"
          ref="inputEl"
          rows="1"
          :disabled="!!pendingInterrupt"
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          @keydown="onKeydown"
          @input="autoResize"
        ></textarea>
        <button v-if="!streaming && !pendingInterrupt" class="send" @click="send()" :disabled="!input.trim()">发送</button>
        <button v-else-if="streaming && !pendingInterrupt" class="send stop" @click="stop">停止</button>
        <div v-else class="pending-hint">⏸ 请先处理上方的待确认事项</div>
      </footer>
    </div>

    <aside class="task-panel" v-if="showTasks">
      <div class="task-head">
        <span class="task-title">任务清单</span>
        <span class="task-count" v-if="currentPlan.length">{{ doneCount }}/{{ currentPlan.length }}</span>
        <button class="task-close" @click="showTasks = false" aria-label="收起任务清单">✕</button>
      </div>
      <div class="task-progress" v-if="currentPlan.length">
        <div class="bar"><div class="bar-fill" :style="{ width: taskPct + '%' }"></div></div>
      </div>
      <ul class="task-list" v-if="currentPlan.length">
        <li v-for="(t, i) in currentPlan" :key="i" :class="taskStatusClass(t.status)">
          <span class="t-status">{{ taskStatusIcon(t.status) }}</span>
          <span class="t-content">{{ t.content }}</span>
        </li>
      </ul>
      <div class="task-empty" v-else>暂无任务计划</div>
    </aside>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, computed, watch } from 'vue'
import ChatMessage from '../components/MessageBubble.vue'
import ThreadList from '../components/ThreadList.vue'
import { streamChat } from '../api/chat'
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

// 待用户处理的中断（HITL）：非空时表示图已挂起，等待用户决策/回复
const pendingInterrupt = ref(null)

// 右侧「任务清单」面板：展示最近一份计划 + 进度概览
const showTasks = ref(false)
const currentPlan = computed(() => {
  for (let i = messages.length - 1; i >= 0; i--) {
    const p = messages[i].plan
    if (p && p.length) return p
  }
  return []
})
const doneCount = computed(() => currentPlan.value.filter(t => t.status === 'completed').length)
const taskPct = computed(() =>
  currentPlan.value.length ? Math.round(doneCount.value / currentPlan.value.length * 100) : 0
)
// 第一次出现计划时自动展开面板（之后用户可手动收起）
watch(
  () => currentPlan.value.length,
  (n, o) => { if (n > 0 && o === 0) showTasks.value = true }
)
function taskStatusClass(s) {
  return s === 'completed' ? 'done' : s === 'in_progress' ? 'doing' : 'pending'
}
function taskStatusIcon(s) {
  return s === 'completed' ? '✓' : s === 'in_progress' ? '▶' : '○'
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

function scrollToBottom() {
  nextTick(() => {
    const el = chatEl.value
    if (el) el.scrollTop = el.scrollHeight
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

async function restoreThread(id) {
  messages.splice(0, messages.length)
  if (!id) return
  try {
    const r = await apiFetch(`/api/threads/${id}/messages`)
    if (r.ok) {
      const { messages: ms } = await r.json()
      ms.forEach((m) => messages.push(reactive({
        role: m.role, content: m.content, steps: [], plan: [], streaming: false, error: ''
      })))
    }
  } catch { /* 忽略 */ }
}

function newThread() {
  const id = genId()
  threadId.value = id
  localStorage.setItem('lastThreadId', id)
  messages.splice(0, messages.length)
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
  await restoreThread(id)
  scrollToBottom()
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

async function send(text) {
  const content = (text ?? input.value).trim()
  if (!content || streaming.value || pendingInterrupt.value) return

  if (!threadId.value) newThread()

  input.value = ''
  await nextTick()
  if (inputEl.value) inputEl.value.style.height = 'auto'

  messages.push({ role: 'user', content })
  const assistant = reactive({
    role: 'assistant',
    content: '',
    steps: [],
    plan: [],
    streaming: true,
    error: ''
  })
  messages.push(assistant)
  scrollToBottom()

  streaming.value = true
  controller = new AbortController()

  try {
    await streamChat(content, threadId.value, makeHandlers(assistant), controller.signal, null, null, selectedAgentId.value)
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
  if (assistant) assistant.streaming = true
  streaming.value = true
  controller = new AbortController()

  try {
    await streamChat('', threadId.value, makeHandlers(assistant), controller.signal, resume, null, selectedAgentId.value)
  } catch (err) {
    if (err.name !== 'AbortError') {
      if (assistant) assistant.error = err.message || String(err)
    }
  } finally {
    if (assistant) assistant.streaming = false
    streaming.value = false
    controller = null
    scrollToBottom()
    loadThreads()
  }
}

onMounted(async () => {
  await loadAgents()
  await loadThreads()
  if (threadId.value) {
    await restoreThread(threadId.value)
    scrollToBottom()
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
  gap: 8px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  font-size: 13px;
  color: var(--text);
}
.chat-head-label { color: var(--muted); }
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
.head-btn {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border); background: var(--bg); color: var(--text-2);
  border-radius: 8px; padding: 6px 10px; font-family: inherit; font-size: 13px; cursor: pointer;
  transition: background-color .15s ease, border-color .15s ease;
}
.head-btn:hover { background: var(--panel-hover); border-color: var(--border-strong); }
.head-btn .badge {
  background: var(--primary); color: var(--on-primary);
  border-radius: 99px; padding: 1px 7px; font-size: 11px; font-weight: 600;
}

/* ---------- 右侧任务清单面板 ---------- */
.task-panel {
  flex: none;
  width: 264px;
  border-left: 1px solid var(--border);
  background: var(--panel);
  display: flex; flex-direction: column; min-height: 0;
}
.task-head {
  flex: none; display: flex; align-items: center; gap: 8px;
  padding: 12px 14px; border-bottom: 1px solid var(--border);
  font-weight: 600; font-size: 13px; color: var(--text);
}
.task-title { flex: none; }
.task-count { margin-left: auto; color: var(--muted); font-weight: 500; }
.task-close {
  border: none; background: transparent; color: var(--muted); cursor: pointer;
  font-size: 13px; padding: 2px 6px; border-radius: 6px;
}
.task-close:hover { background: var(--panel-hover); color: var(--text); }
.task-progress { flex: none; padding: 10px 14px 4px; }
.bar { height: 6px; border-radius: 99px; background: var(--panel-2); overflow: hidden; }
.bar-fill { height: 100%; background: var(--primary); transition: width .25s ease; }
.task-list { list-style: none; margin: 0; padding: 6px 8px 12px; overflow: auto; flex: 1; }
.task-list li { display: flex; gap: 8px; padding: 8px; border-radius: 8px; font-size: 13px; align-items: flex-start; }
.task-list li:hover { background: var(--panel-hover); }
.t-status { width: 16px; text-align: center; flex: none; }
.task-list .done { color: var(--success); }
.task-list .doing { color: var(--cta); }
.task-list .pending { color: var(--muted); }
.t-content { flex: 1; line-height: 1.45; }
.task-list li.done .t-content { text-decoration: line-through; color: var(--muted); }
.task-empty { padding: 24px 14px; color: var(--muted); font-size: 13px; text-align: center; }

.chat {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
}
.empty { text-align: center; color: var(--muted); padding: 60px 20px; }
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
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  background: var(--panel);
}
.composer textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px 14px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  background: var(--bg);
  color: var(--text);
  max-height: 160px;
  outline: none;
}
.composer textarea:focus { border-color: var(--accent); }
.send {
  flex: none;
  border: none;
  background: var(--cta-strong);
  color: var(--on-cta);
  padding: 11px 22px;
  border-radius: 12px;
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
.hitl-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.hitl-submit {
  margin-top: 12px; width: 100%; border: none; background: var(--accent); color: #fff;
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
