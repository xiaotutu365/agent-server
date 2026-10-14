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

    <section class="config">
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
        <button
          v-if="task && task.status === 'need-adjust'"
          class="primary"
          :disabled="streaming"
          @click="adjustAndRerun"
        >↻ 调整脚本并重跑</button>
        <button class="ghost" :disabled="streaming" @click="reset">重置</button>
      </div>
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

    <section class="pipeline">
      <div class="stage" :class="stageClass('script')">
        <div class="stage-head"><span class="dot"></span>① 脚本创建 Agent</div>
        <div class="stage-desc">生成综合 Tcl / SDC 脚本</div>
        <pre v-if="task && task.script" class="stage-out">{{ clip(task.script) }}</pre>
      </div>
      <div class="arrow">→</div>
      <div class="stage" :class="stageClass('run')">
        <div class="stage-head"><span class="dot"></span>② 调度运行 Agent</div>
        <div class="stage-desc">模拟提交综合并产出日志 / 报告</div>
        <pre v-if="task && task.runLog" class="stage-out">{{ clip(task.runLog) }}</pre>
      </div>
      <div class="arrow">→</div>
      <div class="stage" :class="stageClass('report')">
        <div class="stage-head"><span class="dot"></span>③ 报告分析 Agent</div>
        <div class="stage-desc">解析 WNS、判定并给建议</div>
        <pre v-if="task && task.analysis" class="stage-out">{{ clip(task.analysis) }}</pre>
      </div>
    </section>

    <section v-if="task" class="details">
      <details><summary>综合脚本全文</summary><pre>{{ task.script }}</pre></details>
      <details><summary>调度运行日志 / 报告</summary><pre>{{ task.report }}</pre></details>
      <details><summary>时序分析报告</summary><pre>{{ task.analysis }}</pre></details>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { streamChat } from '../api/chat'

const SCRIPT_PROMPT = `你是一名资深的数字芯片逻辑综合（RTL Synthesis）工程师，使用 Synopsys Design Compiler 风格的 Tcl/SDC 脚本。根据用户给出的设计需求（含目标时钟周期与额外约束），生成一份完整、可执行的综合脚本：读入 RTL、设置时钟 create_clock、IO 与面积/时序约束、编译/映射/优化策略，并在末尾用注释说明关键约束。只输出脚本与必要的中文说明，不要闲聊。`
const RUN_PROMPT = `你是一名 EDA 流程调度工程师，负责把综合脚本提交到综合服务器并模拟运行。基于用户提供的综合脚本，输出模拟的综合运行日志（步骤：读库→读RTL→编译→映射→优化→写出）与一份模拟的综合报告摘要（面积、时序、各阶段耗时）。注意：真实 WNS 数值由外部注入，你只需描述运行过程与日志，不要编造 WNS 数值。`
const REPORT_PROMPT = `你是一名时序签核（STA）与综合报告分析专家。用户会提供综合运行日志/报告以及关键指标 WNS（最差负裕量，单位 ns）。请解析内容、判断 WNS 是否满足约束（要求 WNS ≥ 0），并给出明确结论（满足 / 不满足）以及若不满足的具体脚本调整建议（如调整时钟周期、增加优化努力、修改约束等）。输出结构化的中文结论。`

const form = reactive({ design: '', pdk: '28nm', targetPeriod: 10, constraint: '' })
const streaming = ref(false)
const task = ref(null)
const stageStatus = reactive({ script: 'idle', run: 'idle', report: 'idle' })
const lastSuggestion = ref('')

function genId() { return 'eda-' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4) }
function clip(t) { return t && t.length > 400 ? t.slice(0, 400) + '\n…（详见下方全文）' : (t || '') }

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
  stageStatus.script = 'running'
  task.value.script = ''
  task.value.script = await runAgentStage(
    SCRIPT_PROMPT, `eda-${task.value.id}-s${iter}-script`, buildScriptMessage(iter),
    (t) => { task.value.script = t },
  )
  stageStatus.script = 'done'

  // ② 调度运行 Agent（模拟）
  stageStatus.run = 'running'
  task.value.runLog = ''
  const runMsg = `综合脚本如下：\n\n${task.value.script}\n\n请模拟提交到综合服务器执行，输出运行日志与综合报告摘要。`
  task.value.runLog = await runAgentStage(
    RUN_PROMPT, `eda-${task.value.id}-s${iter}-run`, runMsg,
    (t) => { task.value.runLog = t },
  )
  stageStatus.run = 'done'

  // 计算 WNS（内置模拟）并组装报告
  const wns = computeWNS(form.pdk, iter)
  task.value.wns = wns
  task.value.report = `${task.value.runLog}\n\n[模拟综合报告] WNS = ${wns} ns（约束要求 WNS ≥ 0 ns）`

  // ③ 报告分析 Agent
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
  runStage(0)
}

function adjustAndRerun() {
  if (streaming.value || !task.value) return
  lastSuggestion.value = task.value.analysis
  runStage(task.value.iteration + 1)
}

function reset() {
  if (streaming.value) return
  task.value = null
  stageStatus.script = stageStatus.run = stageStatus.report = 'idle'
  lastSuggestion.value = ''
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
.ov-card.ok { border-color: #22a06b; }
.ov-card.ok .ov-val, .ov-card.ok .ov-sub { color: #22a06b; }
.ov-card.bad { border-color: #d93025; }
.ov-card.bad .ov-val, .ov-card.bad .ov-sub { color: #d93025; }

.pipeline { display: flex; align-items: stretch; gap: 10px; flex-wrap: wrap; }
.stage {
  flex: 1 1 240px; border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; background: var(--panel); display: flex; flex-direction: column; gap: 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.stage.on { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(79,110,247,0.15); }
.stage.done { border-color: var(--border); }
.stage-head { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: var(--text); }
.dot { width: 9px; height: 9px; border-radius: 50%; background: var(--border); flex: none; }
.stage.on .dot { background: var(--accent); animation: pulse 1s infinite; }
.stage.done .dot { background: #22a06b; }
.stage-desc { font-size: 12px; color: var(--muted); }
.stage-out {
  background: var(--code-bg); border-radius: 8px; padding: 10px; font-size: 12px;
  line-height: 1.5; max-height: 160px; overflow: auto; white-space: pre-wrap; word-break: break-word;
}
.arrow { align-self: center; color: var(--muted); font-size: 20px; flex: none; }

.details { display: flex; flex-direction: column; gap: 8px; }
.details details {
  border: 1px solid var(--border); border-radius: 10px; background: var(--panel); padding: 8px 12px;
}
.details summary { cursor: pointer; font-size: 13px; color: var(--text); font-weight: 600; }
.details pre {
  background: var(--code-bg); border-radius: 8px; padding: 12px; margin-top: 8px;
  font-size: 12px; line-height: 1.5; max-height: 320px; overflow: auto; white-space: pre-wrap; word-break: break-word;
}

@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.4 } }
</style>
