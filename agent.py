"""
agent.py — ядро агента с GigaChat и базой продуктов.
"""
import json
import logging
import asyncio
import re
from gigachat import GigaChat
from config import GIGACHAT_CREDENTIALS

logger = logging.getLogger(__name__)


def get_gigachat_client():
    """Создаёт клиента GigaChat."""
    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        verify_ssl_certs=False,
        scope="GIGACHAT_API_PERS"
    )


async def _gigachat_chat(messages: list, tools: list = None, temperature: float = 0.4, max_tokens: int = 1200):
    """Асинхронная обёртка над синхронным GigaChat SDK."""
    client = get_gigachat_client()
    loop = asyncio.get_event_loop()
    
    def _call():
        kwargs = {
            "messages": messages,  # ✅ есть
            "temperature": temperature,  # ✅ есть
            "max_tokens": max_tokens,  # ✅ есть
            # ❌ УБЕРИ ЭТУ СТРОКУ: "model": "GigaChat",
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return client.chat(**kwargs)
    
    return await loop.run_in_executor(None, _call)


# ─── Tools ────────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_product",
            "description": "Ищет продукт в базе по имени. ВСЕГДА вызывай ПЕРЕД analyze_food_text. Возвращает КБЖУ на 100г если найден.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Название продукта для поиска"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_product",
            "description": "Сохраняет/обновляет продукт в базе. Используй после LLM-анализа чтобы запомнить КБЖУ навсегда. Также вызывай когда пользователь поправил цифры.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "calories": {"type": "number", "description": "Калории на 100г"},
                    "protein": {"type": "number"},
                    "fat": {"type": "number"},
                    "carbs": {"type": "number"},
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"}
                },
                "required": ["name", "calories", "protein", "fat", "carbs"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_food_text",
            "description": "Анализирует еду через LLM. Используй ТОЛЬКО если search_product не нашёл продукт. После вызова обязательно сохрани результат через save_product!",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_meals",
            "description": "Все приёмы пищи за сегодня.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_goal",
            "description": "Цели пользователя по КБЖУ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_meal",
            "description": "Сохраняет приём пищи в базу. ВСЕГДА вызывай после анализа еды!",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "calories": {"type": "number"},
                    "protein": {"type": "number"},
                    "fat": {"type": "number"},
                    "carbs": {"type": "number"},
                    "weight": {"type": "number"},
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]}
                },
                "required": ["user_id", "name", "calories", "protein", "fat", "carbs"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_summary",
            "description": "Сводка за 7 дней.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_last_meal",
            "description": "Удаляет последнюю запись за сегодня.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_meal_quality",
            "description": "Анализ качества питания за сегодня.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_meal",
            "description": "Что съесть исходя из остатка КБЖУ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack", "any"]}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_with_yesterday",
            "description": "Сравнение сегодня со вчера.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_human_feedback",
            "description": "Короткий человеческий комментарий по питанию.",
            "parameters": {
                "type": "object",
                "properties": {
                    "total_calories": {"type": "number"},
                    "protein": {"type": "number"},
                    "fats": {"type": "number"},
                    "carbs": {"type": "number"},
                    "remaining_calories": {"type": "number"}
                },
                "required": ["total_calories", "protein", "fats", "carbs"]
            }
        }
    }
]


# ─── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ты — персональный нутриционист и пищевой трекер в Telegram. Тебя зовут Калори.

━━━ ЧТО ТЫ УМЕЕШЬ ━━━
- Логировать еду по тексту ("съел гречку 200г с курицей") или фото
- Считать КБЖУ и остаток до дневной нормы
- Анализировать качество питания за день
- Предлагать что съесть исходя из остатка нутриентов
- Показывать статистику за день и неделю
- Сравнивать сегодня со вчера
- Удалять последнюю запись если ошибся
- Запоминать продукты в базе чтобы не спрашивать повторно

━━━ АЛГОРИТМ ЛОГИРОВАНИЯ ЕДЫ (ОБЯЗАТЕЛЬНО!) ━━━
1. Когда пользователь пишет про еду — СНАЧАЛА вызови search_product(name)
2. Если продукт найден — используй его КБЖУ (на 100г) и пересчитай на указанный вес
3. Если НЕ найден — ТОЛЬКО ТОГДА вызывай analyze_food_text
4. После analyze_food_text ОБЯЗАТЕЛЬНО вызови save_product чтобы запомнить КБЖУ навсегда
5. Если пользователь поправил цифры — вызови save_product с новыми данными
6. В конце ВСЕГДА вызови save_meal для записи в дневник

