<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <span class="logo">◆</span>
        <div>
          <div class="title">DeepAgent</div>
          <div class="subtitle">LangChain · deepagents · Vue</div>
        </div>
      </div>
      <div class="top-actions">
        <span class="status" :class="statusClass">{{ statusText }}</span>
        <template v-if="isLoginPage"></template>
        <template v-else-if="authed">
          <nav class="nav">
            <RouterLink to="/" class="navlink">前台 · 对话</RouterLink>
            <RouterLink to="/langgraph-lab" class="navlink">LangGraph 实验</RouterLink>
            <RouterLink to="/eda" class="navlink">EDA 综合</RouterLink>
            <RouterLink v-if="user && user.role === 'admin'" to="/admin" class="navlink">后台 · 管理</RouterLink>
          </nav>
          <span class="user" v-if="user">
            {{ user.username }}<em v-if="user.role === 'admin'" class="role">管理员</em>
          </span>
          <button class="logout" @click="logout">登出</button>
        </template>
        <RouterLink v-else to="/login" class="navlink">登录</RouterLink>
      </div>
    </header>

    <main class="view">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getUser, clearAuth, isAuthed } from './auth'

const route = useRoute()
const user = ref(getUser())
const authed = ref(isAuthed())
watch(
  () => route.fullPath,
  () => {
    user.value = getUser()
    authed.value = isAuthed()
  }
)

const isLoginPage = computed(() => route.path === '/login')

const health = ref(null)
const statusText = computed(() => {
  if (health.value === null) return '检测中'
  return health.value ? `已连接 · ${health.value.model || 'model'}` : '后端未连接'
})
const statusClass = computed(() => (health.value ? 'ok' : 'bad'))

function logout() {
  clearAuth()
  location.hash = '#/login'
}

onMounted(async () => {
  try {
    const r = await fetch('/api/health')
    health.value = r.ok ? await r.json() : false
  } catch {
    health.value = false
  }
})
</script>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  width: 100%;
  background: var(--bg);
}

.topbar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, #4f6ef7, #8b5cf6);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.title { font-weight: 700; font-size: 16px; }
.subtitle { font-size: 12px; color: var(--muted); }
.top-actions { display: flex; align-items: center; gap: 12px; }
.status {
  font-size: 12px; padding: 4px 10px; border-radius: 20px;
  background: var(--code-bg); color: var(--muted);
}
.status.ok { color: #22a06b; }
.status.bad { color: #d93025; }
.nav { display: flex; border: 1px solid var(--border); border-radius: 9px; overflow: hidden; }
.navlink {
  border: none; background: transparent; color: var(--muted);
  padding: 6px 16px; cursor: pointer; font-size: 13px; text-decoration: none;
}
.navlink.router-link-active { background: var(--accent); color: #fff; }
.user { font-size: 13px; color: var(--text); display: flex; align-items: center; gap: 6px; }
.user .role { font-style: normal; font-size: 11px; background: #e6f4ec; color: #22a06b; padding: 1px 8px; border-radius: 20px; }
.logout {
  border: 1px solid var(--border); background: transparent; color: var(--muted);
  padding: 6px 14px; border-radius: 9px; cursor: pointer; font-size: 13px;
}
.logout:hover { color: var(--text); border-color: var(--text); }

.view { flex: 1; min-height: 0; display: flex; }
</style>
