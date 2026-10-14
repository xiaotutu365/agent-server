<template>
  <div class="app-root">
    <header class="topbar">
      <div class="brand" @click="$router.push('/')" role="button" tabindex="0"
           @keydown.enter="$router.push('/')">
        <svg class="brand-mark" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="2" y="2" width="28" height="28" rx="8" fill="var(--primary-strong)"/>
          <circle cx="10" cy="10" r="3" fill="#fff"/>
          <circle cx="22" cy="10" r="3" fill="#fff"/>
          <circle cx="16" cy="22" r="3" fill="#fff"/>
          <path d="M10 10 L16 22 M22 10 L16 22" stroke="#fff" stroke-width="2" fill="none"/>
        </svg>
        <span class="brand-name">AgentServer</span>
      </div>

      <nav class="mainnav" v-if="showNav" aria-label="主导航">
        <router-link v-for="n in nav" :key="n.to" :to="n.to" class="navlink">
          <Icon :name="n.icon" :size="18" />
          <span>{{ n.label }}</span>
        </router-link>
        <router-link v-if="isAdmin" to="/admin" class="navlink">
          <Icon name="settings" :size="18" />
          <span>后台 · 管理</span>
        </router-link>
      </nav>

      <div class="topbar-right">
        <span class="status" :class="{ up: healthy }" role="status" :aria-label="healthy ? '服务正常' : '服务异常'">
          <span class="dot"></span>{{ healthy ? '服务正常' : '服务异常' }}
        </span>

        <button class="icon-btn" @click="toggleTheme" :aria-label="theme === 'dark' ? '切换亮色主题' : '切换暗色主题'">
          <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
        </button>

        <div class="usermenu" v-if="user">
          <button class="userbtn" @click="menuOpen = !menuOpen" :aria-expanded="menuOpen" aria-haspopup="true">
            <span class="avatar">{{ initial }}</span>
            <span class="uname">{{ user.username }}</span>
            <Icon name="chevronDown" :size="14" />
          </button>
          <div class="menu" v-if="menuOpen" v-click-outside="() => (menuOpen = false)">
            <div class="menu-head">
              <div class="menu-name">{{ user.username }}</div>
              <div class="menu-role">{{ roleLabel }}</div>
            </div>
            <button class="menu-item" @click="logout">
              <Icon name="logout" :size="16" /><span>退出登录</span>
            </button>
          </div>
        </div>
        <router-link v-else-if="!isLoginPage" to="/login" class="navlink">登录</router-link>
      </div>
    </header>

    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getUser, clearAuth, isAuthed, apiFetch } from './auth'
import Icon from './components/Icon.vue'

const router = useRouter()
const route = useRoute()
const user = ref(getUser())
const authed = ref(isAuthed())
const menuOpen = ref(false)
const healthy = ref(false)
const theme = ref('light')

const nav = [
  { to: '/', label: '对话', icon: 'chat' },
  { to: '/langgraph-lab', label: '实验室', icon: 'lab' },
  { to: '/eda', label: '数据分析', icon: 'eda' },
]

// 路由变化时刷新登录态（登录/登出后顶栏立即更新）
watch(
  () => route.fullPath,
  () => {
    user.value = getUser()
    authed.value = isAuthed()
    menuOpen.value = false
  }
)

const isLoginPage = computed(() => route.path === '/login')
const showNav = computed(() => !isLoginPage.value && authed.value)
const isAdmin = computed(() => user.value?.role === 'admin')

const initial = computed(() => (user.value?.username || '?').slice(0, 1).toUpperCase())
const roleLabel = computed(() => {
  const r = user.value?.role
  return r === 'admin' ? '管理员' : r === 'auditor' ? '审计员' : '普通用户'
})

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value)
  try { localStorage.setItem('as-theme', theme.value) } catch (e) {}
}
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  applyTheme()
}
function initTheme() {
  let t = 'light'
  try { t = localStorage.getItem('as-theme') } catch (e) {}
  if (!t) t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  theme.value = t
  applyTheme()
}

