<template>
  <div class="kb">
    <aside class="kb-side">
      <div class="side-head">
        <h3>知识库</h3>
        <div class="side-actions">
          <button class="mini" @click="openSettings">配置</button>
          <button class="mini" @click="load">刷新</button>
        </div>
      </div>

      <form class="create" @submit.prevent="doCreate">
        <input v-model="newId" placeholder="新知识库 ID（如 policy）" />
        <button type="submit" :disabled="!newId.trim()">创建</button>
      </form>

      <ul class="kb-list">
        <li
          v-for="k in kbs"
          :key="k.kb_id"
          :class="{ active: k.kb_id === current }"
          @click="select(k.kb_id)"
        >
          <div class="row">
            <span class="name">{{ k.kb_id }}</span>
            <span class="count">{{ k.points_count || 0 }}</span>
          </div>
          <button class="del" @click.stop="doDelete(k.kb_id)">删除</button>
        </li>
      </ul>
      <p v-if="!kbs.length" class="hint">暂无知识库，先创建一个。</p>
    </aside>

    <section class="kb-main">
      <template v-if="showSettings">
        <header class="main-head">
          <h2>知识库配置</h2>
          <button class="upload" @click="showSettings = false">← 返回</button>
        </header>

        <div v-if="settingsError" class="error">{{ settingsError }}</div>
        <div v-if="settingsMsg" class="msg">{{ settingsMsg }}</div>

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
            <button class="save" :disabled="settingsSaving" @click="saveSettings">
              {{ settingsSaving ? '保存中…' : '保存配置' }}
            </button>
          </div>
        </div>
      </template>
      <template v-else>
        <template v-if="current">
        <header class="main-head">
          <h2>{{ current }}</h2>
          <label class="upload">
            上传文档
            <input type="file" accept=".txt,.md,.pdf,.docx,.csv,.jsonl" @change="doUpload" :disabled="uploading" />
          </label>
        </header>

        <form class="search" @submit.prevent="doSearch">
          <input v-model="query" placeholder="在此知识库中检索…" />
          <button type="submit" :disabled="!query.trim() || searching">检索</button>
        </form>

        <div v-if="error" class="error">{{ error }}</div>
        <div v-if="msg" class="msg">{{ msg }}</div>

        <div class="results">
          <article v-for="(r, i) in results" :key="i" class="result">
            <div class="meta">
              <span class="src">{{ r.metadata.source || '未知来源' }}</span>
              <span class="idx">#{{(r.metadata.chunk_idx ?? 0) + 1}}</span>
            </div>
            <p class="content">{{ r.content }}</p>
          </article>
          <p v-if="searched && !results.length" class="hint">未找到相关内容。</p>
        </div>
      </template>
        <div v-else class="placeholder">← 选择或创建一个知识库</div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref, reactive } from 'vue'
import { listKbs, createKb, deleteKb, uploadDoc, searchKb, getKbSettings, saveKbSettings } from '../api/kb'

const kbs = ref([])
const current = ref('')
const newId = ref('')
const query = ref('')
const results = ref([])
const searched = ref(false)
const uploading = ref(false)
const searching = ref(false)
const error = ref('')
const msg = ref('')

