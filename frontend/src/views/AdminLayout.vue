<template>
  <div class="admin-layout">
    <aside class="sidebar">
      <div class="brand">
        <span class="logo">◆</span>
        <div>
          <div class="title">管理后台</div>
          <div class="subtitle">DeepAgent</div>
        </div>
      </div>

      <nav class="menu">
        <div v-for="g in menuGroups" :key="g.key" class="menu-group">
          <button class="group-title" :class="{ open: isOpen(g.key) }" @click="toggle(g.key)">
            <span class="gt-icon">{{ g.icon }}</span>
            <span class="gt-label">{{ g.label }}</span>
            <span class="gt-chev">▾</span>
          </button>
          <div v-show="isOpen(g.key)" class="sub-items">
            <RouterLink v-for="item in g.items" :key="item.to" :to="item.to" class="menu-item">
              <span class="mi-icon">{{ item.icon }}</span>
              <span>{{ item.label }}</span>
            </RouterLink>
          </div>
        </div>
      </nav>

      <div class="side-foot">
        <RouterLink to="/" class="back">← 返回前台对话</RouterLink>
      </div>
    </aside>

    <section class="content">
      <router-view />
    </section>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

// 一级菜单：智能体管理 / 系统管理；二级为具体管理页
const menuGroups = [
  {
    key: 'agent',
    label: '智能体管理',
    icon: '🤖',
    items: [
      { to: '/admin/agents', label: 'Agent 管理', icon: '📋' },
      { to: '/admin/models', label: '模型配置', icon: '🧠' },
      { to: '/admin/kb', label: '知识库管理', icon: '📚' },
      { to: '/admin/tools', label: '工具列表', icon: '🧰' },
      { to: '/admin/mcp', label: 'MCP 服务器', icon: '🔌' },
    ],
  },
  {
    key: 'system',
    label: '系统管理',
    icon: '⚙️',
    items: [
      { to: '/admin/users', label: '用户管理', icon: '🧑' },
      { to: '/admin/roles', label: '角色管理', icon: '🎭' },
      { to: '/admin/departments', label: '部门管理', icon: '🏢' },
    ],
  },
]

// 含当前路由的分组自动展开，其余可手动折叠
const openGroups = ref(new Set())
watch(
  () => route.path,
  (p) => {
    const g = menuGroups.find((x) => x.items.some((i) => p.startsWith(i.to)))
    if (g) {
      const s = new Set(openGroups.value)
      s.add(g.key)
      openGroups.value = s
    }
  },
  { immediate: true },
)
function isOpen(key) {
  return openGroups.value.has(key)
}
function toggle(key) {
  const s = new Set(openGroups.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  openGroups.value = s
}
</script>

<style scoped>
.admin-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  width: 100%;
  max-width: 100%;
}
.sidebar {
  flex: none;
  width: 220px;
  border-right: 1px solid var(--border);
  background: var(--panel);
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
}
.brand { display: flex; align-items: center; gap: 10px; padding: 0 6px 18px; }
.logo {
  width: 34px; height: 34px; border-radius: 9px;
  background: linear-gradient(135deg, #4f6ef7, #8b5cf6);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 17px;
}
.title { font-weight: 700; font-size: 15px; }
.subtitle { font-size: 11px; color: var(--muted); }

.menu { display: flex; flex-direction: column; gap: 2px; }
.menu-group { margin-bottom: 2px; }
.group-title {
  width: 100%;
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border: none; border-radius: 9px;
  background: transparent; color: var(--text);
  font-size: 14px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.group-title:hover { background: var(--panel-hover); }
.gt-icon { font-size: 15px; width: 18px; text-align: center; }
.gt-label { flex: 1; text-align: left; }
.gt-chev { font-size: 11px; color: var(--muted); transition: transform 0.15s; }
.group-title:not(.open) .gt-chev { transform: rotate(-90deg); }

.sub-items { display: flex; flex-direction: column; gap: 2px; padding: 2px 0 4px 8px; }
.menu-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: 9px;
  color: var(--text); text-decoration: none; font-size: 13px;
  cursor: pointer;
}
.menu-item:hover { background: var(--panel-hover); }
.menu-item.router-link-active { background: var(--accent); color: #fff; }
.menu-item.router-link-active .mi-icon { filter: none; }
.mi-icon { font-size: 15px; width: 18px; text-align: center; }

.side-foot { margin-top: auto; padding-top: 16px; border-top: 1px solid var(--border); }
.back {
  display: block; padding: 10px 12px; border-radius: 9px;
  color: var(--muted); text-decoration: none; font-size: 13px; cursor: pointer;
}
.back:hover { background: var(--panel-hover); color: var(--text); }

.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
}
</style>
