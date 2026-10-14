"""知识库管理 API：创建/列出/删除知识库、上传文档、检索。挂载到 FastAPI app。"""

import os
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

import kb.config as cfg
from kb import store, ingest, retrieval
import kb.embed as embed
import kb.settings as settings

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class CreateKbReq(BaseModel):
    kb_id: str
    description: str = ""


class SearchReq(BaseModel):
    query: str
    top_k: int = 5


@router.post("")
def create_kb(req: CreateKbReq):
    try:
        cfg.validate_kb_id(req.kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return store.create_kb(req.kb_id, req.description)


@router.get("")
def list_kbs():
    return {"kbs": store.list_kbs()}


# ---------- 知识库全局配置（后台 UI 可覆盖，持久化到 data/kb_settings.json） ----------

@router.get("/settings")
def get_kb_settings():
    return settings.get_settings()


@router.put("/settings")
def update_kb_settings(patch: dict):
    """合并并持久化知识库配置；写入后嵌入客户端缓存会被重置以应用新配置。"""
    return settings.save_settings(patch or {})


@router.delete("/{kb_id}")
def delete_kb(kb_id: str):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return store.drop_kb(kb_id)


@router.post("/{kb_id}/documents")
async def upload_documents(kb_id: str, file: UploadFile = File(...)):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if file.size and file.size > settings.max_file_bytes():
        raise HTTPException(status_code=413, detail="文件超过大小上限。")

    data = await file.read()
    if len(data) > settings.max_file_bytes():
        raise HTTPException(status_code=413, detail="文件超过大小上限。")

    suffix = os.path.splitext(file.filename or "")[1] or ".txt"
    fd, tmppath = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        store.create_kb(kb_id)
        chunks = ingest.ingest_file(kb_id, tmppath)
    except embed.EmbeddingUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"入库失败: {exc}")
    finally:
        if os.path.exists(tmppath):
            os.remove(tmppath)
    return {"kb_id": kb_id, "file": file.filename, "chunks": chunks}


@router.post("/{kb_id}/search")
def search(kb_id: str, req: SearchReq):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        docs = retrieval.hybrid_search(kb_id, req.query, top_k=req.top_k)
    except embed.EmbeddingUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检索失败: {exc}")
    return {
        "kb_id": kb_id,
        "results": [
            {"content": d.page_content, "metadata": d.metadata} for d in docs
        ],
    }