// 知识库配置面板
const ALL_DOC_TYPES = ['.txt', '.md', '.pdf', '.docx', '.csv', '.jsonl', '.html', '.json', '.pptx', '.xlsx']
const showSettings = ref(false)
const settingsError = ref('')
const settingsMsg = ref('')
const settingsSaving = ref(false)
const settingsForm = reactive({
  supported_ext: ['.txt', '.md', '.pdf', '.docx', '.csv', '.jsonl'],
  chunk_size: 800,
  chunk_overlap: 100,
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

async function load() {
  try {
    kbs.value = await listKbs()
    if (current.value && !kbs.value.find((k) => k.kb_id === current.value)) {
      current.value = ''
    }
  } catch (e) {
    error.value = e.message
  }
}

function select(id) {
  current.value = id
  results.value = []
  searched.value = false
  error.value = ''
  msg.value = ''
}

async function doCreate() {
  const id = newId.value.trim()
  if (!id) return
  try {
    await createKb(id)
    newId.value = ''
    await load()
    select(id)
  } catch (e) {
    error.value = e.message
  }
}

async function doDelete(id) {
  if (!confirm(`确认删除知识库 "${id}"？该操作不可恢复。`)) return
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
    await load()
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

async function openSettings() {
  showSettings.value = true
  settingsError.value = ''
  settingsMsg.value = ''
  try {
    const s = await getKbSettings()
    for (const k of Object.keys(settingsForm)) {
      if (s[k] !== undefined) settingsForm[k] = s[k]
    }
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
    settingsMsg.value = '配置已保存 ✓'
  } catch (e) {
    settingsError.value = e.message
  } finally {
    settingsSaving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.kb {
  flex: 1;
  display: flex;
  min-height: 0;
  max-width: 1120px;
  width: 100%;
  margin: 0 auto;
}
.kb-side {
  width: 280px;
  flex: none;
  border-right: 1px solid var(--border);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
}
.side-head { display: flex; align-items: center; justify-content: space-between; }
.side-head h3 { margin: 0; font-size: 15px; }
.mini { border: 1px solid var(--border); background: transparent; color: var(--muted);
  padding: 3px 10px; border-radius: 7px; cursor: pointer; font-size: 12px; }
.create { display: flex; gap: 6px; }
.create input { flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 8px;
  padding: 7px 10px; background: var(--bg); color: var(--text); font-size: 13px; }
.create button { border: none; background: var(--accent); color: #fff; padding: 7px 12px;
  border-radius: 8px; cursor: pointer; font-size: 13px; }
.create button:disabled { opacity: 0.5; cursor: not-allowed; }

.kb-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.kb-list li {
  border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px;
  cursor: pointer; display: flex; flex-direction: column; gap: 4px; background: var(--bg);
}
.kb-list li.active { border-color: var(--accent); background: var(--panel-hover); }
.kb-list .row { display: flex; align-items: center; justify-content: space-between; }
.kb-list .name { font-size: 13px; font-weight: 600; }
.kb-list .count { font-size: 12px; color: var(--muted); }
.kb-list .del { align-self: flex-end; border: none; background: transparent; color: #d93025;
  font-size: 12px; cursor: pointer; padding: 0; }

.hint { color: var(--muted); font-size: 13px; }
.kb-main { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.main-head { display: flex; align-items: center; justify-content: space-between; }
.main-head h2 { margin: 0; font-size: 18px; }
.upload { border: 1px solid var(--border); padding: 7px 12px; border-radius: 8px;
  font-size: 13px; cursor: pointer; background: var(--panel); color: var(--text); }
.upload input { display: none; }
.search { display: flex; gap: 8px; }
.search input { flex: 1; border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;
  background: var(--bg); color: var(--text); font-size: 14px; }
.search button { border: none; background: var(--accent); color: #fff; padding: 10px 20px;
  border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 600; }
.search button:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: #d93025; font-size: 13px; }
.msg { color: #22a06b; font-size: 13px; }
.results { display: flex; flex-direction: column; gap: 12px; }
.result { border: 1px solid var(--border); border-radius: 12px; padding: 14px; background: var(--panel); }
.result .meta { display: flex; gap: 10px; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.result .content { margin: 0; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.placeholder { color: var(--muted); margin: auto; }
.side-actions { display: flex; gap: 6px; }
.cfg { display: flex; flex-direction: column; gap: 16px; }
.cfg-sec { border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; background: var(--panel); }
.cfg-sec h4 { margin: 0 0 12px; font-size: 14px; }
.field-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.field-row .lbl { flex: none; width: 160px; font-size: 13px; color: var(--muted); }
.field-row input { flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; background: var(--bg); color: var(--text); font-size: 13px; font-family: inherit; }
.field-row input:focus { outline: none; border-color: var(--accent); }
.ext-grid { display: flex; flex-wrap: wrap; gap: 8px 14px; flex: 1; }
.ext { display: flex; align-items: center; gap: 5px; font-size: 13px; color: var(--text); }
.cfg-hint { color: var(--muted); font-size: 12px; margin: 8px 0 0; line-height: 1.5; }
.cfg-actions { display: flex; }
.cfg-actions .save { border: none; background: var(--accent); color: #fff; padding: 10px 22px; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 600; }
.cfg-actions .save:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
