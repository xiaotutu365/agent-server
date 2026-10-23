<template>
  <div class="eda">
    <header class="eda-head">
      <div>
        <h1>EDA 数字芯片逻辑综合 · 多 Agent 流水线</h1>
        <p>
          脚本创建 Agent → 调度运行 Agent → 报告/日志分析 Agent。每轮依据
          <b>WNS</b>（最差负裕量）判定是否满足约束；不满足则调整脚本继续迭代。
          WNS 由内置模型推算，便于演示「调整脚本 → WNS 变化」的闭环。
          三个 Agent 各自以不同 <code>system_prompt</code> 复用 <code>/api/chat/stream</code>；
          脚本创建需选定<b>工艺 PDK</b>（标准单元库 / 工艺文件），不同 PDK 的时序特性会直接影响 WNS 收敛演示。
        </p>
      </div>
    </header>

    <!-- 三个步骤框置顶：点击切换下方内容区；运行中自动跟随当前阶段 -->
    <section class="pipeline" role="tablist" aria-label="综合流水线阶段">
      <button
        class="stage" :class="[stageClass('script'), { active: activeStage === 'script' }]"
        role="tab" :aria-selected="activeStage === 'script'" @click="activeStage = 'script'"
      >
        <span class="stage-head"><span class="dot" aria-hidden="true"></span>① 脚本创建 Agent</span>
        <span class="stage-desc">生成综合 Tcl / SDC 脚本</span>
      </button>
      <span class="arrow" aria-hidden="true">→</span>
      <button
        class="stage" :class="[stageClass('run'), { active: activeStage === 'run' }]"
        role="tab" :aria-selected="activeStage === 'run'" @click="activeStage = 'run'"
      >
        <span class="stage-head"><span class="dot" aria-hidden="true"></span>② 调度运行 Agent</span>
        <span class="stage-desc">模拟提交综合并产出日志 / 报告</span>
      </button>
      <span class="arrow" aria-hidden="true">→</span>
      <button
        class="stage" :class="[stageClass('report'), { active: activeStage === 'report' }]"
        role="tab" :aria-selected="activeStage === 'report'" @click="activeStage = 'report'"
      >
        <span class="stage-head"><span class="dot" aria-hidden="true"></span>③ 报告分析 Agent</span>
        <span class="stage-desc">解析 WNS、判定并给建议</span>
      </button>
    </section>

    <section v-if="task" class="overview">
      <div class="ov-card">
        <div class="ov-label">迭代轮次</div>
        <div class="ov-val">{{ task.iteration }}</div>
      </div>
      <div class="ov-card">
        <div class="ov-label">工艺 PDK</div>
        <div class="ov-val pdk">{{ task.pdk }}</div>
      </div>
      <div class="ov-card" :class="wnsClass">
        <div class="ov-label">WNS (ns)</div>
        <div class="ov-val">{{ task.wns === null ? '—' : task.wns }}</div>
        <div class="ov-sub">{{ task.wns === null ? '等待运行' : (task.wns >= 0 ? '✓ 满足约束' : '✗ 未满足') }}</div>
      </div>
      <div class="ov-card">
        <div class="ov-label">状态</div>
        <div class="ov-val status">{{ statusText }}</div>
      </div>
    </section>

    <!-- ① 脚本创建：设计需求表单 + 综合脚本产出 -->
    <section v-if="activeStage === 'script'" class="stage-panel">
      <div class="config">
        <label class="full">
          设计需求 / RTL 描述
          <textarea v-model="form.design" rows="3" placeholder="例如：实现一个 32 位 RISC-V 处理器核，目标工艺 28nm，需综合为门级网表"></textarea>
        </label>
        <div class="row">
          <label>
            工艺 PDK（节点）
            <select v-model="form.pdk">
              <option value="28nm">28nm 平面 CMOS</option>
              <option value="14nm">14nm FinFET</option>
              <option value="7nm">7nm FinFET</option>
              <option value="5nm">5nm（先进节点）</option>
            </select>
          </label>
          <label>
            目标时钟周期 (ns)
            <input v-model="form.targetPeriod" type="number" min="0.1" step="0.1" />
          </label>
          <label>
            综合工具
            <select v-model="form.tool">
              <option v-for="t in TOOLS" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>
          <label class="grow">
            额外约束（可选）
            <input v-model="form.constraint" placeholder="例如：面积上限 50k 门 / 功耗约束" />
          </label>
        </div>
        <div class="actions">
          <button
            class="primary"
            :disabled="!form.design.trim() || streaming || (task && task.status === 'running')"
            @click="startSynthesis"
          >▶ 开始综合</button>
          <button class="ghost" :disabled="streaming" @click="loadExample">载入示例</button>
          <button class="ghost" :disabled="streaming" @click="reset">重置</button>
        </div>
      </div>
      <div v-if="task && task.script" class="out-block">
        <div class="out-head">
          <div class="out-title">综合脚本<span v-if="editScript" class="edit-tag">编辑中——修改将作为②调度运行的输入</span></div>
          <div class="out-tools">
            <button class="mini-btn" @click="copyScript">{{ copied ? '✓ 已复制' : '复制' }}</button>
            <button class="mini-btn" @click="editScript = !editScript">{{ editScript ? '高亮视图' : '编辑' }}</button>
          </div>
        </div>
        <pre v-if="!editScript" class="fullout code-hl" v-html="hlScript(task.script)"></pre>
        <textarea v-else v-model="task.script" class="fullout code-edit" spellcheck="false"></textarea>
      </div>
      <div v-else-if="!task" class="empty-hint">填写设计需求后点击「开始综合」，生成的综合脚本会展示在本页，可高亮查看、复制或手动编辑。</div>
    </section>

    <!-- ② 调度运行：作业信息 + 资源分配 + 进度 + 运行日志 -->
    <section v-else-if="activeStage === 'run'" class="stage-panel">
      <div v-if="job" class="job-grid">
        <div class="job-card">
          <div class="jc-title">综合作业</div>
          <div class="jc-row"><span>作业 ID</span><b class="mono">{{ job.jobId }}</b></div>
          <div class="jc-row"><span>EDA 工具</span><b>{{ job.tool }}</b></div>
          <div class="jc-row"><span>作业状态</span><b :class="job.status === '成功' ? 'ok-text' : 'run-text'">{{ job.status }}</b></div>
        </div>
        <div class="job-card">
          <div class="jc-title">资源分配</div>
          <div class="jc-row"><span>执行节点</span><b class="mono">{{ job.node }}</b></div>
          <div class="jc-row"><span>CPU</span><b>{{ job.cores }} 核</b></div>
          <div class="jc-row"><span>内存</span><b>{{ job.memGB }} GB</b></div>
          <div class="jc-row"><span>调度队列</span><b>前方等待 {{ job.queueAhead }} 个作业</b></div>
        </div>
      </div>

      <div v-if="job" class="job-card progress-card">
        <div class="jc-title">运行进度 <span class="pct">{{ progress }}%</span></div>
        <div class="pbar" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
          <div class="pbar-fill" :style="{ width: progress + '%' }"></div>
        </div>
        <div class="stage-steps">
          <span v-for="s in stages" :key="s.name" class="step" :class="s.status">
            <span class="step-mark" aria-hidden="true">{{ s.status === 'done' ? '✓' : s.status === 'running' ? '●' : '○' }}</span>
            {{ s.name }}<i v-if="s.dur" class="step-dur">{{ s.dur }}s</i>
          </span>
        </div>
      </div>

      <div v-if="task && task.runLog" class="out-block">
        <div class="out-title">工具运行日志 / 综合报告（调度运行 Agent 生成）</div>
        <pre class="fullout">{{ task.runLog }}</pre>
      </div>
      <div v-else-if="!job" class="empty-hint">暂无运行作业——① 脚本生成后，调度运行 Agent 会在此提交作业：展示所用 EDA 工具、分配的计算资源与实时进度，并流式输出运行日志。</div>
    </section>

    <!-- ③ 报告分析：WNS 趋势图 + 判定 + 分析结论 + 调整重跑入口 -->
    <section v-else class="stage-panel">
      <div v-if="chart" class="job-card">
        <div class="jc-title">WNS 收敛趋势（ns · 约束要求 ≥ 0）</div>
        <svg :viewBox="`0 0 ${chart.w} ${chart.h}`" class="wns-chart" role="img" aria-label="各迭代轮次 WNS 趋势图">
          <line :x1="14" :x2="chart.w - 14" :y1="chart.zeroY" :y2="chart.zeroY" class="zero-line" />
          <text :x="chart.w - 16" :y="chart.zeroY - 6" text-anchor="end" class="zero-label">0 ns</text>
          <polyline v-if="chart.pts.length > 1" :points="chart.line" fill="none" class="trend-line" />
          <g v-for="p in chart.pts" :key="p.iter">
            <circle :cx="p.x" :cy="p.y" r="5" :class="p.ok ? 'pt ok' : 'pt bad'" />
            <text :x="p.x" :y="p.y - 11" text-anchor="middle" :class="p.ok ? 'pt-label ok' : 'pt-label bad'">{{ p.wns }}</text>
            <text :x="p.x" :y="chart.h - 8" text-anchor="middle" class="x-label">第 {{ p.iter + 1 }} 轮</text>
          </g>
        </svg>
      </div>
      <div v-if="task && task.wns !== null" class="wns-line" :class="wnsClass">
        本轮 WNS = {{ task.wns }} ns（约束要求 ≥ 0 ns）—— {{ task.wns >= 0 ? '✓ 满足' : '✗ 未满足' }}
      </div>
      <div v-if="task && task.analysis" class="out-block">
        <div class="out-title">时序分析结论与调整建议</div>
        <pre class="fullout">{{ task.analysis }}</pre>
      </div>
      <div v-if="task && task.status === 'need-adjust' && !streaming" class="actions">
        <button class="primary" @click="adjustAndRerun">↻ 调整脚本并重跑</button>
      </div>
      <div v-if="!task || !task.analysis" class="empty-hint">暂无分析结论——② 产出综合报告后，报告分析 Agent 会在此解析 WNS 并给出建议。</div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { streamChat } from '../api/chat'

