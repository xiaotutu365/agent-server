<template>
  <div class="run-page">
    <div class="page-head">
      <div>
        <h2>流程运行</h2>
        <p class="hint">发起流程实例并实时查看节点进度；human 节点会暂停等待审批。</p>
      </div>
      <button class="btn btn-ghost btn-sm" @click="loadRuns">刷新列表</button>
    </div>

    <div v-if="pageError" class="err">{{ pageError }}</div>

    <!-- 发起面板（能读到流程列表的用户可见） -->
    <div v-if="flows.length" class="card start-card">
      <div class="start-row">
        <label class="field start-field">
          <span>流程</span>
          <select v-model="selectedFlowId" class="select">
            <option value="">请选择…</option>
            <option v-for="f in flows" :key="f.flow_id" :value="f.flow_id">
              {{ f.name }}（v{{ f.version }}）
            </option>
          </select>
        </label>
        <label class="field start-field grow">
          <span>输入（JSON，供 ${input.xxx} 插值）</span>
          <input v-model="inputText" class="input" placeholder='如 {"topic": "秋季新品"}' />
        </label>
        <button class="btn btn-primary start-btn" :disabled="!selectedFlowId || starting" @click="start">
          {{ starting ? '发起中…' : '发起运行' }}
        </button>
      </div>
      <div v-if="startError" class="err start-err">{{ startError }}</div>
    </div>

    <div class="main-cols">
      <!-- 实例列表 -->
      <div class="card list-col">
        <div class="col-title">运行实例</div>
        <div v-if="!runs.length" class="muted pad">暂无实例</div>
        <button
          v-for="r in runs" :key="r.run_id"
          class="run-item" :class="{ active: r.run_id === selectedRunId }"
          @click="selectRun(r.run_id)"
        >
          <span class="badge" :class="badgeCls(r.status)">{{ statusLabel(r.status) }}</span>
          <span class="run-meta">
            <span class="run-name">{{ flowName(r.flow_id) }}</span>
            <span class="run-sub">{{ r.current_node ? `节点 ${r.current_node}` : '' }} · {{ fmtTime(r.updated_at) }}</span>
          </span>
        </button>
      </div>

      <!-- 实例详情 -->
      <div class="card detail-col">
        <div v-if="!selectedRunId" class="muted pad">选择左侧实例查看进度</div>
        <template v-else>
          <div class="detail-head">
            <span class="badge" :class="badgeCls(status)">{{ statusLabel(status) }}</span>
            <span class="detail-node">
              {{ currentNode ? `当前节点：${currentNode}` : '' }}
            </span>
            <span class="spacer"></span>
            <button
              v-if="status === 'running' || status === 'waiting_human'"
              class="btn btn-danger btn-sm" @click="cancel"
            >取消</button>
          </div>
          <div v-if="error" class="err">{{ error }}</div>
          <div v-if="streamError" class="err">{{ streamError }}</div>

          <div class="timeline">
            <div v-if="!steps.length" class="muted pad">等待节点事件…</div>
            <div v-for="(s, i) in steps" :key="i" class="tl-item" :class="s.status">
              <span class="tl-dot" aria-hidden="true"></span>
              <span class="tl-node">{{ s.node }}</span>
              <span class="tl-status">{{ s.status === 'running' ? '执行中' : '完成' }}</span>
            </div>
          </div>

          <div v-if="pending" class="hitl-panel">
            <div class="hitl-head">⏸ 需要人工审批：{{ pending.node }}</div>
            <div class="hitl-prompt">{{ pending.prompt }}</div>
            <textarea v-model="comment" class="textarea hitl-comment" rows="2" placeholder="审批意见（拒绝时作为修订要求传给下游节点，可选）"></textarea>
            <div class="hitl-actions">
              <button class="btn btn-primary" :disabled="submitting" @click="decide('approved')">批准</button>
              <button class="btn btn-danger" :disabled="submitting" @click="decide('rejected')">拒绝并退回修订</button>
            </div>
          </div>

          <div v-if="outputs.length" class="outputs">
            <div class="col-title">节点产出</div>
            <div v-for="[k, v] in outputs" :key="k" class="out-block">
              <div class="out-key">{{ k }}</div>
              <pre class="out-val">{{ typeof v === 'string' ? v : JSON.stringify(v, null, 2) }}</pre>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  listFlows, listFlowRuns, getFlowRun, startFlowRun,
  resumeFlowRun, cancelFlowRun, streamFlowRun
} from '../api/flows'

