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
      <button class="btn btn-primary" @click="startCreate">+ 新增模型</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="tabs">
      <button
        v-for="t in tabs"
        :key="t.value"
        class="tab"
        :class="{ active: filter === t.value }"
        @click="setFilter(t.value)"
      >
        {{ t.label }}
        <span class="cnt" v-if="counts[t.value]">{{ counts[t.value] }}</span>
      </button>
    </div>

    <div class="group-card">
      <div v-if="loading" class="empty" role="status">加载中…</div>
      <div v-else-if="!models.length" class="empty" role="status">
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
          <button class="mini" :disabled="rowTests[m.id]?.loading" @click="testRow(m)">测试</button>
          <button class="mini" @click="startEdit(m)">编辑</button>
          <button class="mini danger" @click="del(m)">删除</button>
        </div>
        <div class="m-meta mono">
          <span>model: {{ m.model || '—' }}</span>
          <span>base_url: {{ m.base_url || '—' }}</span>
          <span v-if="m.type === 'embedding'">dim: {{ m.dim || '—' }}</span>
          <span v-if="m.type === 'llm' && m.extra && m.extra.temperature !== undefined">temp: {{ m.extra.temperature }}</span>
          <span v-if="m.type === 'rerank' && m.extra && m.extra.top_n !== undefined">top_n: {{ m.extra.top_n }}</span>
          <span v-if="m.api_key">api_key: ••••••••</span>
          <span v-else>api_key: —</span>
        </div>
        <div v-if="rowTests[m.id] && rowTests[m.id].detail" class="m-test" :class="rowTests[m.id].ok ? 'ok' : 'fail'">
          {{ rowTests[m.id].ok ? '✓' : '✗' }} {{ rowTests[m.id].detail }}<span v-if="rowTests[m.id].latency_ms"> · {{ rowTests[m.id].latency_ms }}ms</span>
        </div>
      </div>
    </div>

    <!-- 新增 / 编辑表单 -->
    <div v-if="editing" class="modal-mask" @click.self="cancel">
      <div
        ref="modalEl"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-form-title"
        @keydown.esc="cancel"
      >
        <h3 id="model-form-title">{{ form.id ? '编辑模型' : '新增模型' }}</h3>

        <label class="field">
          <span>类型</span>
          <select v-model="form.type" :disabled="!!form.id" @change="onTypeChange">
            <option v-for="t in MODEL_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </label>

        <label class="field">
          <span>名称 <i class="req">*</i></span>
          <input v-model="form.name" :class="{ invalid: errors.name }" @input="clearErr('name')" placeholder="如 default-llm" />
          <div class="fld-err" v-if="errors.name">{{ errors.name }}</div>
        </label>

        <label class="field">
          <span>Base URL <i class="req">*</i></span>
          <input v-model="form.base_url" :class="{ invalid: errors.base_url }" @input="clearErr('base_url')" :placeholder="placeholderBase" />
          <div class="fld-err" v-if="errors.base_url">{{ errors.base_url }}</div>
        </label>

        <label class="field">
          <span>API Key</span>
          <input v-model="form.api_key" type="password" :placeholder="placeholderKey" />
        </label>

        <label class="field">
          <span>模型名 <i class="req">*</i></span>
          <input v-model="form.model" :class="{ invalid: errors.model }" @input="clearErr('model')" :placeholder="placeholderModel" />
          <div class="fld-err" v-if="errors.model">{{ errors.model }}</div>
        </label>

        <label class="field" v-if="form.type === 'embedding'">
          <span>向量维度 dim <i class="req">*</i></span>
          <input v-model.number="form.dim" type="number" min="0" step="1" :class="{ invalid: errors.dim }" @input="clearErr('dim')" placeholder="如 1536" />
          <div class="fld-err" v-if="errors.dim">{{ errors.dim }}</div>
        </label>

        <label class="field check">
          <input type="checkbox" v-model="form.is_default" />
          <span>设为该类型默认（对话/检索将优先使用）</span>
        </label>

        <div class="fld-sec" v-if="form.type === 'llm'">
          <div class="sec-title">高级参数（大模型）</div>
          <div class="grid2">
            <label class="field"><span>Temperature 温度</span><input v-model="form.extra.temperature" type="number" step="0.1" min="0" max="2" placeholder="0.3" /></label>
            <label class="field"><span>Top P</span><input v-model="form.extra.top_p" type="number" step="0.05" min="0" max="1" placeholder="1.0" /></label>
            <label class="field"><span>Max Tokens 最大输出</span><input v-model="form.extra.max_tokens" type="number" min="1" step="1" placeholder="模型默认" /></label>
            <label class="field"><span>Timeout 超时(秒)</span><input v-model="form.extra.timeout" type="number" min="1" step="1" placeholder="默认" /></label>
            <label class="field"><span>Frequency Penalty 频率惩罚</span><input v-model="form.extra.frequency_penalty" type="number" step="0.1" min="-2" max="2" placeholder="0" /></label>
            <label class="field"><span>Presence Penalty 存在惩罚</span><input v-model="form.extra.presence_penalty" type="number" step="0.1" min="-2" max="2" placeholder="0" /></label>
          </div>
          <label class="field"><span>Stop 停止词（逗号分隔）</span><input v-model="form.extra.stop" placeholder="如：stop1, stop2" /></label>
        </div>

        <div class="fld-sec" v-if="form.type === 'rerank'">
          <div class="sec-title">高级参数（重排）</div>
          <label class="field"><span>Top N 返回条数</span><input v-model="form.extra.top_n" type="number" min="1" step="1" placeholder="如 5" /></label>
        </div>

        <div v-if="formError" class="err" style="margin-top: 4px;">{{ formError }}</div>

        <div v-if="formTest" class="test-result" :class="formTest.ok ? 'ok' : 'fail'">
          {{ formTest.ok ? '✓' : '✗' }} {{ formTest.detail }}<span v-if="formTest.latency_ms"> · {{ formTest.latency_ms }}ms</span>
        </div>

        <div class="modal-actions">
          <button class="btn btn-ghost" @click="cancel">取消</button>
          <button class="btn btn-ghost" :disabled="testing || !form.model" @click="testForm">测试连接</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, reactive, computed, watch } from 'vue'