const SCRIPT_PROMPT = `你是一名资深的数字芯片逻辑综合（RTL Synthesis）工程师，使用 Synopsys Design Compiler 风格的 Tcl/SDC 脚本。根据用户给出的设计需求（含目标时钟周期与额外约束），生成一份完整、可执行的综合脚本：读入 RTL、设置时钟 create_clock、IO 与面积/时序约束、编译/映射/优化策略，并在末尾用注释说明关键约束。只输出脚本与必要的中文说明，不要闲聊。`
const RUN_PROMPT = `你是一名 EDA 流程调度工程师，负责把综合脚本提交到综合服务器并模拟运行。基于用户提供的综合脚本，输出模拟的综合运行日志（步骤：读库→读RTL→编译→映射→优化→写出）与一份模拟的综合报告摘要（面积、时序、各阶段耗时）。注意：真实 WNS 数值由外部注入，你只需描述运行过程与日志，不要编造 WNS 数值。`
const REPORT_PROMPT = `你是一名时序签核（STA）与综合报告分析专家。用户会提供综合运行日志/报告以及关键指标 WNS（最差负裕量，单位 ns）。请解析内容、判断 WNS 是否满足约束（要求 WNS ≥ 0），并给出明确结论（满足 / 不满足）以及若不满足的具体脚本调整建议（如调整时钟周期、增加优化努力、修改约束等）。输出结构化的中文结论。`

