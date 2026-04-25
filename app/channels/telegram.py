import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.config import settings
from app.engine.deepseek import chat
from app.memory.conversation import get_history, append_history, clear_history
from app.rag.retriever import retrieve_knowledge
from app.db.postgres import save_conversation

TELEGRAM_ENABLED = (
    settings.telegram_bot_token
    and settings.telegram_bot_token != "your_telegram_bot_token"
)

if TELEGRAM_ENABLED:
    kwargs = {"token": settings.telegram_bot_token}
    if settings.proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession
        kwargs["session"] = AiohttpSession(proxy=settings.proxy_url)
    bot = Bot(**kwargs)
    dp = Dispatcher()


def get_handoff_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="转人工客服", callback_data="handoff")],
        [InlineKeyboardButton(text="清除对话", callback_data="clear")],
    ])


if TELEGRAM_ENABLED:

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer(
            "您好！我是AI智能客服助手，有什么可以帮您的？\n\n"
            "直接发送消息即可与我对话。\n"
            "输入 /clear 清除对话历史。\n"
            "输入 /handoff 转人工客服。",
            reply_markup=get_handoff_keyboard(),
        )

    @dp.message(Command("clear"))
    async def cmd_clear(message: types.Message):
        await clear_history(str(message.from_user.id))
        await message.answer("对话历史已清除，开始新的对话吧！")

    @dp.message(Command("handoff"))
    async def cmd_handoff(message: types.Message):
        await message.answer(
            "正在为您转接人工客服，请稍候...\n"
            "预计等待时间：2-5分钟\n\n"
            "如果长时间无人响应，请通过其他渠道联系我们。"
        )

    @dp.callback_query(lambda c: c.data == "handoff")
    async def callback_handoff(callback: types.CallbackQuery):
        await callback.answer()
        await callback.message.answer(
            "正在为您转接人工客服，请稍候...\n"
            "预计等待时间：2-5分钟"
        )

    @dp.callback_query(lambda c: c.data == "clear")
    async def callback_clear(callback: types.CallbackQuery):
        await callback.answer()
        await clear_history(str(callback.from_user.id))
        await callback.message.answer("对话历史已清除！")

    @dp.message()
    async def handle_message(message: types.Message):
        user_id = str(message.from_user.id)
        user_msg = message.text

        if not user_msg or not user_msg.strip():
            return

        await bot.send_chat_action(message.chat.id, "typing")

        history = await get_history(user_id)
        await append_history(user_id, "user", user_msg)
        history.append({"role": "user", "content": user_msg})

        try:
            knowledge = await retrieve_knowledge(user_msg)
            reply = await chat(history, knowledge=knowledge)
        except Exception:
            reply = "抱歉，我暂时无法处理您的请求，请稍后再试或转人工客服。"

        await append_history(user_id, "assistant", reply)

        handoff_keywords = ["转人工", "人工客服", "找真人", "我要投诉"]
        if any(kw in user_msg for kw in handoff_keywords):
            full_history = await get_history(user_id)
            await save_conversation(
                conv_id=f"{user_id}-{int(time.time())}",
                user_id=user_id,
                channel="telegram",
                messages=full_history,
                handoff=True,
            )
            await message.answer(reply)
            await message.answer(
                "已为您记录转人工需求，客服人员将尽快与您联系。\n"
                "您的对话编号：" + user_id[-8:]
            )
        else:
            await message.answer(reply, reply_markup=get_handoff_keyboard())


async def start_telegram():
    """启动 Telegram Bot（由 main.py 调用）"""
    if TELEGRAM_ENABLED:
        await dp.start_polling(bot)
