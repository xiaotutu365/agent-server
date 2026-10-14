<template>
  <div class="lab">
    <header class="lab-head">
      <div class="lab-title">
        <h1>LangGraph 实验台 · HITL</h1>
        <p>
          独立测试 LangGraph 的 <code>interrupt()</code> / <code>Command(resume=…)</code>
          人机中断恢复能力，复用现有 <code>deep_agent</code> 的 <code>INTERRUPT_TOOLS</code>
          （<code>ask_human</code> → respond、<code>create_work_order</code> → approve/reject）。
          本页会话与「对话」逻辑隔离，不互相污染。
        </p>
      </div>
      <div class="thread-box">
        <span class="muted">thread</span>
        <code>{{ threadId }}</code>
        <button class="ghost" :disabled="streaming" @click="reset">重置实验</button>
      </div>
    </header>

    <section class="scenarios">
      <button class="scn" @click="runScenario('ask')">
        <b>场景 A · 主动提问</b>
        <span>触发 <code>ask_human</code> → <b>respond</b> 中断：图挂起，等你回答后再继续</span>
      </button>
      <button class="scn" @click="runScenario('order')">
        <b>场景 B · 业务确认</b>
        <span>触发 <code>create_work_order</code> → <b>approve / reject</b> 中断：写操作执行前需你确认</span>
      </button>
    </section>

    <section class="composer">
      <textarea
        v-model="input"
        ref="inputEl"
        rows="2"
        :disabled="!!pending"
        placeholder="或直接输入任意消息（Enter 发送，Shift+Enter 换行）"
        @keydown="onKeydown"
      ></textarea>
      <button
        v-if="!streaming"
        class="send"
        :disabled="!input.trim() || !!pending"
        @click="send()"
      >发送</button>
      <button v-else class="send stop" @click="stop">停止</button>
    </section>

    <!-- HITL 中断决策面板 -->
    <section v-if="pending" class="hitl">
      <div class="hitl-head">⏸ 图已中断（interrupt）—— 需要你的决策</div>
      <details class="raw-wrap">
        <summary>查看原始 HITLRequest（LangGraph interrupt value）</summary>
        <pre class="raw">{{ pretty(pending.requests) }}</pre>
      </details>

      <div v-for="(req, ri) in pending.requests" :key="ri" class="hitl-req-group">
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
            <button
              v-for="dt in allowedDecisions(req, ai)"
              :key="dt"
              class="hitl-btn"
              :class="{ active: choiceType(ri, ai) === dt }"
              @click="setType(ri, ai, dt)"
            >{{ decisionLabel(dt) }}</button>
            <textarea
              v-if="choiceType(ri, ai) === 'respond' || choiceType(ri, ai) === 'reject'"
              v-model="pending.choices[choiceIndex(ri, ai)].message"
              class="hitl-input"
              :placeholder="choiceType(ri, ai) === 'respond' ? '输入你的回答…' : '拒绝理由（可选）'"
              rows="2"
            ></textarea>
            <textarea
              v-if="choiceType(ri, ai) === 'edit'"
              v-model="pending.choices[choiceIndex(ri, ai)].argsText"
              class="hitl-input hitl-json"
              placeholder="编辑工具参数 JSON"
              rows="4"
            ></textarea>
          </div>
        </div>
      </div>
      <button class="hitl-submit" @click="respondInterrupt">提交决策（resume 恢复图）</button>
    </section>

    <!-- 执行时间线 -->
    <section class="timeline">
      <div v-for="(e, i) in log" :key="i" class="tl" :class="'tl-' + e.type">
        <div class="tl-tag">{{ tagOf(e) }}</div>
        <div class="tl-body">
          <span v-if="e.type === 'tool'">
            <b>{{ e.name }}</b>
            <span class="muted" v-if="e.input"> · 入参: {{ e.input }}</span>
            <div v-if="e.output" class="tl-out">↳ {{ e.output }}</div>
          </span>
          <span v-else-if="e.type === 'assistant'">{{ e.text || '（思考中…）' }}</span>
          <span v-else-if="e.type === 'user'"><b>你：</b>{{ e.text }}</span>
          <span v-else-if="e.type === 'interrupt'">图已挂起，等待决策（HITLRequest 见上方面板）</span>
          <span v-else-if="e.type === 'resume'">恢复图 → <code>{{ pretty(e.decisions) }}</code></span>
          <span v-else>{{ e.text }}</span>
        </div>
      </div>
      <div v-if="!log.length" class="tl-empty">点击上方场景按钮，或输入消息开始实验。</div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { streamChat } from '../api/chat'

