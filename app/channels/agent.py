import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.db.postgres import save_conversation, get_pending_handoffs

router = APIRouter(prefix="/agent", tags=["agent"])


# ── WebSocket 连接管理 ──

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}  # agent_id -> websocket

    async def connect(self, agent_id: str, ws: WebSocket):
        await ws.accept()
        self.active[agent_id] = ws

    def disconnect(self, agent_id: str):
        self.active.pop(agent_id, None)

    async def broadcast(self, msg: dict):
        for ws in self.active.values():
            try:
                await ws.send_json(msg)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/ws/{agent_id}")
async def agent_websocket(ws: WebSocket, agent_id: str):
    """客服 WebSocket 连接，接收实时待处理通知"""
    await manager.connect(agent_id, ws)
    try:
        # Send current pending handoffs on connect
        pending = await get_pending_handoffs()
        await ws.send_json({"type": "pending_list", "data": pending})

        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "accept_handoff":
                conv_id = msg["conversation_id"]
                # Update conversation status
                manager.disconnect(agent_id)  # Simple: agent takes over
                await ws.send_json({"type": "handoff_accepted", "conversation_id": conv_id})

            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(agent_id)
    except Exception:
        manager.disconnect(agent_id)


@router.get("/pending")
async def pending_handoffs():
    """获取所有待处理的转人工请求"""
    return await get_pending_handoffs()


@router.post("/{conv_id}/accept")
async def accept_handoff(conv_id: str, agent_id: str):
    """接受某个转人工请求"""
    from app.db.postgres import async_session, Conversation
    from sqlalchemy import update

    async with async_session() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conv_id)
            .values(handoff_status="accepted", agent_id=agent_id)
        )
        await session.commit()

    await manager.broadcast({
        "type": "handoff_taken",
        "conversation_id": conv_id,
        "agent_id": agent_id,
    })

    return {"status": "accepted", "conversation_id": conv_id}
