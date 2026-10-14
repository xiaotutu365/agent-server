// 认证与请求封装：token 存取、JWT 角色解析、统一 apiFetch（自动带 Authorization + 401 跳登录）

const TOKEN_KEY = 'da_token'
const USER_KEY = 'da_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isAuthed() {
  return !!getToken()
}

// 仅前端读 JWT payload 的 role，用于路由守卫（不校验签名，仅做 UX 判断）
export function tokenRole() {
  const t = getToken()
  if (!t) return null
  try {
    const p = t.split('.')[1]
    const json = JSON.parse(atob(p))
    if (json.exp && json.exp * 1000 < Date.now()) return null
    return json.role
  } catch {
    return null
  }
}

async function login(username, password) {
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(data.detail || '登录失败')
  setAuth(data.token, data.user)
  return data.user
}

export { login }

// 统一请求：自动注入 Authorization；401 时清登录态并跳登录页
export async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const t = getToken()
  if (t) headers['Authorization'] = 'Bearer ' + t
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  const resp = await fetch(path, { ...options, headers })
  if (resp.status === 401) {
    clearAuth()
    if (location.hash.replace('#', '') !== '/login') location.hash = '#/login'
    throw new Error('登录已过期，请重新登录')
  }
  return resp
}
