"""
agent.py — ядро агента. Заменяет прямые вызовы Groq в ai_service.py.

Логика:
  1. Получает сообщение (текст или фото) + историю диалога
  2. Запускает ReAct loop: LLM решает какой tool вызвать
  3. Выполняет tool, возвращает результат LLM
  4. Повторяет до финального ответа пользователю
"""

import json
import base64
import logging
from groq import AsyncGroq
from config import GROQ_API_KEY, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)

# ─── Описание инструментов для LLM ───────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_food_text",
            "description": "Анализирует текстовое описание еды и возвращает КБЖУ. Используй когда пользователь описывает что съел текстом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Описание еды от пользователя"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_meals",
            "description": "Получает все приёмы пищи пользователя за сегодня из базы данных. Используй когда нужно показать статистику за день или ответить на вопрос о питании сегодня.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_goal",
            "description": "Получает цели пользователя по калориям и БЖУ. Используй для сравнения текущего питания с целью.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_meal",
            "description": "Сохраняет приём пищи в базу данных. Используй после успешного анализа еды для записи результата.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"},
                    "name": {"type": "string", "description": "Название блюда"},
                    "calories": {"type": "number", "description": "Калории"},
                    "protein": {"type": "number", "description": "Белки в граммах"},
                    "fat": {"type": "number", "description": "Жиры в граммах"},
                    "carbs": {"type": "number", "description": "Углеводы в граммах"},
                    "weight": {"type": "number", "description": "Вес в граммах"},
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                        "description": "Тип приёма пищи"
                    }
                },
                "required": ["user_id", "name", "calories", "protein", "fat", "carbs"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_summary",
            "description": "Получает сводку питания за последние 7 дней. Используй когда пользователь спрашивает о питании за неделю или хочет увидеть динамику.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_last_meal",
            "description": "Удаляет последний добавленный приём пищи. Используй если пользователь просит отменить или удалить последнюю запись.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"}
                },
                "required": ["user_id"]
            }
        }
    }
]

SYSTEM_PROMPT = """Ты — персональный нутриционист и пищевой трекер в Telegram. Тебя зовут Калори.

Твои задачи:
- Помогать пользователю отслеживать питание и КБЖУ
- Анализировать фото и описания еды
- Давать краткие умные советы по питанию
- Замечать паттерны: пропущенные приёмы пищи, перебор по нутриентам

Правила:
- Всегда сохраняй еду в базу после анализа (используй save_meal)
- Если непонятно какой тип приёма пищи — определи по времени суток или спроси
- Отвечай коротко и по делу, без воды
- Используй эмодзи умеренно
- Если пользователь просто пишет что съел — анализируй и сохраняй без лишних вопросов
- После сохранения всегда показывай: название, КБЖУ, и остаток до дневной нормы если есть цель

Формат ответа после логирования еды:
✅ [Название] — [калории] ккал
Б: [белки]г | Ж: [жиры]г | У: [углеводы]г
[Если есть цель: До нормы осталось X ккал]
"""


# ─── Tool executors ────────────────────────────────────────────────────────────