const form = reactive({ design: '', pdk: '28nm', targetPeriod: 10, constraint: '', tool: 'Design Compiler (DC)' })
const streaming = ref(false)
const task = ref(null)
const stageStatus = reactive({ script: 'idle', run: 'idle', report: 'idle' })
const lastSuggestion = ref('')
// 当前查看的阶段页签；运行中自动跟随正在执行的阶段
const activeStage = ref('script')

// —— ② 调度运行：作业 / 资源池 / 进度（前端模拟，演示调度台形态）——
const TOOLS = ['Design Compiler (DC)', 'Fusion Compiler (FC)', 'Yosys（开源）']
const NODE_POOL = [
  { id: 'syn-node-01', cores: 32, memGB: 128 },
  { id: 'syn-node-02', cores: 32, memGB: 128 },
  { id: 'syn-node-03', cores: 16, memGB: 64 },
]
const STAGE_NAMES = ['读入库', '读入 RTL', '加载约束', '编译 elaborate', '映射优化', '写出报告']
const job = ref(null)          // { jobId, tool, node, cores, memGB, status, queueAhead }
const stages = ref([])         // [{ name, status: pending|running|done, dur }]
const progress = ref(0)
let progTimer = null

function startJobConsole() {
  const node = NODE_POOL[Math.floor(Math.random() * NODE_POOL.length)]
  const cores = Math.min(16, node.cores)
  job.value = {
    jobId: `JOB-${Date.now().toString(36).toUpperCase()}`,
    tool: form.tool, node: node.id, cores, memGB: cores * 4,
    status: '运行中', queueAhead: Math.floor(Math.random() * 2),
  }
  stages.value = STAGE_NAMES.map((n) => ({ name: n, status: 'pending', dur: null, _start: 0 }))
  progress.value = 0
  let ticks = 0
  clearInterval(progTimer)
  progTimer = setInterval(() => {
    ticks += 1
    const cur = stages.value.find((s) => s.status !== 'done')
    if (cur) {
      if (cur.status === 'pending') { cur.status = 'running'; cur._start = ticks }
      else if (ticks - cur._start >= 3) { cur.status = 'done'; cur.dur = 3 + Math.floor(Math.random() * 3) }
    }
    const done = stages.value.filter((s) => s.status === 'done').length
    progress.value = Math.min(99, Math.round((done / STAGE_NAMES.length) * 100))
  }, 1000)
}

