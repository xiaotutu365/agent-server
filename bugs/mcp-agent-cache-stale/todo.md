# 修复清单：mcp-agent-cache-stale

- [x] 复现：读取用户浏览器线程历史（xa9zl1wcmvamuhjg：echo 成功、crm_ping 被回复不存在）
- [x] 定位：对照实验区分两条路径 — 全局 AGENT（crm_ping ✅）vs AGENT_CACHE["agent:default"]（crm_ping ❌）
- [x] 根因确认：PUT / set-default / delete 三处热重建只重建全局 AGENT，不清 AGENT_CACHE；UI 聊天恒带 agent_id 走缓存
- [x] 回归测试（red）：tests/test_agent_cache_invalidation.py — 3 个失效用例失败、基线用例通过
- [x] 修复：main.py 三处端点加 AGENT_CACHE 清理（PUT/set-default 全清，delete 清对应条目）
- [x] 回归测试（green）：test_agent_cache_invalidation.py + test_mcp_gate.py 共 5 passed
- [x] 重启后端加载修复；端到端验证 UI 路径 echo / crm_ping 均正常
- [x] 还原测试数据基线：test-suite 的 allow_roles 恢复为空（场景 C 遗留未还原）
