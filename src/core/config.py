import os
from pathlib import Path

TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3005",
    "http://127.0.0.1:3005",
    "http://localhost:3010",
    "http://127.0.0.1:3010",
    "http://localhost:3015",
    "http://127.0.0.1:3015",
]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def _env_csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(default)


def _resolve_cors_allowed_origins(*, allow_credentials: bool) -> list[str]:
    origins = _env_csv("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ALLOWED_ORIGINS)
    if allow_credentials:
        origins = [origin for origin in origins if origin != "*"]
    return origins or list(DEFAULT_CORS_ALLOWED_ORIGINS)


def _resolve_session_cookie_samesite() -> str:
    value = os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    if value not in {"lax", "strict", "none"}:
        return "lax"
    return value


# Base paths — src/ is the project root
BASE_DIR = Path(__file__).parent.parent  # = .../cvg-master-rag/src
DATA_DIR = BASE_DIR / "data"
# ── Corpus paths ──────────────────────────────────────────────────────────────
# CANONICAL corpus (ingestão/consulta ativa): src/data/documents/default/
# LEGACY (arquivado): src/data/documents-ARCHIVED/default/
# `src/data/default` contém os arquivos de suporte operacional da fase (dataset, markdown)
DOCUMENTS_DIR = DATA_DIR / "documents"
CHUNKS_DIR = DATA_DIR / "chunks"
LOGS_DIR = BASE_DIR / "logs"
DATASETS_DIR = DATA_DIR / "datasets"

# Ensure directories exist
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Qdrant config
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "rag_phase0")
QDRANT_CHECK_COMPATIBILITY = _env_bool("QDRANT_CHECK_COMPATIBILITY", False)

# OpenAI config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    os.getenv("EMBEDDING_EMBEDDING_MODEL", "text-embedding-3-small"),
)
EMBEDDING_DIM = 1536
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# CORS config
CORS_ALLOW_CREDENTIALS = _env_bool("CORS_ALLOW_CREDENTIALS", True)
CORS_ALLOWED_ORIGINS = _resolve_cors_allowed_origins(allow_credentials=CORS_ALLOW_CREDENTIALS)

# Session config
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "8"))
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
SESSION_COOKIE_SAMESITE = _resolve_session_cookie_samesite()

# Chunking config
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "240"))

# Future persistence scale triggers.
# The 400MB release intentionally keeps a single atomic *_chunks.json file.
# If either threshold is reached, the next scaling task must migrate chunks to
# JSONL shards before raising upload limits further.
CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT = int(os.getenv("CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT", "100000"))
CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES = int(os.getenv("CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES", "524288000"))

# Retrieval config
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
DEFAULT_THRESHOLD = float(os.getenv("DEFAULT_THRESHOLD", "0.25"))

# RRF k parameter
RRF_K = 60

# Reranking config
RERANKING_ENABLED = _env_bool("RERANKING_ENABLED", True)
RERANKING_METHOD = os.getenv("RERANKING_METHOD", "bm25f")  # "bm25f", "neural", or "none"

# Query expansion config (HyDE-like)
QUERY_EXPANSION_ENABLED = _env_bool("QUERY_EXPANSION_ENABLED", False)

# External chat integration
EXTERNAL_CHAT_API_KEY = os.getenv("EXTERNAL_CHAT_API_KEY", "")

# Supported formats
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
SUPPORTED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}
