"""
bot.py — точка входа с graceful shutdown и очисткой webhook.
"""

import asyncio
import sys
import os
import signal
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


# ─── Graceful shutdown ────────────────────────────────────────────────────────
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Обработчик сигналов SIGTERM/SIGINT для graceful shutdown."""
    logger.info(f"🛑 Получен сигнал {sig}, завершаю работу...")
    shutdown_event.set()


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


async def post_init(application: Application) -> None:
    """Выполняется при инициализации бота — очищает webhook."""
    logger.info("🧹 Удаляю webhook если был установлен...")
    await application.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook удалён, запускаю polling...")


async def run_bot(application):
    """Запускает polling и ждёт сигнала остановки."""
    logger.info("✅ Бот запущен!")
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
    # Ждём сигнала остановки
    await shutdown_event.wait()
    
    logger.info("🛑 Останавливаю бота...")
    await application.updater.stop()


async def run_fastapi():
    """Запускает FastAPI сервер."""
    port = int(os.getenv("PORT", 8080))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    await init_db()

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)  # очищает webhook при старте
        .build()
    )

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("goal", set_goal))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear", clear_command))

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

    # Ждём завершения любой задачи
    done, pending = await asyncio.wait(
        [bot_task, fastapi_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # Отменяем оставшиеся задачи
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Graceful shutdown
    logger.info("🛑 Завершаю работу приложения...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    logger.info("✅ Приложение остановлено.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
