<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>模型配置</h2>
        <p class="hint">
          统一管理<b>大模型 / 嵌入模型 / 重排模型</b>的接入点、密钥与模型名。配置「默认」后，
          对话使用默认大模型、知识库检索使用默认嵌入（与重排）模型；未配置时回退到原环境变量。
        </p>
      </div>
      <button class="primary" @click="startCreate">+ 新增模型</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="tabs">
      <button
        v-for="t in tabs"
        :key="t.value"
        :class="{ active: filter === t.value }"
        @click="setFilter(t.value)"
      >
        {{ t.label }}
        <span class="cnt" v-if="counts[t.value]">{{ counts[t.value] }}</span>
      </button>
    </div>

    <div class="group-card">
      <div v-if="loading" class="muted" style="padding: 18px;">加载中…</div>
      <div v-else-if="!models.length" class="muted" style="padding: 18px;">
        暂无{{ typeLabel(filter) }}配置，点击右上角「新增模型」。
      </div>
      <div
        v-for="m in models"
        :key="m.id"
        class="model-row"
      >
        <div class="m-head">
          <span class="m-name">{{ m.name }}</span>
          <span class="badge" :class="m.type">{{ typeLabel(m.type) }}</span>
          <span v-if="m.is_default" class="star" title="默认">★ 默认</span>
          <span class="spacer"></span>
          <button class="mini" @click="startEdit(m)">编辑</button>
          <button class="mini danger" @click="del(m)">删除</button>
        </div>
        <div class="m-meta mono">
          <span>model: {{ m.model || '—' }}</span>
          <span>base_url: {{ m.base_url || '—' }}</span>
          <span v-if="m.type === 'embedding'">dim: {{ m.dim || '—' }}</span>
          <span v-if="m.api_key">api_key: ••••••••</span>
          <span v-else>api_key: —</span>
        </div>
      </div>
    </div>

    <!-- 新增 / 编辑表单 -->
    <div v-if="editing" class="modal-mask" @click.self="cancel">
      <div class="modal">
        <h3>{{ form.id ? '编辑模型' : '新增模型' }}</h3>

        <label class="fld">
          <span>类型</span>
          <select v-model="form.type" :disabled="!!form.id" @change="onTypeChange">
            <option v-for="t in MODEL_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </label>

        <label class="fld">
          <span>名称</span>
          <input v-model="form.name" placeholder="如 default-llm" />
        </label>

        <label class="fld">
          <span>Base URL</span>
          <input v-model="form.base_url" :placeholder="placeholderBase" />
        </label>

        <label class="fld">
          <span>API Key</span>
          <input v-model="form.api_key" type="password" :placeholder="placeholderKey" />
        </label>

        <label class="fld">
          <span>模型名</span>
          <input v-model="form.model" :placeholder="placeholderModel" />
        </label>

        <label class="fld" v-if="form.type === 'embedding'">
          <span>向量维度 dim</span>
          <input v-model.number="form.dim" type="number" min="0" step="1" placeholder="如 1536" />
        </label>

        <label class="fld check">
          <input type="checkbox" v-model="form.is_default" />
          <span>设为该类型默认（对话/检索将优先使用）</span>
        </label>

        <div v-if="formError" class="err" style="margin-top: 4px;">{{ formError }}</div>

        <div class="modal-actions">
          <button class="ghost" @click="cancel">取消</button>
          <button class="primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, reactive, computed } from 'vue'
import { listModels, createModel, updateModel, deleteModel, MODEL_TYPES } from '../api/models'

const tabs = [{ value: 'all', label: '全部' }, ...MODEL_TYPES]

const models = ref([])
const loading = ref(false)
const error = ref('')
const filter = ref('all')
const counts = reactive({ llm: 0, embedding: 0, rerank: 0 })

const editing = ref(false)
const saving = ref(false)
const formError = ref('')
const blank = () => ({
  id: null, type: 'llm', name: '', base_url: '', api_key: '', model: '', dim: 0, is_default: false,
})
const form = reactive(blank())

function typeLabel(t) {
  return MODEL_TYPES.find((x) => x.value === t)?.label || t
}