function finishJobConsole() {
  clearInterval(progTimer); progTimer = null
  stages.value.forEach((s) => { if (s.status !== 'done') { s.status = 'done'; s.dur = s.dur ?? 3 } })
  progress.value = 100
  if (job.value) job.value.status = '成功'
}

function clearJobConsole() {
  clearInterval(progTimer); progTimer = null
  job.value = null
  stages.value = []
  progress.value = 0
}

// —— ① 脚本查看/编辑：轻量 Tcl/SDC 高亮（无第三方依赖）——
const editScript = ref(false)
const copied = ref(false)
const KEYWORDS = [
  'current_design', 'read_verilog', 'read_db', 'read_lib', 'link_design', 'create_clock',
  'set_clock_uncertainty', 'set_input_delay', 'set_output_delay', 'set_load', 'set_driving_cell',
  'set_max_area', 'set_max_transition', 'set_max_fanout', 'compile_ultra', 'compile',
  'report_area', 'report_timing', 'report_qor', 'write', 'source', 'get_clocks',
  'all_inputs', 'all_outputs', 'exit',
]
function escapeHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
function hlLine(line) {
  if (line.trim().startsWith('#')) return `<span class="hl-com">${escapeHtml(line)}</span>`
  const ci = line.indexOf('#')
  let code = escapeHtml(ci >= 0 ? line.slice(0, ci) : line)
  const com = ci >= 0 ? `<span class="hl-com">${escapeHtml(line.slice(ci))}</span>` : ''
  code = code.replace(/"[^"]*"/g, (m) => `<span class="hl-str">${m}</span>`)
  code = code.replace(/\b\d+(?:\.\d+)?(?:ns|ps|us|fF|pF)?\b/g, (m) => `<span class="hl-num">${m}</span>`)
  for (const kw of KEYWORDS) {
    code = code.replace(new RegExp(`\\b${kw}\\b`, 'g'), (m) => `<span class="hl-kw">${m}</span>`)
  }
  return code + com
}
function hlScript(text) {
  return (text || '').split('\n')
    .map((line, i) => `<span class="cl"><span class="lnum">${i + 1}</span>${hlLine(line) || '&nbsp;'}</span>`)
    .join('')
}
async function copyScript() {
  try {
    await navigator.clipboard.writeText(task.value?.script || '')
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* 非安全上下文剪贴板不可用时静默 */ }
}

