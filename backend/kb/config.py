"""知识库模块配置与公共工具。"""

import os
import re

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
# 本地嵌入式模式（默认开启，免 Docker 即可开发自测）。
# 设为空字符串可改用上面的 QDRANT_URL（指向 Docker / 云 Qdrant）。
QDRANT_LOCAL_PATH = os.getenv("QDRANT_LOCAL_PATH", "./qdrant_data")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

# 稀疏向量模型（BM25）。中文效果有限时可换成 Qdrant/bm25-zh
SPARSE_MODEL = os.getenv("SPARSE_MODEL", "Qdrant/bm25")

# 单文件大小上限：几 MB 到 10MB
MAX_FILE_BYTES = 10 * 1024 * 1024

DENSE_NAME = "dense"
SPARSE_NAME = "bm25"

KB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_kb_id(kb_id: str) -> str:
    """校验 kb_id，非法则抛 ValueError。"""
    if not isinstance(kb_id, str) or not KB_ID_PATTERN.match(kb_id):
        raise ValueError(
            "kb_id 仅允许字母、数字、-、_，长度 1-64；当前值不合法。"
        )
    return kb_id


def collection_name(kb_id: str) -> str:
    """每知识库一个 collection 的命名规则（硬隔离）。"""
    return f"kb_{validate_kb_id(kb_id)}"
