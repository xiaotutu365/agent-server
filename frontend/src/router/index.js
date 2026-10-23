import { createRouter, createWebHashHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import AdminLayout from '../views/AdminLayout.vue'
import AgentListView from '../views/AgentListView.vue'
import AgentEditView from '../views/AgentEditView.vue'
import UserListView from '../views/UserListView.vue'
import RoleManagementView from '../views/RoleManagementView.vue'
import DepartmentManagementView from '../views/DepartmentManagementView.vue'
import KnowledgeBase from '../components/KnowledgeBase.vue'
import KbEvalView from '../views/KbEvalView.vue'
import LoginView from '../views/LoginView.vue'
import LangGraphLabView from '../views/LangGraphLabView.vue'
import EDAView from '../views/EDAView.vue'
import ToolsView from '../views/ToolsView.vue'
import McpServersView from '../views/McpServersView.vue'
import ModelConfigView from '../views/ModelConfigView.vue'
import MemoryView from '../views/MemoryView.vue'
import FlowView from '../views/FlowView.vue'
import FlowRunView from '../views/FlowRunView.vue'
import { isAuthed, tokenRole } from '../auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    // 前台：用户对话页
    { path: '/', name: 'chat', component: ChatView },
    // 前台：LangGraph HITL 实验台（独立测试页，复用 deep_agent 的 INTERRUPT_TOOLS；仅 admin）
    { path: '/langgraph-lab', name: 'langgraph-lab', component: LangGraphLabView },
    // 前台：EDA 数字芯片逻辑综合多 Agent 流水线（脚本/调度/报告三阶段 + WNS 闭环；仅 admin）
    { path: '/eda', name: 'eda', component: EDAView },
    // 前台：流程运行（发起/进度/人审；仅 admin，非 admin 审批入口已按需求收敛）
    { path: '/flows', name: 'flow-runs', component: FlowRunView },
    // 后台：左侧菜单管理系统
    {
      path: '/admin',
      component: AdminLayout,
      redirect: '/admin/agents',
      children: [
        { path: 'agents', name: 'agent-list', component: AgentListView },
        { path: 'agents/new', name: 'agent-new', component: AgentEditView },
        { path: 'agents/:id', name: 'agent-edit', component: AgentEditView },
        { path: 'users', name: 'user-list', component: UserListView },
        { path: 'roles', name: 'role-list', component: RoleManagementView },
        { path: 'departments', name: 'dept-list', component: DepartmentManagementView },
        { path: 'kb', name: 'kb-admin', component: KnowledgeBase },
        { path: 'eval', name: 'kb-eval', component: KbEvalView },
        { path: 'tools', name: 'tool-list', component: ToolsView },
        { path: 'mcp', name: 'mcp-servers', component: McpServersView },
        { path: 'models', name: 'model-list', component: ModelConfigView },
        { path: 'memory', name: 'memory-admin', component: MemoryView },
        { path: 'flows', name: 'flow-admin', component: FlowView },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.path === '/login') {
    // 已登录则跳首页
    if (isAuthed() && tokenRole()) return { path: '/' }
    return true
  }
  // 其余路由均需登录
  if (!isAuthed() || !tokenRole()) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // 后台仅管理员
  if (to.path.startsWith('/admin') && tokenRole() !== 'admin') {
    return { path: '/' }
  }
  // 非 admin（普通用户/审计员）只保留对话页
  const ADMIN_ONLY_FRONT = ['/langgraph-lab', '/eda', '/flows']
  if (ADMIN_ONLY_FRONT.includes(to.path) && tokenRole() !== 'admin') {
    return { path: '/' }
  }
  return true
})

export default router
