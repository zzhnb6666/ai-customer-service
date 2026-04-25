from pathlib import Path
from app.rag.vectorstore import search_similar, QDRANT_AVAILABLE


async def retrieve_knowledge(query: str, top_k: int = 3) -> str:
    """RAG 检索：根据用户问题找出相关知识片段"""
    if QDRANT_AVAILABLE:
        results = await search_similar(query, top_k=top_k)
        if results:
            return "\n---\n".join(results)

    # Fallback: simple file-based keyword search
    return _local_search(query, top_k)


def _local_search(query: str, top_k: int = 3) -> str:
    """本地文件关键词搜索（无需 Qdrant）"""
    upload_dir = Path("uploads")
    if not upload_dir.exists():
        return ""

    keywords = query.lower().split()
    matches = []

    for file_path in upload_dir.iterdir():
        if file_path.suffix.lower() not in [".txt", ".md"]:
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            # Simple relevance: count keyword matches
            score = sum(
                content.lower().count(kw) for kw in keywords if len(kw) >= 2
            )
            if score > 0:
                # Extract relevant paragraphs
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                for para in paragraphs:
                    para_score = sum(
                        para.lower().count(kw) for kw in keywords if len(kw) >= 2
                    )
                    if para_score > 0:
                        matches.append((para_score, para[:500], file_path.name))
        except Exception:
            pass

    # Sort by score, deduplicate, take top_k
    matches.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    results = []
    for score, text, source in matches:
        if text not in seen:
            seen.add(text)
            results.append(text)
            if len(results) >= top_k:
                break

    return "\n---\n".join(results) if results else ""
