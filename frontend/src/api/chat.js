import { apiFetch } from '../auth'

/** SSE 流式聊天客户端：POST /api/chat/stream，解析 event/data 帧。
 *  @param {string} message   普通消息内容（恢复中断时可为空）
 *  @param {string} threadId  会话 id
 *  @param {object} handlers  事件回调
 *  @param {AbortSignal} signal
 *  @param {object|null} resume  HITL 恢复决策（HITLResponse），非空时作为恢复请求
 *  @param {string|null} modelId 会话级模型选择（SPEC-session-model-select）：
 *         传字符串时始终携带（''=跟随全局默认）；null 不携带（老行为）
 */
export async function streamChat(message, threadId, handlers, signal, resume = null, systemPrompt = null, agentId = null, modelId = null) {
  const body = resume
    ? { resume, thread_id: threadId }
    : { message, thread_id: threadId }
  if (systemPrompt) body.system_prompt = systemPrompt
  if (agentId) body.agent_id = agentId
  if (modelId !== null) body.model_id = modelId
  const resp = await apiFetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal
  })

  if (!resp.ok || !resp.body) {
    throw new Error(`请求失败: HTTP ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const dispatch = (event, dataStr) => {
    let data = {}
    try { data = JSON.parse(dataStr) } catch { return }
    switch (event) {
      case 'token': handlers.onToken?.(data.content); break
      case 'tool_start': handlers.onToolStart?.(data); break
      case 'tool_end': handlers.onToolEnd?.(data); break
      case 'plan': handlers.onPlan?.(data); break
      case 'interrupt': handlers.onInterrupt?.(data); break
      case 'error': handlers.onError?.(data.message); break
      case 'done': handlers.onDone?.(); break
    }
  }

  // SSE 帧以空行分隔；每帧内含 event: 与 data: 行
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      const dataLines = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length) dispatch(event, dataLines.join('\n'))
    }
  }
}
