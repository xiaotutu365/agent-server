<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>流程管理</h2>
        <p class="hint">
          用 JSON DSL 配置确定性多步流程（<b>llm / tool / human</b> 节点 + 条件边），
          human 节点暂停等待人审，批准/拒绝驱动后续走向。配置完成后在
          <router-link to="/flows" class="inline-link">流程运行</router-link> 页发起。
        </p>
      </div>
      <button class="btn btn-primary" @click="openCreate">新建流程</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="card tbl-card">
      <table class="tbl">
        <thead>
          <tr>
            <th>名称</th>
            <th>版本</th>
            <th>节点</th>
            <th>更新时间</th>
            <th class="op">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="5" class="muted">加载中…</td></tr>
          <tr v-else-if="!flows.length"><td colspan="5" class="muted">暂无流程，点击右上角新建</td></tr>
          <tr v-for="f in flows" :key="f.flow_id">
            <td class="name">{{ f.name }}</td>
            <td>v{{ f.version }}</td>
            <td class="muted">{{ (f.definition.nodes || []).length }} 个</td>
            <td class="muted">{{ fmtTime(f.updated_at) }}</td>
            <td class="op">
              <button class="btn btn-ghost btn-sm" @click="openEdit(f)">编辑</button>
              <button class="btn btn-ghost btn-sm" @click="goRun(f)">发起运行</button>
              <button class="btn btn-danger btn-sm" @click="remove(f)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新建/编辑弹窗 -->
    <div v-if="dialog" class="modal-mask" @click.self="dialog = null">
      <div class="modal modal-wide">
        <h3>{{ dialog.flow_id ? '编辑流程' : '新建流程' }}</h3>
        <label class="field">
          <span>名称</span>
          <input v-model="dialog.name" class="input" placeholder="如：文案生成审批流" />
        </label>
        <label class="field">
          <span>definition（JSON DSL：entry / nodes / edges / limits）</span>
          <textarea v-model="dialog.defText" class="textarea def-textarea" spellcheck="false"></textarea>
        </label>
        <div v-if="dialog.msg" class="err">{{ dialog.msg }}</div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="dialog = null">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listFlows, createFlow, updateFlow, deleteFlow } from '../api/flows'

const router = useRouter()
const flows = ref([])
const loading = ref(true)
const error = ref('')
const dialog = ref(null)   // { flow_id?, name, defText, msg? }
const saving = ref(false)

const TEMPLATE = JSON.stringify({
  entry: 'draft',
  nodes: [
    { id: 'draft', type: 'llm', output_key: 'draft',
      agent: { system_prompt: '你是写作助手，按用户输入中的主题产出高质量文案，只输出文案正文' } },
    { id: 'review', type: 'human', output_key: 'decision',
      prompt: '请审阅当前草稿：批准则发布，拒绝则退回修订（请在意见中写明修改要求）' },
    { id: 'revise', type: 'llm', output_key: 'draft',
      agent: { system_prompt: '你是修订助手，按审批意见修订文案，只输出修订后的全文' },
      input: '原文：${draft}\n审批意见：${decision}\n请按意见修订。' },
    { id: 'publish', type: 'llm', output_key: 'final',
      agent: { system_prompt: '你是定稿助手，对文案做最终润色并输出定稿全文' },
      input: '已批准文案：${draft}\n请输出定稿。' }
  ],
  edges: [
    { from: 'draft', to: 'review' },
    { from: 'review', to: 'publish', when: 'approved' },
    { from: 'review', to: 'revise', when: 'rejected' },
    { from: 'revise', to: 'review' }
  ],
  limits: { max_revisions: 2 }
}, null, 2)

async function load() {
  loading.value = true
  error.value = ''
  try {
    flows.value = await listFlows()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openCreate() {
  dialog.value = { name: '', defText: TEMPLATE, msg: '' }
}

function openEdit(f) {
  dialog.value = {
    flow_id: f.flow_id,
    name: f.name,
    defText: JSON.stringify(f.definition, null, 2),
    msg: ''
  }
}

async function save() {
  const d = dialog.value
  if (!d || saving.value) return
  d.msg = ''
  if (!d.name.trim()) { d.msg = '名称不能为空'; return }
  let definition
  try {
    definition = JSON.parse(d.defText)
  } catch (e) {
    d.msg = `JSON 不合法：${e.message}`
    return
  }
  saving.value = true
  try {
    if (d.flow_id) await updateFlow(d.flow_id, { name: d.name.trim(), definition })
    else await createFlow(d.name.trim(), definition)
    dialog.value = null
    await load()
  } catch (e) {
    d.msg = e.message || String(e)   // 后端 DSL 校验 400 detail 就地展示
  } finally {
    saving.value = false
  }
}

async function remove(f) {
  if (!confirm(`确认删除流程「${f.name}」？其历史运行实例仍会保留。`)) return
  error.value = ''
  try {
    await deleteFlow(f.flow_id)
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  }
}

function goRun(f) {
  router.push({ path: '/flows', query: { flow_id: f.flow_id } })
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
</script>

<style scoped>
.modal-wide { width: 720px; }
.def-textarea {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 12.5px;
  min-height: 360px;
  white-space: pre;
  tab-size: 2;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.op .btn { margin-right: 6px; }
.inline-link { color: var(--primary-strong); }
</style>
