"""记忆管理 API（require_admin）：列表 / 手动添加 / 启停 / 遗忘。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import agent.auth
from memory import store, vector

router = APIRouter(
    prefix="/api/memory", tags=["memory"],
    dependencies=[Depends(agent.auth.require_admin)],  # 管理端点统一鉴权
)


class MemoryCreate(BaseModel):
    content: str


class MemoryEnabled(BaseModel):
    enabled: bool


@router.get("")
async def list_memories(user_id: str | None = None, enabled: bool | None = None):
    return {"memories": await store.list_memories(user_id=user_id, enabled=enabled)}


@router.post("")
async def create_memory(body: MemoryCreate, user: dict = Depends(agent.auth.require_admin)):
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    entry = await store.add_memory(user["id"], content, source_thread="manual")
    vector.upsert_memory(entry)
    return {"memory": entry}


@router.put("/{memory_id}/enabled")
async def set_memory_enabled(memory_id: str, body: MemoryEnabled):
    m = await store.set_enabled(memory_id, body.enabled)
    if not m:
        raise HTTPException(status_code=404, detail="记忆不存在")
    vector.update_enabled(memory_id, body.enabled)
    return {"memory": m}


@router.delete("/{memory_id}")
async def forget_memory(memory_id: str):
    ok = await store.forget_memory(memory_id)
    vector.delete_points(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"status": "forgotten", "id": memory_id}