━━━ КАК ТЫ ОБЩАЕШЬСЯ ━━━
- ВСЕГДА отвечай на вопросы пользователя
- Коротко и по делу, без воды
- Подтверждай запись еды и показывай остаток
- Добавляй человеческую реакцию через generate_human_feedback
- Можешь замечать паттерны: "кстати, сегодня ты ещё не ел белка"

━━━ ФОРМАТ ОТВЕТА ПРИ ЛОГИРОВАНИИ ━━━
✅ [Название] — [калории] ккал
Б: [белки]г | Ж: [жиры]г | У: [углеводы]г
До нормы осталось [X] ккал
[Ответ на вопросы]
[Комментарий]

━━━ ВАЖНО ━━━
- Работай с реальными данными из базы
- Никогда не выдумывай цифры если есть данные в базе
- Всегда поддерживай диалог
- КЕШИРУЙ все новые продукты через save_product!
"""


# ─── Tool executors ───────────────────────────────────────────────────────────
def _normalize_name(name: str) -> str:
    """Нормализует название продукта для поиска."""
    name = name.lower().strip()
    name = re.sub(r'[^\wа-яё\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name


async def _tool_search_product(args: dict) -> dict:
    """Ищет продукт в базе по имени."""
    from sqlalchemy import select
    from database import async_session
    from models import Product

    name = args.get("name", "")
    normalized = _normalize_name(name)

    async with async_session() as session:
        result = await session.execute(
            select(Product).where(Product.name == normalized)
        )
        product = result.scalar_one_or_none()

        if not product:
            result = await session.execute(
                select(Product).where(Product.name.like(f"%{normalized}%"))
            )
            product = result.scalars().first()

        if not product:
            return {"found": False, "name": name}

        return {
            "found": True,
            "name": product.display_name,
            "calories_per_100g": product.calories,
            "protein_per_100g": product.protein,
            "fat_per_100g": product.fat,
            "carbs_per_100g": product.carbs,
            "source": product.source,
            "hint": "Используй эти данные и пересчитай на вес блюда"
        }


async def _tool_save_product(args: dict) -> dict:
    """Сохраняет/обновляет продукт в базе."""
    from sqlalchemy import select
    from database import async_session
    from models import Product

    name = args.get("name", "")
    normalized = _normalize_name(name)
    display_name = name

    async with async_session() as session:
        result = await session.execute(
            select(Product).where(Product.name == normalized)
        )
        product = result.scalar_one_or_none()

        if product:
            product.calories = args.get("calories", product.calories)
            product.protein = args.get("protein", product.protein)
            product.fat = args.get("fat", product.fat)
            product.carbs = args.get("carbs", product.carbs)
            product.source = "corrected"
            product.corrections_count += 1
            action = "updated"
        else:
            product = Product(
                name=normalized,
                display_name=display_name,
                calories=args.get("calories", 0),
                protein=args.get("protein", 0),
                fat=args.get("fat", 0),
                carbs=args.get("carbs", 0),
                user_id=args.get("user_id"),
                source="llm"
            )
            session.add(product)
            action = "created"

        await session.commit()
        await session.refresh(product)

    return {
        "success": True,
        "action": action,
        "product_id": product.id,
        "name": product.display_name,
        "calories_per_100g": product.calories,
        "protein_per_100g": product.protein,
        "fat_per_100g": product.fat,
        "carbs_per_100g": product.carbs
    }


async def _tool_analyze_food_text(args: dict) -> dict:
    """LLM-анализ еды через GigaChat."""
    prompt = f"""Проанализируй еду. Верни КБЖУ НА 100 ГРАММ продукта.
