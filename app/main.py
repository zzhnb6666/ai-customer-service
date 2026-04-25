import asyncio
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from app.config import settings
from app.engine.deepseek import chat
from app.memory.conversation import get_history, append_history, clear_history
from app.models.schemas import ChatRequest, ChatResponse
# RAG modules (each independently optional)
try:
    from app.rag.retriever import retrieve_knowledge
except ImportError:
    async def retrieve_knowledge(query: str, top_k: int = 3):
        return ""

try:
    from app.rag.loader import load_documents
except ImportError:
    async def load_documents(*args, **kwargs):
        return []

try:
    from app.rag.vectorstore import index_documents
except ImportError:
    async def index_documents(*args, **kwargs):
        return 0

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def _init_db_safe():
    try:
        from app.db.postgres import init_db
        await init_db()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init DB in background (not critical for basic chat)
    import asyncio as _asyncio
    _asyncio.create_task(_init_db_safe())

    telegram_task = None
    if settings.telegram_bot_token:
        from app.channels.telegram import start_telegram
        telegram_task = asyncio.create_task(start_telegram())

    yield

    # Shutdown
    if telegram_task:
        telegram_task.cancel()
    try:
        from app.db.redis import get_redis
        r = await get_redis()
        if r:
            await r.close()
    except Exception:
        pass


app = FastAPI(title="AI 智能客服系统", version="0.1.0", lifespan=lifespan)

# WhatsApp Webhook + Agent Panel
from app.channels.whatsapp import router as whatsapp_router
from app.channels.agent import router as agent_router
app.include_router(whatsapp_router)
app.include_router(agent_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """统一对话接口"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    history = await get_history(req.user_id)
    await append_history(req.user_id, "user", req.message)
    history.append({"role": "user", "content": req.message})

    # 调用 AI（带 RAG 知识检索）
    try:
        knowledge = await retrieve_knowledge(req.message)
        reply = await chat(history, knowledge=knowledge)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 引擎错误: {str(e)}")

    await append_history(req.user_id, "assistant", reply)

    # 检测是否需要转人工
    handoff_keywords = ["转人工", "人工客服", "找真人", "我要投诉"]
    handoff = any(kw in req.message for kw in handoff_keywords)

    if handoff:
        from app.db.postgres import save_conversation
        full_history = await get_history(req.user_id)
        await save_conversation(
            conv_id=f"{req.user_id}-{int(time.time())}",
            user_id=req.user_id,
            channel=req.channel,
            messages=full_history,
            handoff=True,
        )

    return ChatResponse(
        reply=reply,
        intent="handoff" if handoff else "general",
        handoff=handoff,
    )


@app.post("/chat/clear")
async def clear_chat(user_id: str):
    """清除用户对话历史"""
    await clear_history(user_id)
    return {"message": "对话历史已清除"}


# ── 知识库管理 ──

@app.post("/knowledge/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """上传产品文档（PDF/DOCX/MD/TXT）"""
    saved = []
    for file in files:
        ext = file.filename.split(".")[-1].lower()
        if ext not in ["pdf", "docx", "md", "txt"]:
            continue
        file_path = UPLOAD_DIR / file.filename
        file_path.write_bytes(await file.read())
        saved.append(file.filename)
    # 上传后自动刷新知识库
    from app.engine.deepseek import reload_knowledge
    reload_knowledge()

    return {"uploaded": saved, "count": len(saved)}


@app.post("/knowledge/index")
async def build_index():
    """将所有已上传文档向量化并建立索引"""
    chunks = await load_documents(str(UPLOAD_DIR))
    if not chunks:
        return {"error": "没有找到可用的文档，请先上传"}

    count = await index_documents(chunks)
    return {"message": "索引完成", "chunks": count}


@app.get("/knowledge/search")
async def search_knowledge(q: str, top_k: int = 3):
    """搜索知识库"""
    results = await retrieve_knowledge(q)
    return {"query": q, "results": results.split("\n---\n") if results else []}


# ── 人工对话学习 ──

HUMAN_EXAMPLES_DIR = Path("data/human_examples")
HUMAN_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)


from pydantic import BaseModel as PydanticModel

class HumanChatUpload(PydanticModel):
    title: str = ""
    messages: list[dict]


@app.post("/learn/human-chat")
async def upload_human_chat(body: HumanChatUpload):
    """上传人工客服的对话记录，让 AI 学习说话方式

    messages 格式:
    [
        {"role": "user", "content": "客户消息"},
        {"role": "assistant", "content": "人工客服回复"},
        ...
    ]
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="对话内容不能为空")

    import time
    filename = f"{int(time.time())}_{body.title or 'chat'}.txt"
    filepath = HUMAN_EXAMPLES_DIR / filename

    # 格式化为可读的对话记录
    lines = [f"# 人工客服对话记录 - {body.title or '未命名'}\n"]
    lines.append(f"# 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    for m in body.messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            lines.append(f"客户: {content}")
        elif role == "assistant":
            lines.append(f"客服: {content}")
        else:
            lines.append(f"[{role}]: {content}")

    filepath.write_text("\n".join(lines), encoding="utf-8")

    # 热更新 AI 系统提示词
    from app.engine.deepseek import reload_knowledge
    reload_knowledge()

    return {
        "status": "ok",
        "message": f"已学习 {len(body.messages)} 条对话记录",
        "file": filename,
    }


@app.post("/learn/reload")
async def reload_ai_knowledge():
    """手动刷新 AI 知识库（上传新文件后调用）"""
    from app.engine.deepseek import reload_knowledge
    reload_knowledge()
    return {"status": "ok", "message": "知识库已刷新"}


@app.get("/learn/examples")
async def list_human_examples():
    """列出所有已上传的人工对话记录"""
    files = []
    for f in sorted(HUMAN_EXAMPLES_DIR.iterdir(), reverse=True):
        if f.suffix in (".txt", ".md"):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "preview": f.read_text(encoding="utf-8")[:300],
            })
    return {"count": len(files), "files": files}
