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
        <RouterLink to="/admin/agents" class="menu-item">
          <span class="mi-icon">🤖</span><span>Agent 管理</span>
        </RouterLink>
        <RouterLink to="/admin/users" class="menu-item">
          <span class="mi-icon">🧑</span><span>用户管理</span>
        </RouterLink>
        <RouterLink to="/admin/kb" class="menu-item">
          <span class="mi-icon">📚</span><span>知识库管理</span>
        </RouterLink>
        <RouterLink to="/admin/tools" class="menu-item">
          <span class="mi-icon">🧰</span><span>工具列表</span>
        </RouterLink>
        <RouterLink to="/admin/mcp" class="menu-item">
          <span class="mi-icon">🔌</span><span>MCP 服务器</span>
        </RouterLink>
        <RouterLink to="/admin/models" class="menu-item">
          <span class="mi-icon">🧠</span><span>模型配置</span>
        </RouterLink>
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
// 左侧菜单布局：菜单项通过 router-link-active 自动高亮（含子路由）
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
.menu { display: flex; flex-direction: column; gap: 4px; }
.menu-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 9px;
  color: var(--text); text-decoration: none; font-size: 14px;
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
