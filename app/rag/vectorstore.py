from app.config import settings

COLLECTION_NAME = "product_knowledge"

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    client = QdrantClient(url=settings.qdrant_url)
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    client = None


def _check_available():
    if not QDRANT_AVAILABLE:
        raise RuntimeError("Qdrant not available (install qdrant-client or use Docker)")


def ensure_collection():
    _check_available()
    collections = client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """使用 DeepSeek API 生成文本向量 (1024维)"""
    from openai import OpenAI
    sync_client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    resp = sync_client.embeddings.create(
        model="deepseek-embedding-v3",
        input=texts,
    )
    return [d.embedding for d in resp.data]


async def index_documents(chunks, progress_callback=None):
    """将文档块向量化并存入 Qdrant"""
    _check_available()
    ensure_collection()

    try:
        client.delete_collection(COLLECTION_NAME)
        ensure_collection()
    except Exception:
        pass

    batch_size = 32
    total = len(chunks)
    texts = [chunk.page_content for chunk in chunks]

    points = []
    for i in range(0, total, batch_size):
        batch_texts = texts[i:i + batch_size]
        try:
            embeddings = await embed_texts(batch_texts)
        except Exception:
            embeddings = [[0.0] * 1024 for _ in batch_texts]

        for j, (chunk, emb) in enumerate(zip(chunks[i:i + batch_size], embeddings)):
            points.append(PointStruct(
                id=i + j + 1,
                vector=emb,
                payload={
                    "text": chunk.page_content,
                    "source": chunk.metadata.get("source", ""),
                }
            ))

        if progress_callback:
            progress_callback(min((i + batch_size) / total, 1.0))

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    return total


async def search_similar(query: str, top_k: int = 5) -> list[str]:
    """检索与查询最相关的文档片段"""
    if not QDRANT_AVAILABLE:
        return []
    try:
        embeddings = await embed_texts([query])
    except Exception:
        return []

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=embeddings[0],
        limit=top_k,
    )
    return [r.payload["text"] for r in results]