const route = useRoute()

const flows = ref([])
const runs = ref([])
const pageError = ref('')

const selectedFlowId = ref(route.query.flow_id || '')
const inputText = ref('{}')
const startError = ref('')
const starting = ref(false)

const selectedRunId = ref('')
const status = ref('')
const currentNode = ref('')
const error = ref('')
const pending = ref(null)
const runOutputs = ref({})
const steps = reactive([])
const streamError = ref('')
const comment = ref('')
const submitting = ref(false)

let controller = null
let pollTimer = null

const outputs = computed(() => Object.entries(runOutputs.value))

const STATUS_LABELS = {
  running: '运行中', waiting_human: '等待审批', done: '完成',
  failed: '失败', cancelled: '已取消'
}
function statusLabel(s) { return STATUS_LABELS[s] || s }
function badgeCls(s) {
  return {
    running: 'badge-primary', waiting_human: 'badge-cta',
    done: 'badge-success', failed: 'badge-danger', cancelled: ''
  }[s] || ''
}
function flowName(fid) {
  const f = flows.value.find((x) => x.flow_id === fid)
  return f ? f.name : fid.slice(0, 8)
}
function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString()
}

async function loadFlows() {
  try {
    flows.value = await listFlows()
  } catch { /* 非管理员读不到流程列表：隐藏发起面板即可 */ }
}

async function loadRuns() {
  pageError.value = ''
  try {
    runs.value = await listFlowRuns()
  } catch (e) {
    pageError.value = e.message || String(e)
  }
}

async function start() {
  if (!selectedFlowId.value || starting.value) return
  startError.value = ''
  let input
  try {
    input = inputText.value.trim() ? JSON.parse(inputText.value) : {}
  } catch (e) {
    startError.value = `输入不是合法 JSON：${e.message}`
    return
  }
  starting.value = true
  try {
    const run = await startFlowRun(selectedFlowId.value, input)
    await loadRuns()
    selectRun(run.run_id)
  } catch (e) {
    startError.value = e.message || String(e)
  } finally {
    starting.value = false
  }
}

function resetDetail() {
  status.value = ''
  currentNode.value = ''
  error.value = ''
  pending.value = null
  runOutputs.value = {}
  streamError.value = ''
  comment.value = ''
  steps.splice(0)
}

async function selectRun(runId) {
  if (controller) controller.abort()
  selectedRunId.value = runId
  resetDetail()
  await openStream(runId)
  await refreshRun(runId)
}

// SSE 订阅：快照+历史回放+实时跟随；连接自然结束（done）后若仍在执行则重连
async function openStream(runId) {
  controller = new AbortController()
  const signal = controller.signal
  try {
    await streamFlowRun(runId, {
      onStep(d) {
        if (runId !== selectedRunId.value) return
        steps.push({ node: d.node, status: d.status })
      },
      onStatus(d) {
        if (runId !== selectedRunId.value) return
        status.value = d.status
        if (d.current_node !== undefined) currentNode.value = d.current_node
        error.value = d.error || ''
      },
      onError(m) {
        if (runId !== selectedRunId.value) return
        streamError.value = m || '进度流异常'
      },
      onDone() { /* 收尾统一走 finally 的续订判断 */ }
    }, signal)
  } catch (err) {
    if (err.name !== 'AbortError' && runId === selectedRunId.value) {
      streamError.value = err.message || String(err)
    }
    return
  } finally {
    if (controller && signal.aborted) return
    controller = null
  }
  // 流正常结束但实例未到终态（如人审暂停后 resume 的新执行段）→ 刷新并续订
  if (runId !== selectedRunId.value) return
  await refreshRun(runId)
  if (status.value === 'running') openStream(runId)
}

