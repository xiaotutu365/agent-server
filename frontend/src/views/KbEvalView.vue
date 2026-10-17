<template>
  <div class="eval-page">
    <header class="page-head">
      <div>
        <h2>检索评测</h2>
        <p class="hint">对指定知识库运行评测集，量化检索质量：Recall@k / MRR 自算 + Ragas context 指标（双轨）。</p>
      </div>
      <div class="kb-picker">
        <label class="lbl" for="eval-kb">知识库</label>
        <select id="eval-kb" v-model="current" :disabled="loadingKbs">
          <option v-for="k in kbs" :key="k.kb_id" :value="k.kb_id">{{ k.kb_id }}</option>
        </select>
      </div>
    </header>

    <p v-if="!kbs.length && !loadingKbs" class="empty">暂无知识库，请先在「知识库管理」创建并上传文档。</p>

    <template v-if="current">
      <section class="card pad" aria-label="评测集编辑">
        <div class="field-head">
          <label class="lbl" for="eval-editor">评测集（JSON：query + expected_files，可选 reference）</label>
          <button class="link" @click="doSaveEvalSet">保存评测集</button>
        </div>
        <textarea
          id="eval-editor"
          v-model="evalText"
          class="eval-editor"
          rows="10"
          spellcheck="false"
          placeholder='[{"query": "…", "expected_files": ["a.md"], "reference": "期望片段原文（可选）"}]'
        ></textarea>
        <p v-if="evalTemplate" class="cfg-hint">当前为示例模板，请替换为真实评测问题后保存。</p>
        <p class="cfg-hint">
          expected_files 驱动 Recall@k / MRR（零 LLM 依赖）；reference 用于 Ragas context 指标（需配置默认 chat 模型作 judge，未配置时自动跳过）。
        </p>
      </section>

      <section class="card pad run-row" aria-label="运行评测">
        <label class="lbl" for="eval-topk">top_k</label>
        <input id="eval-topk" v-model.number="evalTopK" type="number" min="1" step="1" />
        <button class="btn btn-primary" :disabled="evalRunning || !evalItems.length" @click="doRunEval">
          {{ evalRunning ? '评测中…' : '运行评测' }}
        </button>
        <span class="cfg-hint">共 {{ evalItems.length }} 条评测问题</span>
      </section>

      <div v-if="evalError" class="err">{{ evalError }}</div>

      <template v-if="evalResult">
        <section class="card pad" aria-label="汇总指标">
          <h3 class="sec-title">汇总指标</h3>
          <div class="eval-summary">
            <div class="metric"><span class="m-val">{{ pct(evalResult.summary.recall_at_k) }}</span><span class="m-lbl">Recall@k</span></div>
            <div class="metric"><span class="m-val">{{ evalResult.summary.mrr.toFixed(3) }}</span><span class="m-lbl">MRR</span></div>
            <template v-if="evalResult.summary.ragas_available">
              <div class="metric"><span class="m-val">{{ pct(evalResult.summary.context_precision) }}</span><span class="m-lbl">Ragas Precision</span></div>
              <div class="metric"><span class="m-val">{{ pct(evalResult.summary.context_recall) }}</span><span class="m-lbl">Ragas Recall</span></div>
            </template>
          </div>
          <p v-if="evalResult.summary.ragas_error" class="cfg-hint">Ragas 指标未计算：{{ evalResult.summary.ragas_error }}</p>
        </section>

        <section aria-label="逐条结果">
          <h3 class="sec-title">逐条明细（{{ evalResult.items.length }} 条）</h3>
          <article v-for="(it, i) in evalResult.items" :key="i" class="card pad eval-item">
            <header class="eval-item-head">
              <strong class="q">{{ it.query }}</strong>
              <span class="badge" :class="it.recall_at_k >= 1 ? 'badge-ok-line' : 'badge-warn-line'">
                Recall {{ pct(it.recall_at_k) }} · RR {{ it.reciprocal_rank.toFixed(2) }}
              </span>
            </header>
            <div class="hits">
              <article v-for="(h, j) in it.hits" :key="j" class="result">
                <div class="meta">
                  <span class="src">{{ h.source || '未知来源' }}</span>
                  <span class="idx">rank {{ j + 1 }} · #{{ (h.chunk_idx ?? 0) + 1 }}</span>
                  <span v-if="typeof h.score === 'number'" class="score">RRF {{ h.score.toFixed(3) }}</span>
                  <span class="badge" :class="h.hit ? 'badge-ok-line' : 'badge-bad-line'">{{ h.hit ? '命中' : '未命中' }}</span>
                </div>
                <p class="content">{{ h.text }}</p>
              </article>
              <p v-if="!it.hits.length" class="empty" role="status">无召回结果。</p>
            </div>
          </article>
        </section>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listKbs, getEvalSet, saveEvalSet, runEval } from '../api/kb'

