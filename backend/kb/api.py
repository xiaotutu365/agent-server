"""知识库管理 API：创建/列出/删除知识库、上传文档、检索。挂载到 FastAPI app。"""

import os
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

import kb.config as cfg
from kb import store, ingest, retrieval, tasks
import kb.embed as embed
import kb.settings as settings
from kb import eval as kb_eval

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class CreateKbReq(BaseModel):
    kb_id: str
    description: str = ""


class SearchReq(BaseModel):
    query: str
    top_k: int = 5
    candidate: int | None = None
    rrf_k: int | None = None


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

CHUNK_STRATEGY_OPTIONS = [
    {"value": "fixed", "label": "固定长度+重叠", "desc": "通用切分，按字数窗口滑动（默认）"},
    {"value": "markdown", "label": "按段落/标题", "desc": "按 Markdown 标题层级切，保语义完整"},
    {"value": "blank_line", "label": "按空行分段", "desc": "空行分条不合并，适合 FAQ/问答对"},
]


@router.get("/settings")
def get_kb_settings():
    data = settings.get_settings()
    data["chunk_strategies"] = CHUNK_STRATEGY_OPTIONS
    return data


@router.put("/settings")
def update_kb_settings(patch: dict):
    """合并并持久化知识库配置；写入后嵌入客户端缓存会被重置以应用新配置。"""
    try:
        return settings.save_settings(patch or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- 入库任务查询（SPEC-kb-ocr-ingest C2；注册在 /{kb_id} 路由之前） ----------

@router.get("/ingest-tasks/{task_id}")
def get_ingest_task(task_id: str):
    task = tasks.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="入库任务不存在。")
    return task


@router.get("/{kb_id}/ingest-tasks")
def list_ingest_tasks(kb_id: str, active: bool = True):
    _kb_guard(kb_id)
    if active:
        return {"tasks": tasks.list_active(kb_id)}
    return {"tasks": tasks.list_tasks(kb_id)}


@router.delete("/{kb_id}")
def delete_kb(kb_id: str):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return store.drop_kb(kb_id)


@router.get("/{kb_id}/documents")
def list_documents(kb_id: str):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    docs = store.list_documents(kb_id)
    if docs is None:
        raise HTTPException(status_code=404, detail="知识库不存在。")
    return {"documents": docs}


@router.delete("/{kb_id}/documents")
def delete_document(kb_id: str, file: str):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    r = store.delete_document(kb_id, file)
    if r["status"] == "not_found":
        raise HTTPException(status_code=404, detail="知识库或文档不存在。")
    return r


@router.post("/{kb_id}/documents", status_code=202)
async def upload_documents(kb_id: str, file: UploadFile = File(...)):
    """上传 → 留档 → 建入库任务，立即返回 202（OCR/向量化在后台任务执行）。"""
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
    archived = ""
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        store.create_kb(kb_id)  # kb 不存在时隐式建库（沿用现状）
        archived = ingest.archive_file(kb_id, file.filename or "", tmppath)
        # worker 异步读取，落点优先用留档（临时文件才可安全删除）；留档失败退回临时文件并保留
        task_id = tasks.start_ingest_task(
            kb_id, file.filename or "", "upload", archived or tmppath
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"入库任务创建失败: {exc}")
    finally:
        if archived and os.path.exists(tmppath):
            os.remove(tmppath)
    return {"task_id": task_id, "kb_id": kb_id, "file": file.filename}


@router.post("/{kb_id}/documents/reingest", status_code=202)
def reingest_document(kb_id: str, file: str):
    """按当前分片策略重建单个文档：建任务立即返回 202，删旧建新在 worker 成功后执行。"""
    _kb_guard(kb_id)
    dest = ingest.archive_path(kb_id, file or "")
    if not dest or not os.path.isfile(dest):
        raise HTTPException(
            status_code=404,
            detail="该文档没有留档原文件（仅支持留档后上传的文档），请删除后重新上传一次以建立留档。",
        )
    try:
        task_id = tasks.start_ingest_task(kb_id, file, "reingest", dest)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"重新入库任务创建失败: {exc}")
    return {"task_id": task_id, "kb_id": kb_id, "file": file}


@router.get("/{kb_id}/chunk")
def get_chunk(kb_id: str, source: str, chunk_idx: int = 0):
    """按 (source, chunk_idx) 取片段原文，供对话引用 badge 点击查看。"""
    _kb_guard(kb_id)
    chunk = store.get_chunk(kb_id, source, chunk_idx)
    if chunk is None:
        raise HTTPException(status_code=404, detail="知识库或片段不存在。")
    return chunk


@router.get("/{kb_id}/chunks")
def list_chunks(kb_id: str, source: str):
    """分片预览：按 chunk_idx 升序列出某文档全部片段原文。"""
    _kb_guard(kb_id)
    chunks = store.list_chunks(kb_id, source)
    if chunks is None:
        raise HTTPException(status_code=404, detail="知识库不存在。")
    return {"kb_id": kb_id, "source": source, "total": len(chunks), "chunks": chunks}


@router.post("/{kb_id}/search")
def search(kb_id: str, req: SearchReq):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        docs, fallback = retrieval.hybrid_search_ex(kb_id, req.query, top_k=req.top_k, candidate=req.candidate, rrf_k=req.rrf_k)
    except embed.EmbeddingUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检索失败: {exc}")
    return {
        "kb_id": kb_id,
        "fallback": fallback or None,  # 降级原因（即使零结果也提示）
        "results": [
            {"content": d.page_content, "metadata": d.metadata} for d in docs
        ],
    }


# ---------- 检索评测（spec 能力 L6） ----------

class EvalRunReq(BaseModel):
    top_k: int | None = None


def _kb_guard(kb_id: str):
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{kb_id}/evalset")
def get_evalset(kb_id: str):
    _kb_guard(kb_id)
    return kb_eval.load_evalset(kb_id)


@router.put("/{kb_id}/evalset")
def put_evalset(kb_id: str, body: dict):
    _kb_guard(kb_id)
    items = body.get("items") if isinstance(body, dict) else None
    try:
        return {"items": kb_eval.save_evalset(kb_id, items)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{kb_id}/eval/run")
async def run_eval(kb_id: str, req: EvalRunReq):
    _kb_guard(kb_id)
    try:
        return await kb_eval.run_eval(kb_id, top_k=req.top_k)
    except embed.EmbeddingUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"评测失败: {exc}")
