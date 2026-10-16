# Bug：聊天页 Agent 选择下拉出现乱码

## 现象
对话窗口选择 Agent 的 select 显示 `Ã©Â»Â¤Ã¨Â®Â¤ DeepAgent`（应为「默认 DeepAgent」）。

## 复现
登录后打开聊天页，或直接 `GET /api/agents`，返回的 `name` 为乱码。

## 诊断
- 源码常量正常：`config_store.DEFAULT_CONFIG["name"]`、`deep_agent.SYSTEM_PROMPT` 在 venv Python 下读取均为正确中文。
- DB 损坏：`data/agent_sessions.db` 的 `agent_config` 表 default 行 `name` 与 `system_prompt` 均为 UTF-8 双重编码（mojibake），`updated_at=2026-10-16T07:38:52Z`。
- 其他表（roles/departments/users）中文正常 → 非 seed/源码/存储层问题。
- 根因：当日 MCP 后台热重建测试用 PowerShell/curl 以 PUT /api/admin/agents 整体回写配置，请求体中文被客户端双重编码，后端如实存入了乱码字符串。属**数据损坏**（操作侧编码问题），非代码缺陷；乱码 system_prompt 还会影响默认 Agent 行为。

## 修复
1. 一次性脚本将 default 行 name/system_prompt 回写为源码正确值（UPDATE agent_config）。
2. 重启后端使 AGENT 用修复后的 system_prompt 重建。
3. 回归测试 `backend/tests/test_agent_config_seed_encoding.py`：空库 seed 后中文与源码常量一致（钉住 seed 编码正确性）。

## 验证
- `GET /api/agents` 返回「默认 DeepAgent」；聊天页下拉正常。

## 教训
- 用 PowerShell/curl 回写含中文的 JSON 配置时，优先 `--data @utf8_file`（UTF-8 无 BOM），避免内联字符串经 PowerShell 编码转换。
