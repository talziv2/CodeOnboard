from functools import lru_cache

from sentence_transformers import SentenceTransformer


MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
BATCH_SIZE = 32


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, trust_remote_code=True)


def embed_documents(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    prefixed = [DOCUMENT_PREFIX + t for t in texts]
    vectors = model.encode(
        prefixed,
        normalize_embeddings=True,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    model = _get_model()
    vectors = model.encode(
        [QUERY_PREFIX + text],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors[0].tolist()
