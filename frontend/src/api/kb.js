import { apiFetch } from '../auth'

/** 知识库管理 API 封装（走 vite 代理到后端 :8000）。 */

async function jsonFetch(url, opts = {}) {
  const r = await apiFetch(url, opts)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  return data
}

export async function listKbs() {
  return (await jsonFetch('/api/kb')).kbs || []
}

export async function createKb(kbId, description = '') {
  return jsonFetch('/api/kb', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kb_id: kbId, description })
  })
}

export async function deleteKb(kbId) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}`, { method: 'DELETE' })
}

/** 上传文档：202 异步契约，返回 {task_id, kb_id, file}，入库进度经 getIngestTask 轮询（SPEC-kb-ocr-ingest C2）。 */
export async function uploadDoc(kbId, file) {
  const fd = new FormData()
  fd.append('file', file)
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/documents`, {
    method: 'POST',
    body: fd
  })
}

/** 查入库任务（轮询用）：全字段含 status/total_pages/done_pages/chunks/error/stats。 */
export async function getIngestTask(taskId) {
  return jsonFetch(`/api/kb/ingest-tasks/${encodeURIComponent(taskId)}`)
}

/** 进行中的入库任务列表（进入页面时恢复进度展示）。 */
export async function listActiveIngestTasks(kbId) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/ingest-tasks?active=true`)
}

export async function listDocuments(kbId) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/documents`)
}

export async function deleteDocument(kbId, file) {
  const params = new URLSearchParams({ file })
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/documents?${params}`, {
    method: 'DELETE'
  })
}

export async function searchKb(kbId, query, topK = 5) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK })
  })
}

export async function getKbSettings() {
  return (await jsonFetch('/api/kb/settings')) || {}
}

export async function saveKbSettings(patch) {
  return jsonFetch('/api/kb/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
}

/** 评测集：文件不存在时后端返回示例模板（template: true）。 */
export async function getEvalSet(kbId) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/evalset`)
}

export async function saveEvalSet(kbId, items) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/evalset`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items })
  })
}

export async function runEval(kbId, topK = null) {
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/eval/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(topK ? { top_k: topK } : {})
  })
}

/** 按 (source, chunk_idx) 取片段原文（对话引用 badge 点击查看）。 */
export async function getChunk(kbId, source, chunkIdx) {
  const params = new URLSearchParams({ source, chunk_idx: String(chunkIdx ?? 0) })
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/chunk?${params}`)
}

/** 分片预览：列出某文档全部片段（按 chunk_idx 升序）。 */
export async function listChunks(kbId, source) {
  const params = new URLSearchParams({ source })
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/chunks?${params}`)
}

/** 重新入库：202 异步契约，返回 {task_id, kb_id, file}；worker 成功后才删旧建新。 */
export async function reingestDocument(kbId, file) {
  return jsonFetch(
    `/api/kb/${encodeURIComponent(kbId)}/documents/reingest?file=${encodeURIComponent(file)}`,
    { method: 'POST' }
  )
}
