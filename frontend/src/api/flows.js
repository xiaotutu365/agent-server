import { apiFetch } from '../auth'

/** 流程配置与运行 API 封装（SPEC-flow-config 3.4/3.5）。 */

async function jsonFetch(url, opts = {}) {
  const r = await apiFetch(url, opts)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  return data
}

const jsonOpts = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body)
})

// ---------- 流程 CRUD（管理员） ----------

export async function listFlows() {
  return (await jsonFetch('/api/flows')).flows || []
}

export async function createFlow(name, definition) {
  return (await jsonFetch('/api/flows', jsonOpts('POST', { name, definition }))).flow
}

export async function updateFlow(flowId, patch) {
  return (await jsonFetch(`/api/flows/${encodeURIComponent(flowId)}`, jsonOpts('PUT', patch))).flow
}

export async function deleteFlow(flowId) {
  return jsonFetch(`/api/flows/${encodeURIComponent(flowId)}`, { method: 'DELETE' })
}

// ---------- 实例：发起 / 查询 / 人审 / 取消（登录用户） ----------

export async function startFlowRun(flowId, input = {}) {
  return (await jsonFetch(`/api/flows/${encodeURIComponent(flowId)}/runs`,
    jsonOpts('POST', { input }))).run
}

export async function listFlowRuns(flowId = null) {
  const q = flowId ? `?flow_id=${encodeURIComponent(flowId)}` : ''
  return (await jsonFetch(`/api/flow-runs${q}`)).runs || []
}

/** 返回 { run, pending }；pending = { node, prompt, output_key }（waiting_human 时非空） */
export async function getFlowRun(runId) {
  return jsonFetch(`/api/flow-runs/${encodeURIComponent(runId)}`)
}

/** 人审决策：decision = 'approved' | 'rejected'，comment 为意见（rejected 回环时给修订节点） */
export async function resumeFlowRun(runId, decision, comment = '') {
  const body = { decision }
  if (comment) body.comment = comment
  return (await jsonFetch(`/api/flow-runs/${encodeURIComponent(runId)}/resume`,
    jsonOpts('POST', body))).run
}

export async function cancelFlowRun(runId) {
  return (await jsonFetch(`/api/flow-runs/${encodeURIComponent(runId)}/cancel`,
    { method: 'POST' })).run
}

// ---------- SSE 进度流（GET /api/flow-runs/{id}/stream） ----------

/**
 * 事件：flow_step {node,status} / flow_status {status,current_node,error} / done / error {message}
 * 帧解析与 api/chat.js 同构（fetch + ReadableStream，空行分帧）。
 */
export async function streamFlowRun(runId, handlers, signal) {
  const resp = await apiFetch(`/api/flow-runs/${encodeURIComponent(runId)}/stream`, { signal })
  if (!resp.ok || !resp.body) throw new Error(`订阅失败: HTTP ${resp.status}`)

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const dispatch = (event, dataStr) => {
    let data = {}
    try { data = JSON.parse(dataStr) } catch { return }
    switch (event) {
      case 'flow_step': handlers.onStep?.(data); break
      case 'flow_status': handlers.onStatus?.(data); break
      case 'error': handlers.onError?.(data.message); break
      case 'done': handlers.onDone?.(); break
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      const dataLines = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length) dispatch(event, dataLines.join('\n'))
    }
  }
}