const threadId = ref(genId('lab-'))
const input = ref('')
const streaming = ref(false)
const pending = ref(null)
const log = reactive([])
const inputEl = ref(null)
let controller = null
let assistantAcc = null

const SCENARIOS = {
  ask: '请在回答前先调用 ask_human 工具向我提一个问题（例如确认我偏好的回答语言），等我回复后再继续完成你的回答。',
  order: '请调用 create_work_order 工具为我创建一个测试工单：标题「LangGraph 实验」，优先级 medium，描述「HITL 中断恢复测试」。',
}

function genId(p) {
  return p + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4)
}

function reset() {
  if (streaming.value) return
  threadId.value = genId('lab-')
  log.splice(0, log.length)
  pending.value = null
  assistantAcc = null
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function pretty(o) {
  try { return JSON.stringify(o, null, 2) } catch { return String(o) }
}

function pushAssistant(text = '') {
  const e = { type: 'assistant', text }
  log.push(e)
  assistantAcc = e
  return e
}

function makeHandlers() {
  return {
    onToken(t) {
      if (!assistantAcc) assistantAcc = pushAssistant()
      assistantAcc.text += t
    },
    onToolStart(d) {
      assistantAcc = null
      log.push({ type: 'tool', name: d.tool, input: d.input, output: '' })
    },
    onToolEnd(d) {
      const tools = log.filter((x) => x.type === 'tool')
      for (let i = tools.length - 1; i >= 0; i--) {
        if (tools[i].name === d.tool && !tools[i].output) {
          tools[i].output = d.output
          break
        }
      }
      assistantAcc = null
    },
    onPlan() { assistantAcc = null },
    onInterrupt(d) {
      log.push({ type: 'interrupt' })
      pending.value = buildPending(d.requests || [])
    },
    onError(m) { log.push({ type: 'error', text: m || '未知错误' }) },
    onDone() { assistantAcc = null },
  }
}

function buildPending(reqs) {
  const choices = []
  for (const r of reqs) {
    const ars = r.action_requests || []
    const rcs = r.review_configs || []
    ars.forEach((ar, i) => {
      const allowed = (rcs[i] && rcs[i].allowed_decisions) || []
      choices.push({
        type: allowed[0] || 'approve',
        message: '',
        argsText: JSON.stringify(ar.args || {}, null, 2),
        editedAction: { name: ar.name || '', args: ar.args || {} },
      })
    })
  }
  return { requests: reqs, choices }
}

function allowedDecisions(req, ai) {
  const rcs = req.review_configs || []
  const cfg = rcs[ai]
  return (cfg && cfg.allowed_decisions) || []
}
function choiceIndex(ri, ai) {
  const reqs = pending.value?.requests || []
  let idx = 0
  for (let r = 0; r < ri; r++) idx += (reqs[r].action_requests || []).length
  return idx + ai
}
function choiceType(ri, ai) {
  const c = pending.value?.choices[choiceIndex(ri, ai)]
  return c ? c.type : ''
}
function setType(ri, ai, t) {
  const c = pending.value?.choices[choiceIndex(ri, ai)]
  if (c) c.type = t
}

async function runScenario(key) {
  input.value = ''
  await send(SCENARIOS[key])
}

async function send(text) {
  const content = (text ?? input.value).trim()
  if (!content || streaming.value || pending.value) return
  input.value = ''
  log.push({ type: 'user', text: content })
  pushAssistant()
  streaming.value = true
  controller = new AbortController()
  try {
    await streamChat(content, threadId.value, makeHandlers(), controller.signal)
  } catch (err) {
    if (err.name !== 'AbortError') log.push({ type: 'error', text: err.message || String(err) })
  } finally {
    streaming.value = false
    controller = null
  }
}

async function respondInterrupt() {
  const pi = pending.value
  if (!pi || streaming.value) return
  const decisions = pi.choices.map((c) => {
    if (c.type === 'edit') {
      let args = c.editedAction.args
      try { args = JSON.parse(c.argsText) } catch { /* 保留原 args */ }
      return { type: 'edit', edited_action: { name: c.editedAction.name, args } }
    }
    if (c.type === 'respond') return { type: 'respond', message: c.message }
    if (c.type === 'reject') return { type: 'reject', message: c.message || undefined }
    return { type: c.type } // approve
  })
  log.push({ type: 'resume', decisions })
  pending.value = null
  pushAssistant()
  streaming.value = true
  controller = new AbortController()
  try {
    await streamChat('', threadId.value, makeHandlers(), controller.signal, { decisions })
  } catch (err) {
    if (err.name !== 'AbortError') log.push({ type: 'error', text: err.message || String(err) })
  } finally {
    streaming.value = false
    controller = null
  }
}

function stop() {
  controller?.abort()
  controller = null
  streaming.value = false
}

// ---------- 展示辅助 ----------
const TOOL_LABELS = {
  create_work_order: '创建工单',
  ask_human: '向你提问',
  query_customer: '查询客户档案',
}
function toolLabel(n) { return TOOL_LABELS[n] || (n ? `调用工具：${n}` : '待确认操作') }

const ARG_LABELS = {
  phone: '客户手机号', customer_phone: '客户手机号', customer_id: '客户 ID',
  title: '工单标题', priority: '优先级', description: '问题描述',
  name: '名称', query: '查询内容', search: '查询内容',
  order_id: '工单 ID', reason: '原因',
}
function argLabel(k) { return ARG_LABELS[k] || k.replace(/_/g, ' ') }

const VALUE_LABELS = { priority: { urgent: '紧急', high: '高', medium: '中', low: '低' } }
function argEntries(args) { return Object.entries(args).filter(([k]) => k !== 'question') }
function formatVal(k, v) {
  if (v == null) return '—'
  if (VALUE_LABELS[k] && VALUE_LABELS[k][v]) return VALUE_LABELS[k][v]
  if (['string', 'number', 'boolean'].includes(typeof v)) return String(v)
  try { return JSON.stringify(v) } catch { return String(v) }
}

const DEC_LABELS = {
  approve: '批准执行', reject: '拒绝', respond: '回答并继续', edit: '修改参数后执行',
}
function decisionLabel(d) { return DEC_LABELS[d] || d }

function tagOf(e) {
  return {
    user: '你', assistant: 'Agent', tool: '工具',
    interrupt: 'interrupt', resume: 'resume', error: '错误', info: '信息',
  }[e.type] || e.type
}
</script>

<style scoped>
.lab {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 22px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1120px;
  margin: 0 auto;
}
.lab-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.lab-title h1 { margin: 0 0 6px; font-size: 20px; }
.lab-title p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; max-width: 720px; }
.lab-title code {
  font-family: var(--mono); background: var(--code-bg);
  padding: 1px 6px; border-radius: 4px; font-size: 0.9em;
}
.thread-box {
  display: flex; align-items: center; gap: 8px;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 8px 12px; font-size: 12px;
}
.thread-box code { font-family: var(--mono); color: var(--accent); }
.ghost {
  border: 1px solid var(--border); background: transparent; color: var(--muted);
  padding: 5px 12px; border-radius: 8px; cursor: pointer; font-size: 12px;
}
.ghost:hover:not(:disabled) { color: var(--text); border-color: var(--text); }
.ghost:disabled { opacity: 0.5; cursor: not-allowed; }

