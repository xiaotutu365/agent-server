<template>
  <div class="list-page">
    <div class="page-head">
      <div>
        <h2>工具列表</h2>
        <p class="hint">
          系统已注册的全部工具，按能力分组；点击工具行可展开查看
          <b>提示词、参数定义与 JSON Schema</b>。共 <b>{{ total }}</b> 个内置工具。
        </p>
      </div>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <!-- 内置工具目录 -->
    <div v-for="g in groups" :key="g.key" class="group-card">
      <div class="group-head">
        <span class="g-label">{{ g.label }}</span>
        <span class="g-count">{{ g.tools.length }} 个</span>
      </div>
      <div v-for="t in g.tools" :key="t.name" class="tool-row">
        <button
          class="tool-main"
          :aria-expanded="!!open[t.name]"
          :aria-controls="'tool-detail-' + t.name"
          @click="toggle(t)"
        >
          <span class="chev" :class="{ open: open[t.name] }">▸</span>
          <span class="name mono">{{ t.name }}</span>
          <span class="desc-short">{{ t.description || '—' }}</span>
        </button>

        <div
          v-if="open[t.name] && details[t.name]"
          :id="'tool-detail-' + t.name"
          class="tool-detail"
        >
          <div class="dt-block">
            <div class="dt-label">所属分组</div>
            <span class="tag">{{ details[t.name].group_label }}</span>
          </div>
          <div class="dt-block">
            <div class="dt-label">提示词（给模型的工具描述）</div>
            <pre class="dt-pre">{{ details[t.name].prompt }}</pre>
          </div>
          <div class="dt-block">
            <div class="dt-label">参数定义</div>
            <table v-if="details[t.name].params && details[t.name].params.length" class="sub-tbl">
              <thead>
                <tr><th>参数</th><th>类型</th><th>必填</th><th>默认</th><th>说明</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in details[t.name].params" :key="p.name">
                  <td class="mono">{{ p.name }}</td>
                  <td>{{ p.type }}</td>
                  <td>{{ p.required ? '是' : '否' }}</td>
                  <td>{{ p.default === null || p.default === undefined ? '—' : p.default }}</td>
                  <td>{{ p.description || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="muted">该工具无参数。</div>
          </div>
          <div class="dt-block" v-if="details[t.name].schema">
            <details>
              <summary>JSON Schema 原文</summary>
              <pre class="dt-pre json">{{ JSON.stringify(details[t.name].schema, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty" role="status">加载中…</div>
    <div v-else-if="!groups.length && !error" class="empty" role="status">暂无注册工具。</div>

  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiFetch } from '../auth'

// ---------------- 内置工具 ----------------
const groups = ref([])
const total = ref(0)
const error = ref('')
const loading = ref(false)
const open = reactive({})
const details = reactive({})

onMounted(loadTools)

async function loadTools() {
  error.value = ''
  loading.value = true
  try {
    const r = await apiFetch('/api/admin/tools')
    if (!r.ok) throw new Error('加载失败')
    const data = await r.json()
    groups.value = data.groups || []
    total.value = data.total || 0
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

// ---------------- 内置工具展开 ----------------
async function toggle(t) {
  if (open[t.name]) { open[t.name] = false; return }
  if (!details[t.name]) {
    try {
      const r = await apiFetch(`/api/admin/tools/${encodeURIComponent(t.name)}`)
      if (r.ok) details[t.name] = await r.json()
    } catch (e) { /* 详情失败仍展开 */ }
  }
  open[t.name] = true
}
</script>

<style scoped>
.group-card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 16px; }
.group-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--panel-2); }
.g-label { font-weight: 600; font-size: 14px; color: var(--text); }
.g-count { font-size: 12px; color: var(--muted); }

.tool-row { border-bottom: 1px solid var(--border); }
.tool-row:last-child { border-bottom: none; }
.tool-main {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 12px 16px; text-align: left; font-family: inherit;
  background: transparent; border: none; border-radius: 0;
}
.tool-main:hover { background: var(--panel-hover); }
.chev { color: var(--muted); transition: transform 0.15s; flex: none; }
.chev.open { transform: rotate(90deg); }
.name { font-weight: 600; white-space: nowrap; }
.mono { font-family: var(--mono); font-size: 12px; color: var(--primary); }
.desc-short { color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tool-detail { padding: 4px 16px 18px; background: var(--code-bg); border-top: 1px dashed var(--border); }
.dt-block { margin-top: 14px; }
.dt-label { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.dt-pre { font-family: var(--mono); font-size: 12px; line-height: 1.55; white-space: pre-wrap; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px; margin: 0; max-height: 320px; overflow: auto; word-break: break-word; }
.muted { color: var(--muted); font-size: 13px; }
.sub-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.sub-tbl th, .sub-tbl td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
.sub-tbl th { font-weight: 600; color: var(--muted); background: var(--bg); }
.sub-tbl tr:last-child td { border-bottom: none; }
</style>