// —— ③ WNS 收敛趋势（跨迭代记录，SVG 折线）——
const wnsHistory = ref([])
const chart = computed(() => {
  const hs = wnsHistory.value
  if (!hs.length) return null
  const w = 560, h = 210, pad = 40
  const vals = hs.map((x) => x.wns)
  const lo = Math.min(...vals, 0), hi = Math.max(...vals, 0)
  const span = (hi - lo) || 1
  const xAt = (i) => hs.length === 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (hs.length - 1)
  const yAt = (v) => h - pad - ((v - lo) / span) * (h - 2 * pad)
  return {
    w, h,
    zeroY: yAt(0),
    pts: hs.map((x, i) => ({ x: xAt(i), y: yAt(x.wns), wns: x.wns, iter: x.iter, ok: x.wns >= 0 })),
    line: hs.map((x, i) => `${xAt(i)},${yAt(x.wns)}`).join(' '),
  }
})

function genId() { return 'eda-' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4) }

const statusText = computed(() => {
  if (!task.value) return '空闲'
  if (streaming.value) return '运行中'
  return { running: '运行中', done: '✓ 满足', 'need-adjust': '需调整' }[task.value.status] || task.value.status
})
const wnsClass = computed(() => {
  if (!task.value || task.value.wns === null) return ''
  return task.value.wns >= 0 ? 'ok' : 'bad'
})
function stageClass(k) {
  return { idle: '', running: 'on', done: 'done' }[stageStatus[k]] || ''
}

// 不同 PDK 的时序特性：先进节点单元延迟更低、每轮优化收益更高（演示 PDK 对 WNS 收敛的影响）
const PDK_PROFILES = {
  '28nm': { improve: 0.25, base: 1.0 },
  '14nm': { improve: 0.30, base: 1.0 },
  '7nm':  { improve: 0.40, base: 0.9 },
  '5nm':  { improve: 0.50, base: 0.8 },
}
// 内置 WNS 推算：随迭代优化，受 PDK 节点影响收敛速度；初始超标 base ns
function computeWNS(pdk, iter) {
  const p = PDK_PROFILES[pdk] || PDK_PROFILES['28nm']
  const wns = p.improve * iter - p.base
  return Math.round(wns * 1000) / 1000
}

async function runAgentStage(systemPrompt, threadId, message, onText) {
  let acc = ''
  try {
    await streamChat(
      message, threadId,
      {
        onToken: (t) => { acc += t; onText?.(acc) },
        onToolStart() {}, onToolEnd() {}, onPlan() {}, onInterrupt() {},
        onError(m) { acc += `\n[错误] ${m}`; onText?.(acc) },
        onDone() {},
      },
      new AbortController().signal, null, systemPrompt,
    )
  } catch (e) {
    acc += `\n[异常] ${e.message || e}`
    onText?.(acc)
  }
  return acc
}

function buildScriptMessage(iter) {
  let m = `设计需求：${form.design}\n工艺 PDK（节点）：${form.pdk}\n目标时钟周期：${form.targetPeriod} ns\n`
  if (form.constraint) m += `额外约束：${form.constraint}\n`
  m += `请基于所选 ${form.pdk} PDK 的标准单元库与工艺文件（target_library / link_library / 工艺角）编写综合脚本。\n`
  if (iter > 0 && lastSuggestion.value) {
    m += `\n上一轮分析指出 WNS 未满足，调整建议如下，请据此优化脚本：\n${lastSuggestion.value}\n`
  }
  m += `\n请生成对应的逻辑综合 Tcl/SDC 脚本。`
  return m
}