.scenarios { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.scn {
  text-align: left; border: 1px solid var(--border); background: var(--panel);
  border-radius: 12px; padding: 14px 16px; cursor: pointer; display: flex;
  flex-direction: column; gap: 6px; transition: all 0.15s;
}
.scn:hover { border-color: var(--accent); background: var(--panel-hover); }
.scn b { font-size: 14px; color: var(--text); }
.scn span { font-size: 12px; color: var(--muted); line-height: 1.5; }
.scn code { font-family: var(--mono); background: var(--code-bg); padding: 0 4px; border-radius: 3px; }

.composer {
  display: flex; gap: 10px; align-items: flex-end;
  border: 1px solid var(--border); border-radius: 12px; padding: 12px;
  background: var(--panel);
}
.composer textarea {
  flex: 1; resize: none; border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; font-family: inherit; font-size: 13px; line-height: 1.5;
  background: var(--bg); color: var(--text); outline: none;
}
.composer textarea:focus { border-color: var(--accent); }
.send {
  flex: none; border: none; background: var(--accent); color: #fff;
  padding: 10px 20px; border-radius: 10px; cursor: pointer; font-size: 13px; font-weight: 600;
}
.send:disabled { opacity: 0.5; cursor: not-allowed; }
.send.stop { background: var(--destructive); }

.hitl {
  border: 1px solid var(--accent); border-radius: 12px; padding: 14px 16px;
  background: var(--panel);
}
.hitl-head { font-weight: 600; color: var(--text); margin-bottom: 10px; font-size: 14px; }
.raw-wrap { margin-bottom: 10px; }
.raw-wrap summary { cursor: pointer; color: var(--muted); font-size: 12px; }
.raw {
  background: var(--code-bg); padding: 10px 12px; border-radius: 8px;
  overflow-x: auto; font-size: 12px; line-height: 1.5; margin-top: 8px;
}
.hitl-req-group { display: flex; flex-direction: column; gap: 10px; }
.hitl-req {
  border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; background: var(--bg);
}
.hitl-q { color: var(--text); font-size: 14px; line-height: 1.5; margin-bottom: 8px; }
.hitl-tool { color: var(--accent); font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.hitl-args { width: 100%; border-collapse: collapse; margin: 0 0 8px; font-size: 13px; }
.hitl-args th {
  text-align: left; color: var(--muted); font-weight: 500;
  padding: 4px 12px 4px 0; white-space: nowrap; vertical-align: top; width: 92px;
}
.hitl-args td { color: var(--text); padding: 4px 0; word-break: break-word; line-height: 1.5; }
.hitl-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.hitl-input {
  flex: 1 1 100%; resize: none; min-height: 38px;
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  font-family: inherit; font-size: 13px; background: var(--bg); color: var(--text);
}
.hitl-input:focus { border-color: var(--accent); outline: none; }
.hitl-json { font-family: var(--mono); font-size: 12px; }
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

.timeline {
  display: flex; flex-direction: column; gap: 8px;
  border-top: 1px solid var(--border); padding-top: 14px;
}
.tl {
  display: flex; gap: 10px; align-items: flex-start;
  border: 1px solid var(--border); border-radius: 10px; padding: 8px 12px; background: var(--panel);
  font-size: 13px; line-height: 1.55;
}
.tl-tag {
  flex: none; width: 72px; text-align: center; font-size: 11px; font-weight: 600;
  color: var(--muted); background: var(--code-bg); border-radius: 6px; padding: 3px 0;
}
.tl-body { flex: 1; min-width: 0; word-break: break-word; }
.tl-body code { font-family: var(--mono); background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }
.tl-out { color: var(--muted); margin-top: 2px; }
.tl-interrupt { border-color: var(--accent); }
.tl-interrupt .tl-tag { color: var(--accent); }
.tl-resume .tl-tag { color: var(--success); }
.tl-error { border-color: var(--destructive); }
.tl-error .tl-tag { color: var(--destructive); }
.tl-empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px; }
.muted { color: var(--muted); }
</style>
