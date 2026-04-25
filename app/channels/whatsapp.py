import httpx
from fastapi import APIRouter, Request, HTTPException, Query
from app.config import settings
from app.engine.deepseek import chat
from app.memory.conversation import get_history, append_history

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

META_API = "https://graph.facebook.com/v21.0"


async def send_whatsapp_message(to: str, text: str):
    """通过 Meta Cloud API 发送 WhatsApp 消息"""
    url = f"{META_API}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
):
    """Meta Webhook 验证（GET 请求）"""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_message(request: Request):
    """接收 WhatsApp 消息（POST 请求）"""
    body = await request.json()

    try:
        entry = body["entry"][0]
        change = entry["changes"][0]
        value = change["value"]

        # Check for incoming message
        if "messages" not in value:
            return {"status": "no_message"}

        message = value["messages"][0]
        if message["type"] != "text":
            await send_whatsapp_message(
                value["contacts"][0]["wa_id"],
                "目前仅支持文字消息，请发送文字描述您的问题。"
            )
            return {"status": "unsupported_type"}

        user_id = message["from"]
        user_msg = message["text"]["body"]

        # Get history
        history = await get_history(user_id)
        await append_history(user_id, "user", user_msg)
        history.append({"role": "user", "content": user_msg})

        # Call AI
        try:
            reply = await chat(history)
        except Exception:
            reply = "抱歉，我暂时无法处理您的请求，请稍后再试。"

        await append_history(user_id, "assistant", reply)

        # Send reply
        await send_whatsapp_message(user_id, reply)

    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    return {"status": "ok"}
