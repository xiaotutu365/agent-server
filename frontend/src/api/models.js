import { apiFetch } from '../auth'

/** 模型配置 API（大模型 / 嵌入 / 重排）。 */

export const MODEL_TYPES = [
  { value: 'llm', label: '大模型' },
  { value: 'embedding', label: '嵌入模型' },
  { value: 'rerank', label: '重排模型' },
]

async function jsonFetch(url, opts = {}) {
  const r = await apiFetch(url, opts)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  return data
}

export async function listModels(type) {
  const q = type ? `?type=${encodeURIComponent(type)}` : ''
  return (await jsonFetch(`/api/admin/models${q}`)).models || []
}

export async function createModel(body) {
  return (await jsonFetch('/api/admin/models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).model
}

export async function updateModel(id, body) {
  return (await jsonFetch(`/api/admin/models/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).model
}

export async function deleteModel(id) {
  return jsonFetch(`/api/admin/models/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/** 按提交的配置（未保存也可）探测连通性。 */
export async function testModel(cfg) {
  return jsonFetch('/api/admin/models/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
}

/** 按已保存的配置（含密钥）探测连通性。 */
export async function testModelById(id) {
  return jsonFetch(`/api/admin/models/${encodeURIComponent(id)}/test`, { method: 'POST' })
}
