/* Markdown 渲染：基于 marked，支持表格、代码块、列表、引用等 GFM 语法 */

import { marked } from 'marked'

marked.setOptions({
  gfm: true,      // 表格等 GitHub 风格语法
  breaks: true    // 单个换行符转 <br>，符合聊天场景
})

export function renderMarkdown(src) {
  if (!src) return ''
  return marked.parse(src)
}
