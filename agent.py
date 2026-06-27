"""
agent.py — ядро агента с расширенными возможностями.

Новое по сравнению с предыдущей версией:
  - Расширенный SYSTEM_PROMPT: агент умеет разговаривать, знает свои возможности
  - Tool: analyze_meal_quality — разбор качества питания за день
  - Tool: suggest_meal — предлагает что съесть исходя из остатка КБЖУ
  - Tool: compare_with_yesterday — сравнение сегодня со вчера
"""

import json
import logging
from groq import AsyncGroq
from config import GROQ_API_KEY, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)

# ─── Tools ────────────────────────────────────────────────────────────────────

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
            "description": "Получает все приёмы пищи пользователя за сегодня. Используй для статистики, анализа, вопросов о сегодняшнем дне.",
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
            "description": "Получает цели пользователя по калориям и БЖУ.",
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
            "description": "Сохраняет приём пищи в базу. Используй после анализа еды.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Telegram ID пользователя"},
                    "name": {"type": "string", "description": "Название блюда"},
                    "calories": {"type": "number"},
                    "protein": {"type": "number"},
                    "fat": {"type": "number"},
                    "carbs": {"type": "number"},
                    "weight": {"type": "number"},
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"]
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
            "description": "Сводка питания за 7 дней. Используй для недельной статистики и анализа динамики.",
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
            "name": "delete_last_meal",
            "description": "Удаляет последний приём пищи за сегодня. Используй когда пользователь просит отменить или удалить последнюю запись.",
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
            "name": "analyze_meal_quality",
            "description": (
                "Анализирует качество питания за сегодня: баланс БЖУ, достаточность калорий, "
                "пропущенные приёмы пищи, проблемные нутриенты. "
                "Используй когда пользователь спрашивает 'как я питался?', 'всё ли нормально?', "
                "'что не так с моим питанием?', 'оцени мой день'."
            ),
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
            "name": "suggest_meal",
            "description": (
                "Предлагает что съесть исходя из остатка КБЖУ на сегодня. "
                "Используй когда пользователь спрашивает 'что поесть?', 'что бы съесть на ужин?', "
                "'что мне ещё можно?', 'посоветуй что-нибудь'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack", "any"],
                        "description": "Тип приёма пищи для которого нужна рекомендация"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_with_yesterday",
            "description": (
                "Сравнивает питание сегодня со вчерашним днём. "
                "Используй когда пользователь спрашивает 'лучше чем вчера?', 'как я питаюсь в динамике?', "
                "'сравни с вчера'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"}
                },
                "required": ["user_id"]
            }
        }
    }
]

# ─── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — персональный нутриционист и пищевой трекер в Telegram. Тебя зовут Калори.

━━━ ЧТО ТЫ УМЕЕШЬ ━━━
- Логировать еду по тексту ("съел гречку 200г с курицей") или фото
- Считать КБЖУ и остаток до дневной нормы
- Анализировать качество питания за день — баланс, пропуски, проблемы
- Предлагать что съесть исходя из остатка нутриентов
- Показывать статистику за день и неделю
- Сравнивать сегодня со вчера
- Удалять последнюю запись если ошибся

━━━ КАК ТЫ ОБЩАЕШЬСЯ ━━━
- Коротко и по делу, без воды и капитанства
- Если пользователь просто болтает или задаёт общий вопрос — отвечаешь как человек, не превращаешь каждое сообщение в задачу трекинга
- Если спрашивают что ты умеешь — отвечаешь списком из блока выше
- Можешь иногда сам замечать паттерны: "кстати, сегодня ты ещё не ел белка"
- Если данных нет — честно говоришь об этом, не выдумываешь

━━━ ПРАВИЛА ЛОГИРОВАНИЯ ━━━
- Всегда сохраняй еду в базу после анализа (save_meal)
- Тип приёма пищи определяй по времени суток или из контекста, не спрашивай если очевидно
- Если несколько продуктов — суммируй КБЖУ и сохраняй одной записью с общим названием
- После сохранения всегда показывай остаток до нормы если у пользователя есть цель

━━━ ФОРМАТ ПОСЛЕ ЛОГИРОВАНИЯ ━━━
✅ [Название] — [калории] ккал
Б: [белки]г | Ж: [жиры]г | У: [углеводы]г
До нормы осталось [X] ккал  ← только если есть цель