async function runStage(iter) {
  streaming.value = true
  task.value.iteration = iter
  task.value.status = 'running'

  // ① 脚本创建 Agent
  activeStage.value = 'script'
  editScript.value = false
  stageStatus.script = 'running'
  task.value.script = ''
  task.value.script = await runAgentStage(
    SCRIPT_PROMPT, `eda-${task.value.id}-s${iter}-script`, buildScriptMessage(iter),
    (t) => { task.value.script = t },
  )
  stageStatus.script = 'done'

  // ② 调度运行 Agent（模拟）
  activeStage.value = 'run'
  stageStatus.run = 'running'
  startJobConsole()
  task.value.runLog = ''
  const runMsg = `综合脚本如下：\n\n${task.value.script}\n\n请模拟提交到综合服务器执行，输出运行日志与综合报告摘要。`
  task.value.runLog = await runAgentStage(
    RUN_PROMPT, `eda-${task.value.id}-s${iter}-run`, runMsg,
    (t) => { task.value.runLog = t },
  )
  finishJobConsole()
  stageStatus.run = 'done'

  // 计算 WNS（内置模拟）并组装报告
  const wns = computeWNS(form.pdk, iter)
  task.value.wns = wns
  wnsHistory.value.push({ iter, wns })
  task.value.report = `${task.value.runLog}\n\n[模拟综合报告] WNS = ${wns} ns（约束要求 WNS ≥ 0 ns）`

  // ③ 报告分析 Agent
  activeStage.value = 'report'
  stageStatus.report = 'running'
  task.value.analysis = ''
  const repMsg = `综合运行日志与报告：\n\n${task.value.report}\n\n约束要求：WNS ≥ 0 ns。请分析是否满足，并给出结论与调整建议。`
  task.value.analysis = await runAgentStage(
    REPORT_PROMPT, `eda-${task.value.id}-s${iter}-report`, repMsg,
    (t) => { task.value.analysis = t },
  )
  stageStatus.report = 'done'

  // 判定闭环
  task.value.satisfied = wns >= 0
  task.value.status = task.value.satisfied ? 'done' : 'need-adjust'
  streaming.value = false
}

function startSynthesis() {
  if (!form.design.trim() || streaming.value) return
  task.value = {
    id: genId(), iteration: 0, pdk: form.pdk, targetPeriod: Number(form.targetPeriod) || 10,
    script: '', runLog: '', wns: null, report: '', analysis: '', satisfied: false, status: 'running',
  }
  stageStatus.script = stageStatus.run = stageStatus.report = 'idle'
  lastSuggestion.value = ''
  wnsHistory.value = []
  editScript.value = false
  runStage(0)
}

function adjustAndRerun() {
  if (streaming.value || !task.value) return
  lastSuggestion.value = task.value.analysis
  runStage(task.value.iteration + 1)
}

// 内置示例：UART 串口控制器综合需求（一键填入后可直接开始综合）
function loadExample() {
  form.design = '设计一个 UART 串口控制器，顶层模块 uart_top，包含 TX / RX 两个子模块：'
    + '波特率 115200，系统时钟 100MHz，帧格式 8N1（8 数据位、无校验、1 停止位）；'
    + 'TX 接收并行字节并串行发送，RX 采样恢复并行数据；RTL 已用 Verilog 编写，需综合为门级网表。'
  form.pdk = '28nm'
  form.targetPeriod = 10
  form.constraint = '面积上限 30k 门；RX 过采样时钟 8×波特率'
  form.tool = 'Design Compiler (DC)'
}

function reset() {
  if (streaming.value) return
  task.value = null
  stageStatus.script = stageStatus.run = stageStatus.report = 'idle'
  lastSuggestion.value = ''
  activeStage.value = 'script'
  wnsHistory.value = []
  editScript.value = false
  clearJobConsole()
}
</script>