Верни ТОЛЬКО JSON без пояснений.
Еда: {args['text']}
Формат:
{{ "name": "название", "calories_per_100g": 150, "protein_per_100g": 10, "fat_per_100g": 5, "carbs_per_100g": 20, "estimated_weight": 150 }}"""

    response = await _gigachat_chat(
        messages=[
            {"role": "system", "content": "Отвечай только валидным JSON без markdown."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=400
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    if '[' in raw:
        start, end = raw.find('['), raw.rfind(']') + 1
    else:
        start, end = raw.find('{'), raw.rfind('}') + 1

    data = json.loads(raw[start:end])
    return data


async def _tool_get_today_meals(args: dict) -> dict:
    from sqlalchemy import select
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
            "id": m.id, "name": m.name, "meal_type": m.meal_type,
            "calories": m.calories, "protein": m.protein,
            "fat": m.fat, "carbs": m.carbs, "weight": m.weight
        }
        for m in meals
    ]

    totals = {
        "calories": round(sum(m.calories or 0 for m in meals), 1),
        "protein": round(sum(m.protein or 0 for m in meals), 1),
        "fat": round(sum(m.fat or 0 for m in meals), 1),
        "carbs": round(sum(m.carbs or 0 for m in meals), 1),
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
        "calories": goal.calories, "protein": goal.protein,
        "fat": goal.fat, "carbs": goal.carbs, "is_default": False
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
                "calories": round(sum(m.calories or 0 for m in meals), 1),
                "protein": round(sum(m.protein or 0 for m in meals), 1),
                "fat": round(sum(m.fat or 0 for m in meals), 1),
                "carbs": round(sum(m.carbs or 0 for m in meals), 1),
                "meals_count": len(meals)
            })

    return {"days": days}


async def _tool_delete_last_meal(args: dict) -> dict:
    from sqlalchemy import select
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


async def _tool_analyze_meal_quality(args: dict) -> dict:
    today_data = await _tool_get_today_meals(args)
    goal_data = await _tool_get_user_goal(args)
    totals = today_data["totals"]
    meals = today_data["meals"]
    goal = goal_data

    def pct(a, t): return round((a / t * 100) if t else 0, 1)

    cal_pct = pct(totals["calories"], goal["calories"])
    prot_pct = pct(totals["protein"], goal["protein"])
    fat_pct = pct(totals["fat"], goal["fat"])
    carb_pct = pct(totals["carbs"], goal["carbs"])

    meal_types_logged = list({m["meal_type"] for m in meals})
    missing = [t for t in ["breakfast", "lunch", "dinner"] if t not in meal_types_logged]

    issues = []
    if cal_pct < 50: issues.append("критически мало калорий")
    elif cal_pct < 80: issues.append("недобор калорий")
    elif cal_pct > 120: issues.append("перебор калорий")
    if prot_pct < 70: issues.append(f"мало белка ({totals['protein']}г из {goal['protein']}г)")
    if fat_pct > 130: issues.append(f"перебор жиров ({totals['fat']}г)")
    if carb_pct > 130: issues.append(f"перебор углеводов ({totals['carbs']}г)")

    return {
        "totals": totals, "goal": goal,
        "percentages": {"calories": cal_pct, "protein": prot_pct, "fat": fat_pct, "carbs": carb_pct},
        "meals_count": len(meals), "missing_main_meals": missing,
        "issues": issues, "meals_list": [m["name"] for m in meals]
    }


async def _tool_suggest_meal(args: dict) -> dict:
    today_data = await _tool_get_today_meals(args)
    goal_data = await _tool_get_user_goal(args)
    totals = today_data["totals"]
    goal = goal_data

    remaining = {
        "calories": round(goal["calories"] - totals["calories"], 1),
        "protein": round(goal["protein"] - totals["protein"], 1),
        "fat": round(goal["fat"] - totals["fat"], 1),
        "carbs": round(goal["carbs"] - totals["carbs"], 1),
    }

    return {
        "remaining_nutrients": remaining,
        "meal_type_requested": args.get("meal_type", "any"),
        "already_eaten_today": [m["name"] for m in today_data["meals"]],
        "goal": goal, "totals_so_far": totals
    }


async def _tool_compare_with_yesterday(args: dict) -> dict:
    from sqlalchemy import select
    from database import async_session
    from models import Meal
    import datetime

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    goal_data = await _tool_get_user_goal(args)

    async def get_day_totals(date_str):
        async with async_session() as session:
            result = await session.execute(
                select(Meal).where(
                    Meal.user_id == args["user_id"], Meal.date == date_str
                )
            )
            meals = result.scalars().all()
        return {
            "calories": round(sum(m.calories or 0 for m in meals), 1),
            "protein": round(sum(m.protein or 0 for m in meals), 1),
            "fat": round(sum(m.fat or 0 for m in meals), 1),
            "carbs": round(sum(m.carbs or 0 for m in meals), 1),
            "meals_count": len(meals)
        }

    today_totals = await get_day_totals(today.isoformat())
    yesterday_totals = await get_day_totals(yesterday.isoformat())

    def delta(a, b): return round(a - b, 1)

    return {
        "today": {"date": today.isoformat(), **today_totals},
        "yesterday": {"date": yesterday.isoformat(), **yesterday_totals},
        "delta": {
            "calories": delta(today_totals["calories"], yesterday_totals["calories"]),
            "protein": delta(today_totals["protein"], yesterday_totals["protein"]),
            "fat": delta(today_totals["fat"], yesterday_totals["fat"]),
            "carbs": delta(today_totals["carbs"], yesterday_totals["carbs"]),
        },
        "goal": goal_data
    }


async def _tool_generate_human_feedback(args: dict) -> str:
    total = args.get('total_calories', 0)
    protein = args.get('protein', 0)
    fats = args.get('fats', 0)
    carbs = args.get('carbs', 0)
    remaining = args.get('remaining_calories', 0)

    if total == 0:
        return "Пока ничего не съел, начинай день!"

    comments = []
    if carbs > 150: comments.append("многовато углеводов сегодня 🍞")
    if protein < 30: comments.append("маловато белка 🥩")
    if fats > 80: comments.append("жиров перебор 🥑")
    if 0 < remaining < 200: comments.append("почти уложился в норму! 👍")
    if not comments: comments.append("всё отлично, так держать! 💪")

    return " ".join(comments)


# ─── Tool dispatcher ──────────────────────────────────────────────────────────
TOOL_EXECUTORS = {
    "search_product": _tool_search_product,
    "save_product": _tool_save_product,
    "analyze_food_text": _tool_analyze_food_text,
    "get_today_meals": _tool_get_today_meals,
    "get_user_goal": _tool_get_user_goal,
    "save_meal": _tool_save_meal,
    "get_week_summary": _tool_get_week_summary,
    "delete_last_meal": _tool_delete_last_meal,
    "analyze_meal_quality": _tool_analyze_meal_quality,
    "suggest_meal": _tool_suggest_meal,
    "compare_with_yesterday": _tool_compare_with_yesterday,
    "generate_human_feedback": _tool_generate_human_feedback,
}


async def execute_tool(tool_name: str, tool_args: dict) -> str:
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = await executor(tool_args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Tool {tool_name} error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


# ─── ReAct loop ───────────────────────────────────────────────────────────────
async def run_agent(
    user_id: int,
    message: str,
    history: list[dict],
    photo_base64: str | None = None
) -> str:
    if photo_base64:
        vision_result = await _analyze_photo_with_vision(photo_base64, message)
        user_content_for_agent = (
            f"[Фото еды] Результат анализа: {vision_result}\n"
            f"Пользователь: {message or 'Определи и сохрани'}"
        )
    else:
        user_content_for_agent = message

    system = SYSTEM_PROMPT + f"\n\nТекущий пользователь: user_id={user_id}"
    messages = [{"role": "system", "content": system}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_content_for_agent})

    for _ in range(8):
        response = await _gigachat_chat(messages, TOOLS)

        choice = response.choices[0]

        if choice.finish_reason == "stop" or not choice.message.tool_calls:
            return choice.message.content or "Готово."

        tool_calls = choice.message.tool_calls

        messages.append({
            "role": "assistant",
            "content": choice.message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ]
        })

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            logger.info(f"Agent → {tool_name}({tool_args})")
            tool_result = await execute_tool(tool_name, tool_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result
            })

    return "Не удалось обработать запрос. Попробуй ещё раз."


async def _analyze_photo_with_vision(photo_base64: str, hint: str = "") -> str:
    response = await _gigachat_chat(
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "Проанализируй фото еды. Верни КБЖУ НА 100 ГРАММ:\n"
                    '{ "name": "блюдо", "calories_per_100g": 150, "protein_per_100g": 10, "fat_per_100g": 5, "carbs_per_100g": 20, "estimated_weight": 200}\n'
                    f"Подсказка: {hint or 'нет'}"
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{photo_base64}"}}
            ]
        }],
        max_tokens=300,
        temperature=0.2
    )
    return response.choices[0].message.content.strip()