━━━ ВАЖНО ━━━
Ты работаешь с реальными данными из базы. Никогда не выдумывай цифры.
Если данных нет — скажи об этом прямо.
"""

# ─── Tool executors ────────────────────────────────────────────────────────────

async def _tool_analyze_food_text(args: dict) -> dict:
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

    if isinstance(data, list):
        return {
            "name": ", ".join(d.get("name", "") for d in data),
            "weight": sum(d.get("weight", 0) for d in data),
            "calories": sum(d.get("calories", 0) for d in data),
            "protein": sum(d.get("protein", 0) for d in data),
            "fat": sum(d.get("fat", 0) for d in data),
            "carbs": sum(d.get("carbs", 0) for d in data),
            "items": data
        }
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
    """
    Собирает данные за сегодня + цель и возвращает структурированный анализ.
    Сам агент (LLM) потом сформулирует ответ пользователю на основе этих данных.
    """
    today_data = await _tool_get_today_meals(args)
    goal_data = await _tool_get_user_goal(args)

    totals = today_data["totals"]
    meals = today_data["meals"]
    goal = goal_data

    # Считаем % выполнения по каждому нутриенту
    def pct(actual, target):
        return round((actual / target * 100) if target else 0, 1)

    cal_pct = pct(totals["calories"], goal["calories"])
    prot_pct = pct(totals["protein"], goal["protein"])
    fat_pct = pct(totals["fat"], goal["fat"])
    carb_pct = pct(totals["carbs"], goal["carbs"])

    # Определяем типы приёмов пищи которые были
    meal_types_logged = list({m["meal_type"] for m in meals})
    all_types = ["breakfast", "lunch", "dinner", "snack"]
    missing_types = [t for t in ["breakfast", "lunch", "dinner"] if t not in meal_types_logged]

    # Проблемы
    issues = []
    if cal_pct < 50:
        issues.append("критически мало калорий")
    elif cal_pct < 80:
        issues.append("недобор калорий")
    elif cal_pct > 120:
        issues.append("перебор калорий")

    if prot_pct < 70:
        issues.append(f"мало белка ({totals['protein']}г из {goal['protein']}г)")
    if fat_pct > 130:
        issues.append(f"перебор жиров ({totals['fat']}г при норме {goal['fat']}г)")
    if carb_pct > 130:
        issues.append(f"перебор углеводов ({totals['carbs']}г при норме {goal['carbs']}г)")

    return {
        "totals": totals,
        "goal": goal,
        "percentages": {
            "calories": cal_pct,
            "protein": prot_pct,
            "fat": fat_pct,
            "carbs": carb_pct
        },
        "meals_count": len(meals),
        "meal_types_logged": meal_types_logged,
        "missing_main_meals": missing_types,
        "issues": issues,
        "meals_list": [m["name"] for m in meals]
    }


async def _tool_suggest_meal(args: dict) -> dict:
    """
    Считает остаток КБЖУ и возвращает данные для рекомендации.
    LLM сам придумает конкретные блюда на основе остатка.
    """
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

    meal_type = args.get("meal_type", "any")

    # Определяем что уже ели сегодня чтобы не повторяться
    already_eaten = [m["name"] for m in today_data["meals"]]

    return {
        "remaining_nutrients": remaining,
        "meal_type_requested": meal_type,
        "already_eaten_today": already_eaten,
        "goal": goal,
        "totals_so_far": totals
    }


async def _tool_compare_with_yesterday(args: dict) -> dict:
    """Сравнивает сегодня и вчера по КБЖУ"""
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
                    Meal.user_id == args["user_id"],
                    Meal.date == date_str
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

    def delta(a, b):
        return round(a - b, 1)

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


# ─── Tool dispatcher ───────────────────────────────────────────────────────────

TOOL_EXECUTORS = {
    "analyze_food_text": _tool_analyze_food_text,
    "get_today_meals": _tool_get_today_meals,
    "get_user_goal": _tool_get_user_goal,
    "save_meal": _tool_save_meal,
    "get_week_summary": _tool_get_week_summary,
    "delete_last_meal": _tool_delete_last_meal,
    "analyze_meal_quality": _tool_analyze_meal_quality,
    "suggest_meal": _tool_suggest_meal,
    "compare_with_yesterday": _tool_compare_with_yesterday,
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


# ─── ReAct loop ────────────────────────────────────────────────────────────────

async def run_agent(
    user_id: int,
    message: str,
    history: list[dict],
    photo_base64: str | None = None
) -> str:
    client = AsyncGroq(api_key=GROQ_API_KEY)

    if photo_base64:
        vision_result = await _analyze_photo_with_vision(client, photo_base64, message)
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

    max_iterations = 8

    for _ in range(max_iterations):
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.4,
            max_tokens=1200
        )

        choice = response.choices[0]

        if choice.finish_reason == "stop" or not choice.message.tool_calls:
            return choice.message.content or "Готово."

        tool_calls = choice.message.tool_calls

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


async def _analyze_photo_with_vision(client: AsyncGroq, photo_base64: str, hint: str = "") -> str:
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
