<template>
  <div class="layout">
    <aside class="sidebar">
      <nav class="menu" aria-label="功能导航">
        <div v-for="g in groups" :key="g.title" class="group">
          <button class="group-head" @click="toggle(g.title)" :aria-expanded="openMap[g.title]">
            <Icon :name="g.icon" :size="18" />
            <span class="group-title">{{ g.title }}</span>
            <Icon :name="openMap[g.title] ? 'chevronDown' : 'chevronRight'" :size="14" class="caret" />
          </button>
          <div class="group-items" v-show="openMap[g.title]">
            <router-link
              v-for="c in g.children"
              :key="c.to"
              :to="c.to"
              class="navlink"
            >{{ c.label }}</router-link>
          </div>
        </div>
      </nav>
    </aside>

    <section class="main">
      <router-view />
    </section>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import Icon from '../components/Icon.vue'

const groups = [
  { title: '对话', icon: 'bot', children: [{ to: '/', label: '智能体对话' }] },
  { title: '知识库', icon: 'book', children: [{ to: '/admin/kb', label: '知识库管理' }] },
  { title: '工具', icon: 'toolbox', children: [{ to: '/admin/tools', label: '工具列表' }] },
  { title: '模型', icon: 'brain', children: [{ to: '/admin/models', label: '模型配置' }] },
  { title: 'MCP', icon: 'plug', children: [{ to: '/admin/mcp', label: 'MCP 服务器' }] },
  { title: '系统', icon: 'settings', children: [
      { to: '/admin/agents', label: '智能体管理' },
      { to: '/admin/roles', label: '角色管理' },
      { to: '/admin/departments', label: '部门管理' },
      { to: '/admin/users', label: '用户管理' },
    ] },
]

const openMap = reactive({})
groups.forEach(g => { openMap[g.title] = true })

function toggle(t) { openMap[t] = !openMap[t] }
</script>

<style scoped>
.layout { display: flex; height: 100%; }
.sidebar {
  width: 232px; flex: none;
  background: var(--panel); border-right: 1px solid var(--border);
  overflow-y: auto; padding: 14px 10px;
}
.menu { display: flex; flex-direction: column; gap: 2px; }
.group { margin-bottom: 4px; }
.group-head {
  display: flex; align-items: center; gap: 10px; width: 100%;
  background: transparent; border: none; border-radius: var(--radius-sm);
  padding: 9px 10px; font-family: inherit; color: var(--text-2);
  font-size: 13px; font-weight: 600;
}
.group-head:hover { background: var(--panel-hover); }
.group-head .group-title { flex: 1; text-align: left; }
.caret { color: var(--muted); }
.group-items { display: flex; flex-direction: column; gap: 1px; padding: 2px 0 6px 14px; }
.navlink {
  display: block; padding: 8px 12px; border-radius: var(--radius-sm);
  color: var(--muted); text-decoration: none; font-size: 13px;
  border-left: 2px solid transparent; transition: background-color .15s ease, color .15s ease;
}
.navlink:hover { background: var(--panel-hover); color: var(--text); }
.navlink.router-link-active {
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--primary-strong); border-left-color: var(--primary-strong); font-weight: 600;
}

.main { flex: 1; min-width: 0; padding: 16px; }

@media (max-width: 760px) {
  .layout { flex-direction: column; min-height: 0; }
  .sidebar { width: 100%; max-height: 176px; border-right: 0; border-bottom: 1px solid var(--border); padding: 8px; }
  .menu { gap: 0; }
  .group { margin: 0; }
  .group-head { min-height: 40px; }
  .group-items { padding: 0 0 4px 14px; }
  .main { padding: 12px; overflow: auto; }
}
</style>
