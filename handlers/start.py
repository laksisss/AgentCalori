import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from sqlalchemy import select
from database import async_session
from models import User, Goal


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            db_user = User(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
            session.add(db_user)
            session.add(Goal(user_id=user.id))
            await session.commit()

    app_url = os.getenv("APP_URL", "https://caloriv2-production.up.railway.app")

    keyboard = [
        [InlineKeyboardButton(
            "📊 Открыть приложение",
            web_app=WebAppInfo(url=app_url)
        )],
        [
            InlineKeyboardButton("📈 Статистика", callback_data="stats"),
            InlineKeyboardButton("🎯 Цель", callback_data="goal"),
        ],
    ]

    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я помогу отслеживать питание.\n\n"
        "📝 Отправь мне:\n"
        "• Текст: `курица 200г, рис 150г`\n"
        "• Фото блюда 📸\n"
        "• Несколько продуктов через запятую\n\n"
        "👇 Нажми кнопку ниже, чтобы открыть дашборд"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
