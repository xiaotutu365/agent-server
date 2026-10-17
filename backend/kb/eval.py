"""知识库检索评测：评测集文件管理 + Recall@k/MRR 自算 + Ragas context 指标双轨。

评测集：data/kb_eval_<kb_id>.json，条目 [{"query", "expected_files", "reference"?}]。
- expected_files（必填，文件级标注）驱动自算指标 Recall@k / MRR；
- reference（可选，期望片段原文或参考答案）解锁 Ragas context_precision / context_recall
  （LLM-as-judge，用 model_store 默认 chat 模型；不可用时优雅降级为只跑自算）。

设计依据：docs/adr/ADR-002-ragas-eval.md。
"""

import asyncio
import json
import os

import kb.settings as settings
from kb import retrieval

_EVAL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

# 示例评测集模板：GET 无文件时返回，供用户照着补充标注
EVAL_TEMPLATE = [
    {"query": "公司的退货政策是什么？", "expected_files": ["policy.md"],
     "reference": "商品支持 7 天无理由退货，需保持包装完好。"},
    {"query": "运费怎么计算？", "expected_files": ["policy.md"]},
    {"query": "产品 X 如何安装？", "expected_files": ["manual.md"]},
    {"query": "API 的调用频率限制是多少？", "expected_files": ["api.md"],
     "reference": "默认每分钟最多 60 次调用。"},
    {"query": "售后服务的时间是几点到几点？", "expected_files": ["policy.md"]},
]


def evalset_path(kb_id: str) -> str:
    return os.path.join(_EVAL_DIR, f"kb_eval_{kb_id}.json")


def load_evalset(kb_id: str) -> dict:
    """返回 {"items": [...], "template": bool}；文件不存在/损坏时回退到示例模板。"""
    path = evalset_path(kb_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                return {"items": items, "template": False}
        except Exception:  # noqa: BLE001
            pass
    return {"items": [dict(x) for x in EVAL_TEMPLATE], "template": True}


def save_evalset(kb_id: str, items: list) -> list:
    """校验并持久化评测集，返回清洗后的条目。"""
    if not isinstance(items, list) or not items:
        raise ValueError("评测集必须是非空数组")
    cleaned = []
    for it in items:
        if not isinstance(it, dict) or not str(it.get("query", "")).strip():
            raise ValueError("每条评测必须有非空的 query")
        ef = it.get("expected_files")
        if not isinstance(ef, list) or not ef or not all(
            isinstance(x, str) and x.strip() for x in ef
        ):
            raise ValueError(f"条目 {str(it.get('query'))!r} 的 expected_files 必须是非空字符串数组")
        entry = {"query": str(it["query"]).strip(), "expected_files": [x.strip() for x in ef]}
        ref = str(it.get("reference") or "").strip()
        if ref:
            entry["reference"] = ref
        cleaned.append(entry)
    os.makedirs(_EVAL_DIR, exist_ok=True)
    with open(evalset_path(kb_id), "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    return cleaned


def compute_recall_mrr(hits: list, expected_files: list) -> tuple:
    """按 source 文件级匹配。返回 (recall@k, 首个期望文件排名的倒数；未命中为 0)。"""
    expected = set(expected_files)
    got = {h.get("source") for h in hits if h.get("source")}
    recall = len(expected & got) / len(expected) if expected else 0.0
    rr = 0.0
    for rank, h in enumerate(hits, start=1):
        if h.get("source") in expected:
            rr = 1.0 / rank
            break
    return recall, rr


def _judge_llm():
    """用 model_store 默认 chat 模型构造 Ragas judge LLM；不可用返回 None。"""
    try:
        from agent.model_store import get_default_sync

        m = get_default_sync("chat") or {}
        if not (m.get("api_key") and m.get("base_url") and m.get("model")):
            return None
        from langchain_openai import ChatOpenAI
        from ragas.llms import LangchainLLMWrapper

        return LangchainLLMWrapper(ChatOpenAI(
            model=m["model"], api_key=m["api_key"], base_url=m["base_url"], temperature=0,
        ))
    except Exception:  # noqa: BLE001
        return None


def _ragas_scores(samples: list, llm) -> dict:
    """跑 Ragas context 指标并聚合均值。samples 为 dict 形态，内部转 SingleTurnSample。"""
    from ragas import evaluate
    from ragas.metrics import context_precision, context_recall
    from ragas import SingleTurnSample

    st = [SingleTurnSample(
        user_input=s["query"],
        retrieved_contexts=s["retrieved_contexts"],
        reference=s["reference"],
    ) for s in samples]
    result = evaluate(samples=st, metrics=[context_precision, context_recall], llm=llm)
    df = result.to_pandas()
    out = {}
    for col in ("context_precision", "context_recall"):
        if col in df.columns:
            vals = df[col].dropna()
            if len(vals):
                out[col] = float(vals.mean())
    return out


async def run_eval(kb_id: str, top_k: int | None = None) -> dict:
    """运行评测：自算指标始终可用；Ragas 指标仅在 judge LLM 可用时计算。"""
    k = int(top_k or settings.get_settings().get("top_k", 5))
    es = load_evalset(kb_id)

    items_out, recalls, rrs, ragas_pool = [], [], [], []
    for it in es["items"]:
        docs = retrieval.hybrid_search(kb_id, it["query"], top_k=k) or []
        expected = set(it["expected_files"])
        hits = [{
            "text": d.page_content,
            "source": (d.metadata or {}).get("source", ""),
            "chunk_idx": (d.metadata or {}).get("chunk_idx", 0),
            "score": (d.metadata or {}).get("score"),
        } for d in docs]
        for h in hits:
            h["hit"] = h["source"] in expected
        recall, rr = compute_recall_mrr(hits, it["expected_files"])
        recalls.append(recall)
        rrs.append(rr)
        entry = {
            "query": it["query"],
            "expected_files": it["expected_files"],
            "recall_at_k": recall,
            "reciprocal_rank": rr,
            "hits": hits,
        }
        if it.get("reference"):
            ragas_pool.append({
                "query": it["query"],
                "retrieved_contexts": [h["text"] for h in hits],
                "reference": it["reference"],
            })
        items_out.append(entry)

    n = len(recalls)
    summary = {
        "recall_at_k": sum(recalls) / n if n else 0.0,
        "mrr": sum(rrs) / n if n else 0.0,
        "ragas_available": False,
    }
    if ragas_pool:
        llm = _judge_llm()
        if llm is None:
            summary["ragas_error"] = "Ragas 或 judge LLM 不可用（需安装 ragas 包，并在模型管理中配置默认 chat 模型）"
        else:
            try:
                scores = await asyncio.to_thread(_ragas_scores, ragas_pool, llm)
                summary.update(scores)
                summary["ragas_available"] = bool(scores)
                if not scores:
                    summary["ragas_error"] = "Ragas 未返回有效得分"
            except Exception as exc:  # noqa: BLE001
                summary["ragas_error"] = f"{type(exc).__name__}: {exc}"
    return {"items": items_out, "summary": summary}
