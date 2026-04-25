import json
from pathlib import Path
from app.config import settings
from app.db.redis import get_redis

# Local file storage
DATA_DIR = Path("data/conversations")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _file_path(user_id: str) -> Path:
    safe_id = user_id.replace("/", "_").replace("\\", "_")
    return DATA_DIR / f"{safe_id}.json"


async def _get_redis():
    return await get_redis()


async def get_history(user_id: str) -> list[dict]:
    # Try Redis first
    r = await _get_redis()
    if r:
        data = await r.get(f"chat:{user_id}")
        if data:
            return json.loads(data)

    # Fallback to local file
    fp = _file_path(user_id)
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


async def append_history(user_id: str, role: str, content: str):
    r = await _get_redis()
    history = await get_history(user_id)
    history.append({"role": role, "content": content})

    max_messages = settings.max_history_turns * 2
    if len(history) > max_messages:
        history = history[-max_messages:]

    # Save to Redis or local file
    if r:
        await r.setex(
            f"chat:{user_id}",
            settings.chat_history_ttl,
            json.dumps(history, ensure_ascii=False),
        )
    else:
        _file_path(user_id).write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


async def clear_history(user_id: str):
    r = await _get_redis()
    if r:
        await r.delete(f"chat:{user_id}")

    fp = _file_path(user_id)
    if fp.exists():
        fp.unlink()
