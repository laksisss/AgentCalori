"""
bot.py — переписанная точка входа.

Что изменилось vs оригинал:
- Убраны ConversationHandler (SELECT_MEAL_TYPE, PHOTO_CONFIRM)
- Убраны handlers/meal.py и handlers/photo.py из импортов
- Добавлен единый agent_handler
- Добавлена команда /clear (сброс истории диалога)
- Исправлен PTBUserWarning (per_message)
- Исправлен 409 Conflict (drop_pending_updates=True)
"""

import asyncio
import sys
import os
import logging
import json
import uvicorn
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler
)
from telegram import Update
from config import TELEGRAM_TOKEN
from database import init_db
from handlers.agent_handler import handle_text_agent, handle_photo_agent
from handlers.start import start_command
from handlers.profile import set_goal, show_goal
from handlers.stats import stats_command
from memory import clear_history
from web_app import app as fastapi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def clear_command(update: Update, context) -> None:
    """Очищает историю диалога пользователя"""
    user_id = update.effective_user.id
    clear_history(user_id)
    await update.message.reply_text("🗑️ История диалога очищена. Начинаем заново!")


async def menu_callback(update: Update, context) -> None:
    """Обработка callback-кнопок меню"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "stats":
        await stats_command(update, context)
    elif data == "goal":
        await show_goal(update, context)
    elif data in ("menu", "menu_stats", "menu_main"):
        await start_command(update, context)
    elif data.startswith("hist_"):
        await query.edit_message_text("📅 История за другие дни доступна в Mini App!")


async def handle_web_app_data(update: Update, context) -> None:
    """Обработка данных от Mini App"""
    web_app_data = update.effective_message.web_app_data
    if web_app_data:
        try:
            data = json.loads(web_app_data.data)
            if data.get("action") == "add_meal":
                await update.effective_message.reply_text(
                    "📝 Отправь что ты съел — текстом или фото!",
                )
        except json.JSONDecodeError:
            pass


async def error_handler(update: object, context) -> None:
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)


async def run_bot(application):
    logger.info("✅ Бот запущен!")
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True  # исправляет 409 Conflict при редеплое
    )
    while True:
        await asyncio.sleep(1)


async def run_fastapi():
    port = int(os.getenv("PORT", 8080))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await init_db()

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("goal", set_goal))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear", clear_command))  # новая команда

    # Callback кнопки меню
    application.add_handler(CallbackQueryHandler(menu_callback))

    # Mini App данные
    application.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data)
    )

    # Главные обработчики — агент
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_agent))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_agent)
    )

    application.add_error_handler(error_handler)

    logger.info("🚀 Запуск бота и Mini App...")

    await application.initialize()
    await application.start()

    bot_task = asyncio.create_task(run_bot(application))
    fastapi_task = asyncio.create_task(run_fastapi())

    done, pending = await asyncio.wait(
        [bot_task, fastapi_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()

    await application.updater.stop()
    await application.stop()
    await application.shutdown()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