function logout() {
  clearAuth()
  router.push('/login')
}

// 点击外部关闭菜单
const vClickOutside = {
  mounted(el, binding) {
    el._h = (e) => { if (!el.contains(e.target)) binding.value(e) }
    document.addEventListener('click', el._h)
  },
  unmounted(el) { document.removeEventListener('click', el._h) },
}

// 健康检查用原生 fetch（公开接口，未登录也可用，避免 apiFetch 的 401 跳转副作用）
async function checkHealth() {
  try {
    const r = await fetch('/api/health')
    if (!r.ok) return false
    const j = await r.json().catch(() => ({}))
    return j.status === 'ok'
  } catch (e) { return false }
}

onMounted(async () => {
  initTheme()
  healthy.value = await checkHealth()
})
</script>

<style scoped>
.app-root { display: flex; flex-direction: column; height: 100%; background: var(--bg); }
.topbar {
  position: sticky; top: 0; z-index: 30;
  display: flex; align-items: center; gap: 20px;
  height: 56px; padding: 0 18px;
  background: var(--panel); border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 9px; cursor: pointer; }
.brand-mark { flex: none; }
.brand-name { font-weight: 700; font-size: 16px; letter-spacing: -0.2px; color: var(--text); }

.mainnav { display: flex; align-items: center; gap: 4px; margin-left: 8px; }
.navlink {
  display: flex; align-items: center; gap: 7px;
  padding: 8px 12px; border-radius: var(--radius-sm);
  color: var(--muted); font-weight: 500; font-size: 14px; text-decoration: none;
  transition: background-color .15s ease, color .15s ease;
}
.navlink:hover { background: var(--panel-hover); color: var(--text); }
.navlink.router-link-active { background: color-mix(in srgb, var(--primary) 12%, transparent); color: var(--primary-strong); }

.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border-radius: var(--radius-sm);
  background: transparent; border: 1px solid var(--border);
  color: var(--text-2); cursor: pointer;
  transition: background-color .15s ease, border-color .15s ease;
}
.icon-btn:hover { background: var(--panel-hover); border-color: var(--border-strong); }
.status {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--destructive); padding: 5px 10px;
  border: 1px solid var(--border); border-radius: 20px;
}
.status .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--destructive); }
.status.up { color: var(--success); }
.status.up .dot { background: var(--success); }

.usermenu { position: relative; }
.userbtn {
  display: flex; align-items: center; gap: 8px;
  background: transparent; border: 1px solid var(--border); border-radius: 22px;
  padding: 4px 10px 4px 4px; font-family: inherit; color: var(--text); font-size: 13px; cursor: pointer;
}
.userbtn:hover { background: var(--panel-hover); }
.avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--primary-strong); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-weight: 600; font-size: 13px;
}
.menu {
  position: absolute; right: 0; top: 42px; width: 190px;
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 6px; z-index: 40;
}
.menu-head { padding: 8px 10px; border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.menu-name { font-weight: 600; font-size: 13px; color: var(--text); }
.menu-role { font-size: 12px; color: var(--muted); }
.menu-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: transparent; border: none; border-radius: var(--radius-sm);
  padding: 9px 10px; font-family: inherit; font-size: 13px; color: var(--text); cursor: pointer;
}
.menu-item:hover { background: var(--panel-hover); }

.content { flex: 1; min-height: 0; overflow: auto; }

@media (max-width: 760px) {
  .topbar { height: auto; min-height: 56px; padding: 8px 12px; gap: 8px; flex-wrap: wrap; }
  .brand { margin-right: auto; }
  .mainnav { order: 3; width: 100%; margin: 0; overflow-x: auto; padding-bottom: 2px; }
  .navlink { flex: none; white-space: nowrap; }
  .topbar-right { margin-left: 0; gap: 6px; }
  .status, .uname { display: none; }
}
</style>
