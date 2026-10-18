<template>
  <aside class="sidebar">
    <button class="new-btn" @click="$emit('new')" :disabled="busy">＋ 新建会话</button>
    <div class="list">
      <div v-for="g in groups" :key="g.label" class="group">
        <div class="group-title">{{ g.label }}</div>
        <div
          v-for="t in g.items"
          :key="t.thread_id"
          class="item"
          :class="{ active: t.thread_id === currentId }"
          role="button"
          tabindex="0"
          :aria-current="t.thread_id === currentId ? 'true' : undefined"
          @click="$emit('select', t.thread_id)"
          @keydown.enter.prevent="$emit('select', t.thread_id)"
          @keydown.space.prevent="$emit('select', t.thread_id)"
        >
          <span class="item-title">{{ t.title || '新会话' }}</span>
          <span class="item-time" :title="absTime(t.updated_at)">{{ relTime(t.updated_at) }}</span>
          <button class="del" aria-label="删除会话" @click.stop="$emit('remove', t.thread_id)">×</button>
        </div>
      </div>
      <div v-if="!threads.length" class="empty">暂无历史会话</div>
    </div>
    <!-- 左下角用户区（对齐 EvoFlow 需求图）：用户名/角色 + 主题切换 + 退出 -->
    <div class="user-zone" v-if="user">
      <span class="u-avatar" aria-hidden="true">{{ (user.username || '?').slice(0, 1).toUpperCase() }}</span>
      <span class="u-meta">
        <span class="u-name">{{ user.username }}</span>
        <span class="u-role">{{ roleLabel }}</span>
      </span>
      <button class="u-icon" @click="toggleTheme" :aria-label="theme === 'dark' ? '切换亮色主题' : '切换暗色主题'">
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
      </button>
      <button class="u-icon" @click="logout" aria-label="退出登录">
        <Icon name="logout" :size="16" />
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from './Icon.vue'
import { getUser, clearAuth, apiFetch } from '../auth'

const props = defineProps({
  threads: { type: Array, default: () => [] },
  currentId: { type: String, default: '' },
  busy: { type: Boolean, default: false }
})
defineEmits(['new', 'select', 'remove'])

// 会话分组（对齐 EvoFlow 需求图）：今天 / 昨天 / 7 天内 / 更早，组内按最近活动倒序
const groups = computed(() => {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const sorted = [...props.threads].sort((a, b) => {
    const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0
    const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0
    return tb - ta
  })
  const buckets = { today: [], yesterday: [], week: [], earlier: [] }
  for (const t of sorted) {
    const ts = t.updated_at ? new Date(t.updated_at).getTime() : NaN
    if (isNaN(ts) || ts < startOfToday - 7 * 86400e3) buckets.earlier.push(t)
    else if (ts >= startOfToday) buckets.today.push(t)
    else if (ts >= startOfToday - 86400e3) buckets.yesterday.push(t)
    else buckets.week.push(t)
  }
  return [
    { label: '今天', items: buckets.today },
    { label: '昨天', items: buckets.yesterday },
    { label: '7 天内', items: buckets.week },
    { label: '更早', items: buckets.earlier },
  ].filter((g) => g.items.length)
})

// 会话条目相对时间（对齐 EvoFlow 需求图）：刚刚 / Xm / Xh / Xd / 超一周显示日期
function relTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 0) return ''
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function absTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d) ? '' : d.toLocaleString()
}

// ── 用户区：身份 + 主题切换 + 退出（与 App.vue 顶栏同款逻辑，聊天页顶栏已隐藏该区）──
const router = useRouter()
const user = getUser()
const theme = ref('light')
try { theme.value = localStorage.getItem('as-theme') || theme.value } catch (e) {}
theme.value = document.documentElement.getAttribute('data-theme') || theme.value
const roleLabel = computed(() => {
  const r = user?.role
  return r === 'admin' ? '管理员' : r === 'auditor' ? '审计员' : '普通用户'
})

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', theme.value)
  try { localStorage.setItem('as-theme', theme.value) } catch (e) {}
}

async function logout() {
  try { await apiFetch('/api/auth/logout', { method: 'POST' }) } catch (e) { /* 服务端登出失败不影响本地清态 */ }
  clearAuth()
  router.push('/login')
}
</script>

<style scoped>
.sidebar {
  flex: none;
  width: 220px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--panel);
  padding: 12px;
  gap: 10px;
}
.new-btn {
  border: none;
  background: var(--accent);
  color: var(--on-primary);
  padding: 9px 0;
  border-radius: 9px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.new-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.group-title { color: var(--muted); font-size: 11px; padding: 8px 10px 2px; user-select: none; }
.item {
  display: flex; align-items: center; gap: 6px;
  padding: 9px 10px; border-radius: 10px; cursor: pointer;
  font-size: 13px; color: var(--text);
  transition: background-color .15s ease;
}
.item:hover { background: var(--panel-hover); }
.item.active {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  font-weight: 600;
}
.item-title { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item-time { flex: none; color: var(--muted); font-size: 11px; }
.del {
  flex: none; border: none; background: transparent; color: var(--muted);
  font-size: 16px; cursor: pointer; line-height: 1; padding: 2px 6px; border-radius: 5px;
  visibility: hidden;
}
.item:hover .del { visibility: visible; }
.item:focus-within .del { visibility: visible; }
.del:hover { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, transparent); }
.empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px 0; }

/* 左下角用户区 */
.user-zone {
  flex: none; display: flex; align-items: center; gap: 8px;
  border-top: 1px solid var(--border); padding-top: 10px;
}
.u-avatar {
  flex: none; width: 26px; height: 26px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--accent); color: var(--on-primary); font-size: 12px; font-weight: 700;
}
.u-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }
.u-name { font-size: 12px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.u-role { font-size: 10px; color: var(--muted); }
.u-icon {
  flex: none; border: none; background: transparent; color: var(--muted);
  cursor: pointer; padding: 5px; border-radius: 7px; line-height: 1;
  display: inline-flex; align-items: center;
  transition: background-color .15s ease, color .15s ease;
}
.u-icon:hover { background: var(--panel-hover); color: var(--text); }

@media (max-width: 760px) {
  .sidebar { width: 100%; max-height: 180px; border-right: 0; border-bottom: 1px solid var(--border); }
  .list { min-height: 0; }
  .del { visibility: visible; }
}
</style>