<style scoped>
.eda {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 22px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1120px;
  margin: 0 auto;
}
.eda-head p { margin: 6px 0 0; color: var(--muted); font-size: 13px; line-height: 1.6; max-width: 880px; }
.eda-head code { font-family: var(--mono); background: var(--code-bg); padding: 1px 6px; border-radius: 4px; font-size: 0.9em; }
.eda-head b { color: var(--text); }

.config {
  border: 1px solid var(--border); border-radius: 12px; padding: 16px;
  background: var(--panel); display: flex; flex-direction: column; gap: 12px;
}
.config label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
.config .full { width: 100%; }
.config .row { display: flex; gap: 12px; flex-wrap: wrap; }
.config .row label { flex: 0 0 160px; }
.config .row label.grow { flex: 1 1 240px; }
.config textarea, .config input, .config select {
  border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
  font-family: inherit; font-size: 13px; background: var(--bg); color: var(--text); outline: none;
}
.config textarea { resize: vertical; }
.config textarea:focus, .config input:focus { border-color: var(--accent); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; }
.primary {
  border: none; background: var(--accent); color: #fff; padding: 10px 20px;
  border-radius: 10px; cursor: pointer; font-size: 13px; font-weight: 600;
}
.primary:disabled { opacity: 0.5; cursor: not-allowed; }
.ghost {
  border: 1px solid var(--border); background: transparent; color: var(--muted);
  padding: 10px 18px; border-radius: 10px; cursor: pointer; font-size: 13px;
}
.ghost:hover:not(:disabled) { color: var(--text); border-color: var(--text); }
.ghost:disabled { opacity: 0.5; cursor: not-allowed; }

.overview { display: flex; gap: 12px; flex-wrap: wrap; }
.ov-card {
  flex: 1 1 160px; border: 1px solid var(--border); border-radius: 12px;
  padding: 14px 16px; background: var(--panel);
}
.ov-label { font-size: 12px; color: var(--muted); }
.ov-val { font-size: 26px; font-weight: 700; margin-top: 4px; }
.ov-val.status { font-size: 18px; }
.ov-val.pdk { font-size: 20px; }
.ov-sub { font-size: 12px; margin-top: 4px; color: var(--muted); }
.ov-card.ok { border-color: var(--success); }
.ov-card.ok .ov-val, .ov-card.ok .ov-sub { color: var(--success); }
.ov-card.bad { border-color: var(--destructive); }
.ov-card.bad .ov-val, .ov-card.bad .ov-sub { color: var(--destructive); }

.pipeline { display: flex; align-items: stretch; gap: 10px; flex-wrap: wrap; }
.stage {
  flex: 1 1 240px; border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; background: var(--panel); display: flex; flex-direction: column; gap: 8px;
  cursor: pointer; text-align: left; font-family: inherit; color: var(--text);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.stage:hover { border-color: var(--accent); }
.stage.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 25%, transparent);
}
.stage.on { outline: 2px solid color-mix(in srgb, var(--primary) 30%, transparent); outline-offset: 2px; }
.stage.done { border-color: var(--border); }
.stage-head { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: var(--text); }
.dot { width: 9px; height: 9px; border-radius: 50%; background: var(--border); flex: none; }
.stage.on .dot { background: var(--accent); animation: pulse 1s infinite; }
.stage.done .dot { background: var(--success); }
.stage-desc { font-size: 12px; color: var(--muted); }
.arrow { align-self: center; color: var(--muted); font-size: 20px; flex: none; }

.stage-panel { display: flex; flex-direction: column; gap: 14px; }
.out-block { display: flex; flex-direction: column; gap: 6px; }
.out-title { font-size: 13px; font-weight: 600; color: var(--muted); }
.fullout {
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px; margin: 0; font-size: 12.5px; line-height: 1.6;
  max-height: 480px; overflow: auto; white-space: pre-wrap; word-break: break-word;
}
.empty-hint {
  padding: 26px 18px; text-align: center; color: var(--muted);
  border: 1px dashed var(--border); border-radius: 12px; font-size: 13px;
}
.wns-line {
  border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px;
  font-size: 14px; font-weight: 600; background: var(--panel);
}
.wns-line.ok { border-color: var(--success); color: var(--success); }
.wns-line.bad { border-color: var(--destructive); color: var(--destructive); }

