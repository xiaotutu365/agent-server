"""知识库全局配置（可被后台 UI 覆盖，持久化到 data/kb_settings.json）。

默认值来自环境变量（见 kb.config），可在后台「知识库配置」页修改并持久化。
embed / ingest / retrieval / store 在调用时读取本模块，从而实现运行时可调。

注意：嵌入模型与向量维度在建库时即写死进 Qdrant 集合 schema，
修改后仅对新创建的知识库生效；已有集合需用原模型检索，或删除重建。
"""

import json
import os

import kb.config as cfg

# 持久化文件路径：backend/data/kb_settings.json
_SETTINGS_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "kb_settings.json")
)

# 可选文档类型（UI 多选的来源，不限于默认启用项）
ALL_DOC_TYPES = [
    ".txt", ".md", ".pdf", ".docx", ".csv", ".jsonl",
    ".html", ".json", ".pptx", ".xlsx",
]

DEFAULTS = {
    # 文档与分块
    "supported_ext": [".txt", ".md", ".pdf", ".docx", ".csv", ".jsonl"],
    "chunk_size": 800,
    "chunk_overlap": 100,
    "max_file_mb": 10,
    # 嵌入模型（dense：OpenAI 兼容）
    "embedding_base_url": cfg.EMBEDDING_BASE_URL,
    "embedding_model": cfg.EMBEDDING_MODEL,
    "embedding_api_key": cfg.EMBEDDING_API_KEY,
    "embedding_dim": cfg.EMBEDDING_DIM,
    # 稀疏向量（BM25）
    "sparse_model": cfg.SPARSE_MODEL,
    # 检索
    "top_k": 5,
    "candidate": 20,
    "rrf_k": 60,
}

_settings = None


def _load() -> dict:
    global _settings
    data = dict(DEFAULTS)
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            for k, v in overrides.items():
                if k in DEFAULTS:
                    data[k] = v
        except Exception:  # noqa: BLE001
            pass
    _settings = data
    return _settings


def get_settings() -> dict:
    global _settings
    if _settings is None:
        _settings = _load()
    return _settings


def save_settings(patch: dict) -> dict:
    """合并并持久化配置；随后重置嵌入客户端缓存以应用新配置。"""
    s = get_settings()
    for k, v in patch.items():
        if k in DEFAULTS:
            s[k] = v
    os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({k: s[k] for k in DEFAULTS}, f, ensure_ascii=False, indent=2)
    try:
        import kb.embed as embed

        embed.reset_clients()
    except Exception:  # noqa: BLE001
        pass
    return s


def max_file_bytes() -> int:
    return int(get_settings()["max_file_mb"]) * 1024 * 1024


def supported_ext_set() -> tuple:
    return tuple(get_settings()["supported_ext"])
