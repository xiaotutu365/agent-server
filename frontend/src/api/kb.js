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

export async function uploadDoc(kbId, file) {
  const fd = new FormData()
  fd.append('file', file)
  return jsonFetch(`/api/kb/${encodeURIComponent(kbId)}/documents`, {
    method: 'POST',
    body: fd
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
