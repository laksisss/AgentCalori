"""
handlers/agent_handler.py — единый обработчик для агента.

Заменяет handlers/meal.py и handlers/photo.py.
Больше нет ConversationHandler, SELECT_MEAL_TYPE, PHOTO_CONFIRM —
агент сам определяет контекст и тип приёма пищи.
"""

import base64
import logging
from telegram import Update, Bot
from telegram.ext import ContextTypes
from config import TELEGRAM_TOKEN
from agent import run_agent
from memory import get_history, add_message

logger = logging.getLogger(__name__)


async def handle_text_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений — передаёт агенту"""
    user_id = update.effective_user.id
    text = update.message.text

    # Показываем что думаем
    thinking_msg = await update.message.reply_text("⏳ Анализирую...")

    history = get_history(user_id)

    try:
        response = await run_agent(
            user_id=user_id,
            message=text,
            history=history
        )

        # Сохраняем в историю диалога
        add_message(user_id, "user", text)
        add_message(user_id, "assistant", response)

        await thinking_msg.edit_text(response)

    except Exception as e:
        logger.error(f"Agent error for user {user_id}: {e}", exc_info=True)
        await thinking_msg.edit_text("❌ Что-то пошло не так. Попробуй ещё раз.")


async def handle_photo_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик фото — скачивает, кодирует в base64, передаёт агенту"""
    user_id = update.effective_user.id
    caption = update.message.caption or ""

    thinking_msg = await update.message.reply_text("📸 Анализирую фото...")

    try:
        # Скачиваем фото
        bot = Bot(token=TELEGRAM_TOKEN)
        photo = update.message.photo[-1]  # наибольшее разрешение
        file = await bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        photo_base64 = base64.b64encode(photo_bytes).decode("utf-8")

        history = get_history(user_id)

        response = await run_agent(
            user_id=user_id,
            message=caption,
            history=history,
            photo_base64=photo_base64
        )

        # Сохраняем в историю
        add_message(user_id, "user", f"[фото] {caption}" if caption else "[фото]")
        add_message(user_id, "assistant", response)

        await thinking_msg.edit_text(response)

    except Exception as e:
        logger.error(f"Photo agent error for user {user_id}: {e}", exc_info=True)
        await thinking_msg.edit_text("❌ Не удалось обработать фото. Попробуй ещё раз.")
