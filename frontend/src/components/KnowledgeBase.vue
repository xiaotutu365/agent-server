<template>
  <!-- 列表态：与其他后台页一致 -->
  <div v-if="!current && !showSettings" class="list-page">
    <div class="page-head">
      <div>
        <h2>知识库管理</h2>
        <p class="hint">管理知识库：创建后可上传文档并检索。打开某个知识库进入检索与上传工作区。</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="openSettings">配置</button>
        <button class="btn btn-primary" @click="openCreate">+ 新建知识库</button>
      </div>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="card tbl-card">
      <table class="tbl">
        <thead>
          <tr><th>知识库 ID</th><th>片段数</th><th class="op">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="k in kbs" :key="k.kb_id">
            <td class="name">{{ k.kb_id }}</td>
            <td class="muted">{{ k.points_count || 0 }}</td>
            <td class="op">
              <button class="link" @click="select(k.kb_id)">打开</button>
              <button class="link link-danger" @click="doDelete(k.kb_id)">删除</button>
            </td>
          </tr>
          <tr v-if="loadingKbs"><td colspan="3" class="empty" role="status">加载中…</td></tr>
          <tr v-else-if="!kbs.length">
            <td colspan="3" class="empty" role="status">暂无知识库，点击右上角「新建知识库」。</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新建模态窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kb-create-title"
        @keydown.esc="showCreate = false"
      >
        <h3 id="kb-create-title">新建知识库</h3>
        <label class="field">
          <span>知识库 ID</span>
          <input ref="createInput" v-model="newId" placeholder="如 policy" @keydown.enter="doCreate" />
        </label>
        <p class="hint">ID 创建后不可修改，建议使用小写字母/数字/连字符。</p>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" :disabled="!newId.trim() || creating" @click="doCreate">
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- 配置页 -->
  <div v-else-if="showSettings" class="list-page">
    <div class="page-head">
      <div>
        <h2>知识库配置</h2>
        <p class="hint">文档类型、分块、嵌入模型与检索参数。</p>
      </div>
      <button class="btn btn-ghost" @click="showSettings = false">← 返回列表</button>
    </div>

    <div v-if="settingsError" class="err">{{ settingsError }}</div>
    <div v-if="settingsMsg" class="ok">{{ settingsMsg }}</div>

    <div class="cfg">
      <section class="cfg-sec">
        <h4>文档与分块</h4>
        <div class="field-row">
          <label class="lbl">支持的文件类型</label>
          <div class="ext-grid">
            <label v-for="ext in ALL_DOC_TYPES" :key="ext" class="ext">
              <input type="checkbox" :checked="settingsForm.supported_ext.includes(ext)" @change="toggleExt(ext)" />
              <span>{{ ext }}</span>
            </label>
          </div>
        </div>
        <div class="field-row">
          <label class="lbl">分片策略</label>
          <select v-model="settingsForm.chunk_strategy">
            <option v-for="o in strategyOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
        <p v-if="strategyDesc" class="cfg-hint">{{ strategyDesc }}。仅对之后上传的文档生效，已有文档需删除重传。</p>
        <div class="field-row">
          <label class="lbl">分块大小 (字符)</label>
          <input type="number" min="50" step="50" v-model.number="settingsForm.chunk_size" />
        </div>
        <div class="field-row">
          <label class="lbl">分块重叠 (字符)</label>
          <input type="number" min="0" step="10" v-model.number="settingsForm.chunk_overlap" />
        </div>
        <div class="field-row">
          <label class="lbl">单文件大小上限 (MB)</label>
          <input type="number" min="1" step="1" v-model.number="settingsForm.max_file_mb" />
        </div>
      </section>

      <section class="cfg-sec">
        <h4>嵌入模型（dense）</h4>
        <div class="field-row">
          <label class="lbl">嵌入服务 Base URL</label>
          <input v-model="settingsForm.embedding_base_url" placeholder="https://api.openai.com/v1" />
        </div>
        <div class="field-row">
          <label class="lbl">嵌入模型名</label>
          <input v-model="settingsForm.embedding_model" placeholder="text-embedding-3-small" />
        </div>
        <div class="field-row">
          <label class="lbl">API Key</label>
          <input type="password" v-model="settingsForm.embedding_api_key" placeholder="sk-..." />
        </div>
        <div class="field-row">
          <label class="lbl">向量维度</label>
          <input type="number" min="1" step="1" v-model.number="settingsForm.embedding_dim" />
        </div>
        <div class="field-row">
          <label class="lbl">稀疏向量模型</label>
          <input v-model="settingsForm.sparse_model" placeholder="Qdrant/bm25" />
        </div>
        <p class="cfg-hint">修改嵌入模型或维度后，仅对新创建的知识库生效；已有集合需用原模型检索或删除重建。</p>
      </section>

      <section class="cfg-sec">
        <h4>检索</h4>
        <div class="field-row">
          <label class="lbl">默认返回条数 (top_k)</label>
          <input type="number" min="1" step="1" v-model.number="settingsForm.top_k" />
        </div>
        <div class="field-row">
          <label class="lbl">候选集大小 (candidate)</label>
          <input type="number" min="1" step="1" v-model.number="settingsForm.candidate" />
        </div>
        <div class="field-row">
          <label class="lbl">RRF 融合系数 (k)</label>
          <input type="number" min="1" step="1" v-model.number="settingsForm.rrf_k" />
        </div>
      </section>

      <div class="cfg-actions">
        <button class="btn btn-primary" :disabled="settingsSaving" @click="saveSettings">
          {{ settingsSaving ? '保存中…' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>

  <!-- 工作区：打开某个知识库（满高） -->
  <div v-else-if="current" class="kb-workspace">
    <header class="main-head">
      <div class="head-left">
        <button class="btn btn-ghost btn-sm" @click="select('')">← 返回列表</button>
        <h2>{{ current }}</h2>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost btn-sm" @click="openEval">评测</button>
        <button class="btn btn-primary btn-sm" type="button" :disabled="uploading" @click="fileInput?.click()">
          {{ uploading ? '上传中…' : '上传文档' }}
          <input ref="fileInput" type="file" accept=".txt,.md,.pdf,.docx,.csv,.jsonl" @change="doUpload" hidden />
        </button>
      </div>
    </header>

    <section class="doc-panel" aria-label="已入库文档">
      <h3 class="doc-title">已入库文档（{{ docs.length }}）</h3>
      <table v-if="docs.length" class="tbl">
        <thead>
          <tr><th>文件</th><th>片段</th><th>字符数</th><th class="op">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in docs" :key="d.file">
            <td class="name">{{ d.file }}</td>
            <td class="muted">{{ d.chunks }}</td>
            <td class="muted">{{ d.size_chars }}</td>
            <td class="op">
              <button class="link link-danger" :disabled="deletingDoc === d.file" @click="doDeleteDoc(d.file)">
                {{ deletingDoc === d.file ? '删除中…' : '删除' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="loadingDocs" class="empty" role="status">加载中…</p>
      <p v-else class="empty" role="status">暂无文档，点击右上角「上传文档」。</p>
    </section>

    <form class="search" @submit.prevent="doSearch">
      <input v-model="query" aria-label="检索知识库" placeholder="在此知识库中检索…" />
      <button type="submit" class="btn btn-primary" :disabled="!query.trim() || searching">
        {{ searching ? '检索中…' : '检索' }}
      </button>
    </form>

    <div v-if="error" class="err">{{ error }}</div>
    <div v-if="msg" class="ok">{{ msg }}</div>

    <div class="results">
      <article v-for="(r, i) in results" :key="i" class="result">
        <div class="meta">
          <span class="src">{{ r.metadata.source || '未知来源' }}</span>
          <span class="idx">#{{(r.metadata.chunk_idx ?? 0) + 1}}</span>
          <span v-if="typeof r.metadata.score === 'number'" class="score">RRF {{ r.metadata.score.toFixed(3) }}</span>
        </div>
        <p class="content">{{ r.content }}</p>
      </article>
      <p v-if="searching" class="hint" role="status">检索中…</p>
      <p v-else-if="searched && !results.length" class="hint" role="status">未找到相关内容。</p>
    </div>

    <!-- 评测模态窗 -->
    <div v-if="showEval" class="modal-mask" @click.self="showEval = false">
      <div
        class="modal modal-lg"
        role="dialog"
        aria-label="检索评测"
        @keydown.esc="showEval = false"
      >
        <h3>检索评测：{{ current }}</h3>
        <div class="modal-body">
          <div class="field-row">
            <label class="lbl">评测集（JSON：query + expected_files，可选 reference）</label>
            <textarea
              ref="evalInput"
              v-model="evalText"
              class="eval-editor"
              rows="10"
              spellcheck="false"
              placeholder='[{"query": "…", "expected_files": ["a.md"], "reference": "期望片段原文（可选）"}]'
            ></textarea>
            <p class="cfg-hint">
              expected_files 驱动 Recall@k / MRR；reference 用于 Ragas context 指标（需配置默认 chat 模型作 judge）。
              <button class="link" @click="doSaveEvalSet">保存评测集</button>
            </p>
          </div>
          <div class="eval-run-row">
            <label class="lbl">top_k</label>
            <input v-model.number="evalTopK" type="number" min="1" step="1" />
            <button class="btn btn-primary" :disabled="evalRunning || !evalItems.length" @click="doRunEval">
              {{ evalRunning ? '评测中…' : '运行评测' }}
            </button>
          </div>
          <div v-if="evalError" class="err">{{ evalError }}</div>

          <template v-if="evalResult">
            <div class="eval-summary">
              <div class="metric"><span class="m-val">{{ pct(evalResult.summary.recall_at_k) }}</span><span class="m-lbl">Recall@k</span></div>
              <div class="metric"><span class="m-val">{{ evalResult.summary.mrr.toFixed(3) }}</span><span class="m-lbl">MRR</span></div>
              <div v-if="evalResult.summary.ragas_available" class="metric">
                <span class="m-val">{{ pct(evalResult.summary.context_precision) }}</span><span class="m-lbl">Ragas Precision</span>
              </div>
              <div v-if="evalResult.summary.ragas_available" class="metric">
                <span class="m-val">{{ pct(evalResult.summary.context_recall) }}</span><span class="m-lbl">Ragas Recall</span>
              </div>
            </div>
            <p v-if="evalResult.summary.ragas_error" class="cfg-hint">Ragas 指标未计算：{{ evalResult.summary.ragas_error }}</p>

            <section v-for="(it, i) in evalResult.items" :key="i" class="eval-item">
              <header class="eval-item-head">
                <strong>{{ it.query }}</strong>
                <span class="badge" :class="it.recall_at_k >= 1 ? 'ok' : 'warn'">
                  Recall {{ pct(it.recall_at_k) }} · RR {{ it.reciprocal_rank.toFixed(2) }}
                </span>
              </header>
              <article v-for="(h, j) in it.hits" :key="j" class="result">
                <div class="meta">
                  <span class="src">{{ h.source || '未知来源' }}</span>
                  <span class="idx">rank {{ j + 1 }} · #{{ (h.chunk_idx ?? 0) + 1 }}</span>
                  <span v-if="typeof h.score === 'number'" class="score">RRF {{ h.score.toFixed(3) }}</span>
                  <span class="badge" :class="h.hit ? 'ok' : 'bad'">{{ h.hit ? '命中' : '未命中' }}</span>
                </div>
                <p class="content">{{ h.text }}</p>
              </article>
              <p v-if="!it.hits.length" class="empty" role="status">无召回结果。</p>
            </section>
          </template>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showEval = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, reactive, computed, watch } from 'vue'
import { listKbs, createKb, deleteKb, uploadDoc, searchKb, getKbSettings, saveKbSettings, listDocuments, deleteDocument, getEvalSet, saveEvalSet, runEval } from '../api/kb'

const kbs = ref([])
const current = ref('')
const newId = ref('')
const query = ref('')
const results = ref([])
const searched = ref(false)
const uploading = ref(false)
const searching = ref(false)
const loadingKbs = ref(false)
const error = ref('')
const msg = ref('')
const fileInput = ref(null)

// 已入库文档
const docs = ref([])
const loadingDocs = ref(false)
const deletingDoc = ref('')

// 新建模态窗
const showCreate = ref(false)
const creating = ref(false)
const createInput = ref(null)

// 弹窗打开时聚焦输入框（键盘可达）
watch(showCreate, (open) => {
  if (open) {
    newId.value = ''
    nextTick(() => createInput.value?.focus())
  }
})

async function load() {
  loadingKbs.value = true
  error.value = ''
  try {
    kbs.value = await listKbs()
    if (current.value && !kbs.value.find((k) => k.kb_id === current.value)) {
      current.value = ''
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loadingKbs.value = false
  }
}

function select(id) {
  current.value = id
  results.value = []
  searched.value = false
  error.value = ''
  msg.value = ''
  if (id) loadDocs(id)
  else docs.value = []
}

async function loadDocs(id) {
  if (!id) { docs.value = []; return }
  loadingDocs.value = true
  try {
    docs.value = (await listDocuments(id)).documents || []
  } catch (e) {
    error.value = e.message
  } finally {
    loadingDocs.value = false
  }
}

async function doDeleteDoc(file) {
  if (!confirm(`确认删除文档 "${file}"？该操作不可恢复。`)) return
  deletingDoc.value = file
  error.value = ''
  try {
    await deleteDocument(current.value, file)
    await Promise.all([loadDocs(current.value), load()])
  } catch (e) {
    error.value = e.message
  } finally {
    deletingDoc.value = ''
  }
}

function openCreate() {
  showCreate.value = true
}

async function doCreate() {
  const id = newId.value.trim()
  if (!id || creating.value) return
  creating.value = true
  error.value = ''
  try {
    await createKb(id)
    showCreate.value = false
    newId.value = ''
    await load()
    select(id) // 创建后直接进入该库工作区
  } catch (e) {
    error.value = e.message
    showCreate.value = false
  } finally {
    creating.value = false
  }
}

async function doDelete(id) {
  if (!confirm(`确认删除知识库 "${id}"？该操作不可恢复。`)) return
  error.value = ''
  try {
    await deleteKb(id)
    if (current.value === id) current.value = ''
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function doUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading.value = true
  error.value = ''
  msg.value = ''
  try {
    const r = await uploadDoc(current.value, file)
    msg.value = `已入库：${r.file}（${r.chunks} 个片段）`
    await Promise.all([loadDocs(current.value), load()])
  } catch (err) {
    error.value = err.message
  } finally {
    uploading.value = false
    e.target.value = ''
  }
}

async function doSearch() {
  const q = query.value.trim()
  if (!q) return
  searching.value = true
  error.value = ''
  try {
    const r = await searchKb(current.value, q, 5)
    results.value = r.results || []
    searched.value = true
  } catch (err) {
    error.value = err.message
    results.value = []
    searched.value = true
  } finally {
    searching.value = false
  }
}

// 知识库配置
const ALL_DOC_TYPES = ['.txt', '.md', '.pdf', '.docx', '.csv', '.jsonl', '.html', '.json', '.pptx', '.xlsx']
const showSettings = ref(false)
const settingsError = ref('')
const settingsMsg = ref('')
const settingsSaving = ref(false)
const settingsForm = reactive({
  supported_ext: ['.txt', '.md', '.pdf', '.docx', '.csv', '.jsonl'],
  chunk_size: 800,
  chunk_overlap: 100,
  chunk_strategy: 'fixed',
  max_file_mb: 10,
  embedding_base_url: '',
  embedding_model: '',
  embedding_api_key: '',
  embedding_dim: 1536,
  sparse_model: '',
  top_k: 5,
  candidate: 20,
  rrf_k: 60,
})

// 分片策略选项：优先用后端返回的枚举，失败时用本地兜底
const FALLBACK_STRATEGIES = [
  { value: 'fixed', label: '固定长度+重叠', desc: '通用切分，按字数窗口滑动（默认）' },
  { value: 'markdown', label: '按段落/标题', desc: '按 Markdown 标题层级切，保语义完整' },
  { value: 'blank_line', label: '按空行分段', desc: '空行分条不合并，适合 FAQ/问答对' },
]
const strategyOptions = ref(FALLBACK_STRATEGIES)
const loadedStrategy = ref('fixed')
const strategyDesc = computed(
  () => strategyOptions.value.find((o) => o.value === settingsForm.chunk_strategy)?.desc || ''
)

async function openSettings() {
  showSettings.value = true
  error.value = ''
  settingsError.value = ''
  settingsMsg.value = ''
  try {
    const s = await getKbSettings()
    for (const k of Object.keys(settingsForm)) {
      if (s[k] !== undefined) settingsForm[k] = s[k]
    }
    if (Array.isArray(s.chunk_strategies) && s.chunk_strategies.length) {
      strategyOptions.value = s.chunk_strategies
    }
    loadedStrategy.value = s.chunk_strategy || 'fixed'
  } catch (e) {
    settingsError.value = e.message
  }
}

function toggleExt(ext) {
  const arr = settingsForm.supported_ext
  const i = arr.indexOf(ext)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(ext)
}

async function saveSettings() {
  settingsSaving.value = true
  settingsError.value = ''
  settingsMsg.value = ''
  const patch = {}
  for (const k of Object.keys(settingsForm)) patch[k] = settingsForm[k]
  try {
    await saveKbSettings(patch)
    settingsMsg.value = settingsForm.chunk_strategy !== loadedStrategy.value
      ? '配置已保存 ✓（分片策略仅对之后上传的文档生效，已有文档需删除重传）'
      : '配置已保存 ✓'
  } catch (e) {
    settingsError.value = e.message
  } finally {
    settingsSaving.value = false
  }
}

// ---------- 检索评测模态窗（spec 能力 L6） ----------
const showEval = ref(false)
const evalText = ref('')
const evalTemplate = ref(false)
const evalTopK = ref(5)
const evalRunning = ref(false)
const evalResult = ref(null)
const evalError = ref('')
const evalInput = ref(null)

// textarea 内容即评测集视图：运行前自动保存，保证「看到的」就是「运行的」
const evalItems = computed(() => {
  try {
    const v = JSON.parse(evalText.value)
    return Array.isArray(v) ? v.filter((x) => x && x.query) : []
  } catch {
    return []
  }
})

function pct(v) {
  return `${(Number(v ?? 0) * 100).toFixed(1)}%`
}

watch(showEval, (open) => {
  if (open) {
    evalResult.value = null
    evalError.value = ''
    evalText.value = ''
    evalTemplate.value = false
    nextTick(() => evalInput.value?.focus())
    getEvalSet(current.value)
      .then((d) => {
        evalText.value = JSON.stringify(d.items, null, 2)
        evalTemplate.value = !!d.template
      })
      .catch((e) => { evalError.value = e.message })
  }
})

async function doSaveEvalSet() {
  evalError.value = ''
  let items
  try {
    items = JSON.parse(evalText.value)
  } catch {
    evalError.value = '评测集不是合法 JSON，请修正后再保存。'
    return
  }
  try {
    const saved = await saveEvalSet(current.value, items)
    evalText.value = JSON.stringify(saved, null, 2)
    evalTemplate.value = false
  } catch (e) {
    evalError.value = e.message
  }
}

async function doRunEval() {
  if (evalRunning.value) return
  evalError.value = ''
  evalResult.value = null
  evalRunning.value = true
  try {
    const saved = await saveEvalSet(current.value, JSON.parse(evalText.value))
    evalText.value = JSON.stringify(saved, null, 2)
    evalResult.value = await runEval(current.value, evalTopK.value || null)
  } catch (e) {
    evalError.value = e instanceof SyntaxError ? '评测集不是合法 JSON，请修正后再运行。' : e.message
  } finally {
    evalRunning.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.head-actions { display: flex; gap: 10px; align-items: center; }
.op { display: flex; align-items: center; gap: 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }

/* 评测模态窗 */
.modal-lg { width: min(760px, 94vw); max-height: 88vh; overflow: auto; }
.modal-body { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
.eval-editor {
  width: 100%; font-family: var(--mono); font-size: 12px; line-height: 1.6;
  padding: 10px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--panel); color: var(--text); resize: vertical;
}
.eval-run-row { display: flex; align-items: center; gap: 10px; margin: 10px 0 4px; }
.eval-run-row .lbl { flex: none; font-size: 13px; color: var(--muted); }
.eval-run-row input { width: 90px; }
.eval-summary { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 4px; }
.eval-summary .metric {
  flex: 1; min-width: 120px; display: flex; flex-direction: column; gap: 2px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--panel);
}
.eval-summary .m-val { font-size: 20px; font-weight: 700; font-family: var(--mono); }
.eval-summary .m-lbl { font-size: 12px; color: var(--muted); }
.eval-item { margin-top: 16px; }
.eval-item-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.badge.ok { color: var(--success, #16a34a); border-color: var(--success, #16a34a); }
.badge.warn { color: var(--warning, #d97706); border-color: var(--warning, #d97706); }
.badge.bad { color: var(--destructive); border-color: var(--destructive); }

/* 工作区（满高） */
.kb-workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  overflow-y: auto;
  min-width: 0;
  min-height: 0;
  width: 100%;
}
.main-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.head-left h2 { margin: 0; font-size: 18px; }
.doc-panel { border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--panel); padding: 4px 14px 8px; }
.doc-title { margin: 8px 0 4px; font-size: 13px; color: var(--muted); font-weight: 600; }
.search { display: flex; gap: 8px; }
.search input { flex: 1; }
.results { display: flex; flex-direction: column; gap: 12px; }
.result { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px; background: var(--panel); }
.result .meta { display: flex; gap: 10px; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.result .meta .score { color: var(--primary-strong); font-family: var(--mono); }
.result .content { margin: 0; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }

/* 配置 */
.cfg { display: flex; flex-direction: column; gap: 16px; }
.cfg-sec { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px 16px; background: var(--panel); }
.cfg-sec h4 { margin: 0 0 12px; font-size: 14px; }
.field-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.field-row .lbl { flex: none; width: 160px; font-size: 13px; color: var(--muted); }
.field-row input { flex: 1; min-width: 0; }
.ext-grid { display: flex; flex-wrap: wrap; gap: 8px 14px; flex: 1; }
.ext { display: flex; align-items: center; gap: 5px; font-size: 13px; color: var(--text); }
.cfg-hint { color: var(--muted); font-size: 12px; margin: 8px 0 0; line-height: 1.5; }
.cfg-actions { display: flex; }

@media (max-width: 760px) {
  .kb-workspace { padding: 14px; }
  .main-head, .search, .field-row { align-items: stretch; flex-direction: column; }
  .field-row .lbl { width: auto; }
}
</style>