import { listModels, createModel, updateModel, deleteModel, testModel, testModelById, MODEL_TYPES } from '../api/models'

const tabs = [{ value: 'all', label: '全部' }, ...MODEL_TYPES]

const models = ref([])
const loading = ref(false)
const error = ref('')
const filter = ref('all')
const counts = reactive({ llm: 0, embedding: 0, rerank: 0 })

const editing = ref(false)
const saving = ref(false)
const formError = ref('')
const testing = ref(false)
const formTest = ref(null)
const rowTests = reactive({})
const errors = reactive({})
const modalEl = ref(null)
function clearErr(k) { errors[k] = '' }
const blank = () => ({
  id: null, type: 'llm', name: '', base_url: '', api_key: '', model: '', dim: 0, is_default: false,
  extra: { temperature: '', top_p: '', max_tokens: '', timeout: '', frequency_penalty: '', presence_penalty: '', stop: '', top_n: '' },
})
const form = reactive(blank())

// 弹窗打开时聚焦第一个输入框（键盘可达）
watch(editing, (open) => {
  if (open) nextTick(() => modalEl.value?.querySelector('input, select')?.focus())
})

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
  errors.name = errors.base_url = errors.model = errors.dim = ''
  editing.value = true
}

function startEdit(m) {
  const ex = m.extra || {}
  Object.assign(form, {
    id: m.id, type: m.type, name: m.name, base_url: m.base_url, api_key: '',
    model: m.model, dim: m.dim || 0, is_default: m.is_default,
    extra: {
      temperature: ex.temperature ?? '', top_p: ex.top_p ?? '', max_tokens: ex.max_tokens ?? '',
      timeout: ex.timeout ?? '', frequency_penalty: ex.frequency_penalty ?? '',
      presence_penalty: ex.presence_penalty ?? '', stop: ex.stop ?? '', top_n: ex.top_n ?? '',
    },
  })
  formError.value = ''
  errors.name = errors.base_url = errors.model = errors.dim = ''
  editing.value = true
}

function onTypeChange() {
  form.dim = 0
}

function cancel() {
  editing.value = false
  formError.value = ''
}

