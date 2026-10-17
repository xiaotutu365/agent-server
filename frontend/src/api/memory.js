import { apiFetch } from '../auth'

/** 记忆管理 API 封装（管理端点，需管理员）。 */

async function jsonFetch(url, opts = {}) {
  const r = await apiFetch(url, opts)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  return data
}

export async function listMemories(userId = '', enabled = '') {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (enabled !== '') params.set('enabled', enabled)
  const q = params.toString()
  return (await jsonFetch(`/api/memory${q ? '?' + q : ''}`)).memories || []
}

export async function addMemory(content) {
  return (await jsonFetch('/api/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  })).memory
}

export async function setMemoryEnabled(id, enabled) {
  return (await jsonFetch(`/api/memory/${encodeURIComponent(id)}/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled })
  })).memory
}

export async function forgetMemory(id) {
  return jsonFetch(`/api/memory/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