async function refreshRun(runId) {
  try {
    const { run, pending: p } = await getFlowRun(runId)
    if (runId !== selectedRunId.value) return
    status.value = run.status
    currentNode.value = run.current_node || ''
    error.value = run.error || ''
    pending.value = p
    runOutputs.value = run.outputs || {}
  } catch (e) {
    if (runId === selectedRunId.value) streamError.value = e.message || String(e)
  }
}

async function decide(decision) {
  if (!pending.value || submitting.value) return
  submitting.value = true
  streamError.value = ''
  try {
    await resumeFlowRun(selectedRunId.value, decision, comment.value.trim())
    pending.value = null
    status.value = 'running'
    await openStream(selectedRunId.value)
    await loadRuns()
  } catch (e) {
    streamError.value = e.message || String(e)
  } finally {
    submitting.value = false
  }
}

async function cancel() {
  if (!confirm('确认取消该运行实例？')) return
  try {
    await cancelFlowRun(selectedRunId.value)
    await refreshRun(selectedRunId.value)
    await loadRuns()
  } catch (e) {
    streamError.value = e.message || String(e)
  }
}

onMounted(async () => {
  await Promise.all([loadFlows(), loadRuns()])
  if (route.query.run_id) selectRun(route.query.run_id)
  pollTimer = setInterval(loadRuns, 5000)
})

onUnmounted(() => {
  if (controller) controller.abort()
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.run-page { max-width: 1280px; margin: 0 auto; padding: 20px 24px; }
.pad { padding: 14px; }
.spacer { flex: 1; }

.start-card { padding: 14px 16px; margin-bottom: 14px; }
.start-row { display: flex; gap: 14px; align-items: flex-end; flex-wrap: wrap; }
.start-field { margin-bottom: 0; min-width: 220px; }
.grow { flex: 1; }
.start-btn { margin-bottom: 1px; }
.start-err { margin-top: 10px; }

.main-cols { display: flex; gap: 14px; align-items: flex-start; }
.list-col { width: 320px; flex: none; max-height: 70vh; overflow-y: auto; padding: 8px; }
.detail-col { flex: 1; min-width: 0; padding: 14px 16px; }
.col-title { font-size: 13px; font-weight: 600; color: var(--muted); padding: 8px 10px 6px; }

.run-item {
  display: flex; gap: 10px; align-items: center; width: 100%;
  background: transparent; border: none; border-radius: var(--radius-sm);
  padding: 9px 10px; cursor: pointer; text-align: left; font-family: inherit;
}
.run-item:hover { background: var(--panel-hover); }
.run-item.active { background: color-mix(in srgb, var(--primary) 12%, transparent); }
.run-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.run-name { font-size: 13px; font-weight: 600; color: var(--text); }
.run-sub { font-size: 12px; color: var(--muted); }

.detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.detail-node { font-size: 13px; color: var(--muted); }

.timeline { display: flex; flex-direction: column; gap: 2px; margin: 8px 0 14px; }
.tl-item { display: flex; align-items: center; gap: 10px; padding: 7px 8px; border-radius: var(--radius-sm); font-size: 13px; }
.tl-item:hover { background: var(--panel-hover); }
.tl-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); flex: none; }
.tl-item.running .tl-dot { background: var(--primary-strong); animation: pulse 1.2s infinite; }
.tl-node { font-weight: 600; }
.tl-status { color: var(--muted); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

.hitl-panel {
  border: 1px solid color-mix(in srgb, var(--cta-strong) 45%, transparent);
  background: color-mix(in srgb, var(--cta) 8%, transparent);
  border-radius: var(--radius-md); padding: 14px 16px; margin-bottom: 14px;
}
.hitl-head { font-weight: 600; font-size: 14px; margin-bottom: 8px; }
.hitl-prompt { font-size: 13px; color: var(--text-2); margin-bottom: 10px; white-space: pre-wrap; }
.hitl-comment { margin-bottom: 10px; }
.hitl-actions { display: flex; gap: 10px; }

.out-block { margin-bottom: 10px; }
.out-key { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
.out-val {
  margin: 0; padding: 10px 12px; background: var(--panel-2);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 12.5px; white-space: pre-wrap; word-break: break-word;
  max-height: 260px; overflow-y: auto;
}

@media (max-width: 860px) {
  .main-cols { flex-direction: column; }
  .list-col { width: 100%; max-height: 260px; }
}
</style>