function cleanExtra() {
  const out = {}
  const e = form.extra
  for (const k of ['temperature', 'top_p', 'max_tokens', 'timeout', 'frequency_penalty', 'presence_penalty', 'stop', 'top_n']) {
    const v = e[k]
    if (v !== '' && v !== null && v !== undefined) out[k] = v
  }
  return out
}

async function testForm() {
  testing.value = true
  formTest.value = null
  try {
    formTest.value = await testModel({
      type: form.type, base_url: form.base_url, api_key: form.api_key,
      model: form.model, dim: form.dim || 0, extra: cleanExtra(),
    })
  } catch (e) {
    formTest.value = { ok: false, detail: e.message, latency_ms: null }
  } finally {
    testing.value = false
  }
}

async function testRow(m) {
  rowTests[m.id] = { loading: true, ok: null, detail: '' }
  try {
    const r = await testModelById(m.id)
    rowTests[m.id] = { loading: false, ok: r.ok, detail: r.detail, latency_ms: r.latency_ms }
  } catch (e) {
    rowTests[m.id] = { loading: false, ok: false, detail: e.message, latency_ms: null }
  }
}

async function save() {
  saving.value = true
  formError.value = ''
  // 必填校验：名称 / 接口地址 / 模型名 为通用必填；嵌入模型还需维度（错误贴在各输入框下方）
  errors.name = errors.base_url = errors.model = errors.dim = ''
  let bad = false
  if (!form.name.trim()) { errors.name = '请填写模型名称'; bad = true }
  if (!form.base_url.trim()) { errors.base_url = '请填写接口地址(base_url)'; bad = true }
  if (!form.model.trim()) { errors.model = '请填写模型(model)'; bad = true }
  if (form.type === 'embedding' && !(Number(form.dim) > 0)) {
    errors.dim = '嵌入模型请填写维度(dim)，且需大于 0'; bad = true
  }
  if (bad) { saving.value = false; return }
  const body = {
    type: form.type, name: form.name.trim(), base_url: form.base_url.trim(), model: form.model.trim(),
    dim: form.dim || 0, is_default: !!form.is_default,
    extra: cleanExtra(),
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
.muted { color: var(--muted); font-size: 13px; }
.cnt { font-size: 11px; opacity: 0.8; margin-left: 4px; }

.group-card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.model-row { border-bottom: 1px solid var(--border); padding: 14px 16px; }
.model-row:last-child { border-bottom: none; }
.m-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.m-name { font-weight: 600; font-size: 14px; }
.badge.llm { color: var(--primary); border-color: color-mix(in srgb, var(--primary) 40%, transparent); }
.badge.embedding { color: var(--success); border-color: color-mix(in srgb, var(--success) 40%, transparent); }
.badge.rerank { color: var(--warning); border-color: color-mix(in srgb, var(--warning) 40%, transparent); }
.star { font-size: 12px; color: var(--warning); }
.spacer { flex: 1; }
.mini { border: 1px solid var(--border); background: transparent; color: var(--muted); padding: 4px 12px; border-radius: 7px; cursor: pointer; font-size: 12px; }
.mini:hover { background: var(--panel-hover); color: var(--text); }
.mini.danger { color: var(--destructive); }
.m-meta { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 12px; color: var(--muted); }
.m-test { margin-top: 8px; font-size: 12px; padding: 6px 10px; border-radius: var(--radius-sm); display: inline-block; }
.m-test.ok { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }
.m-test.fail { background: color-mix(in srgb, var(--destructive) 10%, transparent); color: var(--destructive); }
.test-result { margin-top: 6px; padding: 8px 12px; border-radius: var(--radius-sm); font-size: 13px; }
.test-result.ok { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }
.test-result.fail { background: color-mix(in srgb, var(--destructive) 10%, transparent); color: var(--destructive); }

.req { color: var(--destructive); font-style: normal; margin-left: 2px; }
.fld-err { font-size: 12px; color: var(--destructive); margin-top: 4px; }
.field input.invalid, .field select.invalid { border-color: var(--destructive); }
.fld-sec { border-top: 1px dashed var(--border); margin-top: 4px; padding-top: 12px; }
.sec-title { font-size: 12px; color: var(--muted); margin-bottom: 10px; font-weight: 600; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
.grid2 .field { margin-bottom: 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }
.mono { font-family: var(--mono); }
</style>