const route = useRoute()
const router = useRouter()

const kbs = ref([])
const current = ref('')
const loadingKbs = ref(false)

const evalText = ref('')
const evalTemplate = ref(false)
const evalTopK = ref(5)
const evalRunning = ref(false)
const evalResult = ref(null)
const evalError = ref('')

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

// 库选择与路由 query 双向同步：?kb=xxx 可直达（知识库页评测按钮跳转进来）
watch(current, (kb) => {
  if (kb && route.query.kb !== kb) router.replace({ query: { ...route.query, kb } })
  if (kb) loadEvalSet(kb)
})

async function loadKbs() {
  loadingKbs.value = true
  evalError.value = ''
  try {
    kbs.value = await listKbs()
    const wanted = route.query.kb
    const hit = wanted && kbs.value.find((k) => k.kb_id === wanted)
    current.value = hit ? hit.kb_id : (kbs.value[0]?.kb_id || '')
  } catch (e) {
    evalError.value = e.message
  } finally {
    loadingKbs.value = false
  }
}

async function loadEvalSet(kbId) {
  evalResult.value = null
  evalError.value = ''
  evalText.value = ''
  evalTemplate.value = false
  try {
    const d = await getEvalSet(kbId)
    evalText.value = JSON.stringify(d.items, null, 2)
    evalTemplate.value = !!d.template
  } catch (e) {
    evalError.value = e.message
  }
}

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

onMounted(loadKbs)
</script>

<style scoped>
.eval-page { display: flex; flex-direction: column; gap: 14px; max-width: 980px; }
.kb-picker { display: flex; align-items: center; gap: 8px; }
.kb-picker select { min-width: 180px; }
.lbl { font-size: 13px; color: var(--muted); font-weight: 600; }
.pad { padding: 14px 16px; }
.sec-title { margin: 0 0 10px; font-size: 14px; }
.field-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.run-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.run-row input { width: 90px; }

.eval-editor {
  width: 100%; font-family: var(--mono); font-size: 12px; line-height: 1.6;
  padding: 10px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--panel); color: var(--text); resize: vertical;
}
.cfg-hint { color: var(--muted); font-size: 12px; margin: 8px 0 0; line-height: 1.5; }

.eval-summary { display: flex; flex-wrap: wrap; gap: 10px; }
.eval-summary .metric {
  flex: 1; min-width: 140px; display: flex; flex-direction: column; gap: 2px;
  padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--panel);
}
.eval-summary .m-val { font-size: 22px; font-weight: 700; font-family: var(--mono); }
.eval-summary .m-lbl { font-size: 12px; color: var(--muted); }

.eval-item-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.eval-item-head .q { word-break: break-word; }
.badge-ok-line { color: var(--success, #16a34a); border-color: var(--success, #16a34a); }
.badge-warn-line { color: var(--warning, #d97706); border-color: var(--warning, #d97706); }
.badge-bad-line { color: var(--destructive); border-color: var(--destructive); }

.hits { display: flex; flex-direction: column; gap: 10px; }
.result { border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 14px; background: var(--panel); }
.result .meta { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.result .meta .score { color: var(--primary-strong); font-family: var(--mono); }
.result .content { margin: 0; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
</style>