/* ① 脚本查看/编辑 */
.out-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.out-tools { display: flex; gap: 8px; }
.mini-btn {
  border: 1px solid var(--border); border-radius: 8px; background: var(--panel);
  color: var(--text-2); font-size: 12px; padding: 4px 10px; cursor: pointer; font-family: inherit;
}
.mini-btn:hover { border-color: var(--accent); color: var(--accent); }
.edit-tag { font-size: 11px; font-weight: 400; color: var(--accent); margin-left: 10px; }
.code-edit {
  width: 100%; box-sizing: border-box; min-height: 360px; resize: vertical;
  font-family: ui-monospace, Consolas, monospace; color: var(--text);
}
.code-hl { font-family: ui-monospace, Consolas, monospace; }
/* v-html 注入内容不带 scoped 属性，需 :deep */
.code-hl :deep(.cl) { display: flex; min-height: 1.6em; }
.code-hl :deep(.lnum) {
  flex: none; width: 40px; text-align: right; padding-right: 12px;
  color: var(--muted); opacity: 0.5; user-select: none;
}
.code-hl :deep(.hl-kw) { color: var(--primary-strong); font-weight: 600; }
.code-hl :deep(.hl-str) { color: var(--success); }
.code-hl :deep(.hl-num) { color: var(--cta-strong); }
.code-hl :deep(.hl-com) { color: var(--muted); font-style: italic; }

/* ③ WNS 趋势图 */
.wns-chart { width: 100%; height: auto; display: block; }
.wns-chart .zero-line { stroke: var(--success); stroke-dasharray: 5 5; opacity: 0.55; }
.wns-chart .zero-label { fill: var(--muted); font-size: 11px; }
.wns-chart .trend-line { stroke: var(--muted); stroke-width: 2; opacity: 0.7; }
.wns-chart .pt.ok { fill: var(--success); }
.wns-chart .pt.bad { fill: var(--destructive); }
.wns-chart .pt-label { font-size: 12px; font-weight: 700; }
.wns-chart .pt-label.ok { fill: var(--success); }
.wns-chart .pt-label.bad { fill: var(--destructive); }
.wns-chart .x-label { fill: var(--muted); font-size: 11px; }

.job-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.job-card {
  flex: 1 1 300px; border: 1px solid var(--border); border-radius: 12px;
  background: var(--panel); padding: 14px 16px;
}
.jc-title { font-size: 13px; font-weight: 700; color: var(--text-2); margin-bottom: 10px; }
.jc-row {
  display: flex; justify-content: space-between; gap: 12px;
  font-size: 13px; color: var(--muted); padding: 4px 0;
}
.jc-row b { color: var(--text); font-weight: 600; }
.mono { font-family: var(--mono, ui-monospace, monospace); }
.ok-text { color: var(--success) !important; }
.run-text { color: var(--accent) !important; }

.progress-card { flex-basis: 100%; }
.pct { float: right; color: var(--accent); font-weight: 700; }
.pbar { height: 10px; border-radius: 6px; background: var(--code-bg); overflow: hidden; }
.pbar-fill {
  height: 100%; border-radius: 6px; background: var(--accent);
  transition: width 0.8s ease;
}
.stage-steps { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.step {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border); border-radius: 999px; padding: 5px 12px;
  font-size: 12px; color: var(--muted); background: var(--bg);
}
.step.done { color: var(--success); border-color: color-mix(in srgb, var(--success) 45%, transparent); }
.step.running { color: var(--accent); border-color: var(--accent); }
.step.running .step-mark { animation: pulse 1s infinite; }
.step-mark { font-size: 11px; }
.step-dur { font-style: normal; color: var(--muted); margin-left: 2px; }

@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.4 } }
</style>