const placeholderBase = computed(() =>
  form.type === 'embedding' ? 'https://api.openai.com/v1' : form.type === 'rerank' ? 'https://api.rerank.com/v1' : 'https://api.deepseek.com')
const placeholderKey = computed(() =>
  form.type === 'embedding' ? 'sk-...（OpenAI 兼容 Embedding）' : form.type === 'rerank' ? 'sk-...（重排服务密钥）' : 'sk-...（大模型密钥）')
const placeholderModel = computed(() =>
  form.type === 'embedding' ? 'text-embedding-3-small' : form.type === 'rerank' ? 'rerank-模型名' : 'deepseek-chat')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const all = await listModels()
    counts.llm = all.filter((m) => m.type === 'llm').length
    counts.embedding = all.filter((m) => m.type === 'embedding').length
    counts.rerank = all.filter((m) => m.type === 'rerank').length
    models.value = filter.value === 'all' ? all : all.filter((m) => m.type === filter.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function setFilter(v) {
  filter.value = v
  load()
}

function startCreate() {
  Object.assign(form, blank())
  formError.value = ''
  editing.value = true
}

function startEdit(m) {
  Object.assign(form, {
    id: m.id, type: m.type, name: m.name, base_url: m.base_url, api_key: '',
    model: m.model, dim: m.dim || 0, is_default: m.is_default,
  })
  formError.value = ''
  editing.value = true
}

function onTypeChange() {
  form.dim = 0
}

function cancel() {
  editing.value = false
  formError.value = ''
}

async function save() {
  saving.value = true
  formError.value = ''
  const body = {
    type: form.type, name: form.name, base_url: form.base_url, model: form.model,
    dim: form.dim || 0, is_default: !!form.is_default,
  }
  if (form.api_key) body.api_key = form.api_key
  try {
    if (form.id) await updateModel(form.id, body)
    else await createModel(body)
    editing.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function del(m) {
  if (!confirm(`确认删除模型「${m.name}」？`)) return
  try {
    await deleteModel(m.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<style scoped>
.list-page { padding: 24px 28px; max-width: 1000px; margin: 0 auto; width: 100%; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.hint { color: var(--muted); font-size: 13px; margin: 0; max-width: 680px; }
.hint b { color: var(--text); }
.primary { border: none; background: var(--accent); color: #fff; padding: 9px 16px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600; }
.primary:disabled { opacity: 0.5; cursor: not-allowed; }
.err { background: #fde8e8; color: #d93025; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.muted { color: var(--muted); font-size: 13px; }

.tabs { display: flex; gap: 8px; margin-bottom: 14px; }
.tabs button {
  border: 1px solid var(--border); background: var(--panel); color: var(--muted);
  padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px;
}
.tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.cnt { font-size: 11px; opacity: 0.8; margin-left: 4px; }

.group-card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.model-row { border-bottom: 1px solid var(--border); padding: 14px 16px; }
.model-row:last-child { border-bottom: none; }
.m-head { display: flex; align-items: center; gap: 10px; }
.m-name { font-weight: 600; font-size: 14px; }
.badge { font-size: 11px; padding: 2px 9px; border-radius: 20px; color: #fff; }
.badge.llm { background: #4f6ef7; }
.badge.embedding { background: #22a06b; }
.badge.rerank { background: #b8860b; }
.star { font-size: 12px; color: #f5a623; }
.spacer { flex: 1; }
.mini { border: 1px solid var(--border); background: transparent; color: var(--muted); padding: 4px 12px; border-radius: 7px; cursor: pointer; font-size: 12px; }
.mini.danger { color: #d93025; }
.m-meta { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 12px; color: var(--muted); }

.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px; width: 440px; max-width: 92vw; }
.modal h3 { margin: 0 0 16px; font-size: 16px; }
.fld { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
.fld > span { font-size: 12px; color: var(--muted); }
.fld input, .fld select { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; background: var(--bg); color: var(--text); font-size: 13px; font-family: inherit; }
.fld.check { flex-direction: row; align-items: center; gap: 8px; }
.fld.check > span { font-size: 13px; color: var(--text); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }
.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); padding: 9px 16px; border-radius: 9px; cursor: pointer; font-size: 13px; }
.mono { font-family: var(--mono); }
</style>