async def _tool_analyze_food_text(args: dict) -> dict:
    """Анализ текста через Groq без vision"""
    from groq import AsyncGroq
    client = AsyncGroq(api_key=GROQ_API_KEY)
    
    prompt = f"""Проанализируй еду и верни ТОЛЬКО JSON без пояснений.
Еда: {args['text']}

Формат (один объект или массив если несколько блюд):
{{"name": "название", "weight": 150, "calories": 300, "protein": 20, "fat": 10, "carbs": 30}}"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Отвечай только валидным JSON без markdown и пояснений."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=600
    )
    
    raw = response.choices[0].message.content.strip()
    # Чистим markdown если есть
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    
    # Извлекаем JSON
    if '[' in raw:
        start, end = raw.find('['), raw.rfind(']') + 1
    else:
        start, end = raw.find('{'), raw.rfind('}') + 1
    
    data = json.loads(raw[start:end])
    
    # Если массив — суммируем
    if isinstance(data, list):
        combined = {
            "name": ", ".join(d.get("name", "") for d in data),
            "weight": sum(d.get("weight", 0) for d in data),
            "calories": sum(d.get("calories", 0) for d in data),
            "protein": sum(d.get("protein", 0) for d in data),
            "fat": sum(d.get("fat", 0) for d in data),
            "carbs": sum(d.get("carbs", 0) for d in data),
            "items": data  # сохраняем детали
        }
        return combined
    return data


async def _tool_get_today_meals(args: dict) -> dict:
    from sqlalchemy import select, func
    from database import async_session
    from models import Meal
    import datetime
    
    today = datetime.date.today().isoformat()
    async with async_session() as session:
        result = await session.execute(
            select(Meal).where(
                Meal.user_id == args["user_id"],
                Meal.date == today
            ).order_by(Meal.created_at)
        )
        meals = result.scalars().all()
    
    if not meals:
        return {"meals": [], "totals": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}
    
    meal_list = [
        {
            "id": m.id,
            "name": m.name,
            "meal_type": m.meal_type,
            "calories": m.calories,
            "protein": m.protein,
            "fat": m.fat,
            "carbs": m.carbs,
            "weight": m.weight
        }
        for m in meals
    ]
    
    totals = {
        "calories": sum(m.calories or 0 for m in meals),
        "protein": sum(m.protein or 0 for m in meals),
        "fat": sum(m.fat or 0 for m in meals),
        "carbs": sum(m.carbs or 0 for m in meals),
    }
    
    return {"meals": meal_list, "totals": totals}


async def _tool_get_user_goal(args: dict) -> dict:
    from sqlalchemy import select
    from database import async_session
    from models import Goal
    
    async with async_session() as session:
        result = await session.execute(
            select(Goal).where(Goal.user_id == args["user_id"])
        )
        goal = result.scalar_one_or_none()
    
    if not goal:
        return {"calories": 2000, "protein": 100, "fat": 70, "carbs": 250, "is_default": True}
    
    return {
        "calories": goal.calories,
        "protein": goal.protein,
        "fat": goal.fat,
        "carbs": goal.carbs,
        "is_default": False
    }


async def _tool_save_meal(args: dict) -> dict:
    from database import async_session
    from models import Meal
    import datetime
    
    today = datetime.date.today().isoformat()
    
    async with async_session() as session:
        meal = Meal(
            user_id=args["user_id"],
            date=today,
            name=args["name"],
            calories=args.get("calories", 0),
            protein=args.get("protein", 0),
            fat=args.get("fat", 0),
            carbs=args.get("carbs", 0),
            weight=args.get("weight", 0),
            meal_type=args.get("meal_type", "snack")
        )
        session.add(meal)
        await session.commit()
        await session.refresh(meal)
    
    return {"success": True, "meal_id": meal.id, "saved": args["name"]}


async def _tool_get_week_summary(args: dict) -> dict:
    from sqlalchemy import select
    from database import async_session
    from models import Meal
    import datetime
    
    today = datetime.date.today()
    days = []
    
    async with async_session() as session:
        for i in range(7):
            day = (today - datetime.timedelta(days=i)).isoformat()
            result = await session.execute(
                select(Meal).where(
                    Meal.user_id == args["user_id"],
                    Meal.date == day
                )
            )
            meals = result.scalars().all()
            days.append({
                "date": day,
                "calories": sum(m.calories or 0 for m in meals),
                "protein": sum(m.protein or 0 for m in meals),
                "fat": sum(m.fat or 0 for m in meals),
                "carbs": sum(m.carbs or 0 for m in meals),
                "meals_count": len(meals)
            })
    
    return {"days": days}


async def _tool_delete_last_meal(args: dict) -> dict:
    from sqlalchemy import select, delete
    from database import async_session
    from models import Meal
    import datetime
    
    today = datetime.date.today().isoformat()
    
    async with async_session() as session:
        result = await session.execute(
            select(Meal).where(
                Meal.user_id == args["user_id"],
                Meal.date == today
            ).order_by(Meal.created_at.desc()).limit(1)
        )
        meal = result.scalar_one_or_none()
        
        if not meal:
            return {"success": False, "message": "Нет записей за сегодня"}
        
        name = meal.name
        await session.delete(meal)
        await session.commit()
    
    return {"success": True, "deleted": name}


# ─── Tool dispatcher ───────────────────────────────────────────────────────────

TOOL_EXECUTORS = {
    "analyze_food_text": _tool_analyze_food_text,
    "get_today_meals": _tool_get_today_meals,
    "get_user_goal": _tool_get_user_goal,
    "save_meal": _tool_save_meal,
    "get_week_summary": _tool_get_week_summary,
    "delete_last_meal": _tool_delete_last_meal,
}


async def execute_tool(tool_name: str, tool_args: dict) -> str:
    """Вызывает нужный tool и возвращает результат как строку для LLM"""
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    
    try:
        result = await executor(tool_args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Tool {tool_name} error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


# ─── Главный агентный loop ─────────────────────────────────────────────────────

async def run_agent(
    user_id: int,
    message: str,
    history: list[dict],
    photo_base64: str | None = None
) -> str:
    """
    Основная функция агента.
    
    Args:
        user_id: Telegram ID пользователя
        message: текст сообщения
        history: история диалога [{"role": "user/assistant", "content": "..."}]
        photo_base64: base64 фото если есть
    
    Returns:
        Финальный ответ агента пользователю
    """
    client = AsyncGroq(api_key=GROQ_API_KEY)
    
    # Строим контент текущего сообщения
    if photo_base64:
        # Фото → vision модель
        user_content = [
            {
                "type": "text",
                "text": message or "Что это за блюдо? Определи название, вес и КБЖУ."
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{photo_base64}"}
            }
        ]
        # Для vision сначала анализируем фото отдельно, потом передаём агенту
        vision_result = await _analyze_photo_with_vision(client, photo_base64, message)
        # Подменяем контент на текстовый результат анализа для основного loop
        user_content_for_agent = f"[Фото еды] Результат анализа: {vision_result}\nПользователь: {message or 'Определи и сохрани'}"
    else:
        user_content_for_agent = message
    
    # Собираем messages для агента
    # Добавляем user_id в системный промпт чтобы агент знал с кем работает
    system = SYSTEM_PROMPT + f"\n\nТекущий пользователь: user_id={user_id}"
    
    messages = [{"role": "system", "content": system}]
    
    # Добавляем историю (последние 10 сообщений чтобы не раздувать контекст)
    messages.extend(history[-10:])
    
    # Добавляем текущее сообщение
    messages.append({"role": "user", "content": user_content_for_agent})
    
    # ─── ReAct loop ───────────────────────────────────────────────────────────
    max_iterations = 8  # защита от бесконечного loop
    
    for iteration in range(max_iterations):
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=1000
        )
        
        choice = response.choices[0]
        
        # Финальный ответ — LLM решил что всё готово
        if choice.finish_reason == "stop" or not choice.message.tool_calls:
            return choice.message.content or "Готово."
        
        # Есть tool calls — выполняем все
        tool_calls = choice.message.tool_calls
        
        # Добавляем ответ ассистента с tool calls в историю
        messages.append({
            "role": "assistant",
            "content": choice.message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in tool_calls
            ]
        })
        
        # Выполняем каждый tool и добавляем результат
        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}
            
            logger.info(f"Agent calling tool: {tool_name} with {tool_args}")
            tool_result = await execute_tool(tool_name, tool_args)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result
            })
        
        # Следующая итерация — LLM видит результаты tools и решает что делать дальше
    
    return "Не удалось обработать запрос. Попробуй ещё раз."


async def _analyze_photo_with_vision(client: AsyncGroq, photo_base64: str, hint: str = "") -> str:
    """Отдельный vision-вызов для анализа фото"""
    response = await client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Проанализируй фото еды. Верни ТОЛЬКО JSON:\n"
                            '{"name": "блюдо", "weight": 200, "calories": 300, "protein": 24, "fat": 10, "carbs": 36}\n'
                            f"Подсказка от пользователя: {hint or 'нет'}"
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{photo_base64}"}
                    }
                ]
            }
        ],
        max_tokens=300,
        temperature=0.2
    )
    return response.choices[0].message.content.strip()
