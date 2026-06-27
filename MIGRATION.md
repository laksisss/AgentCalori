# CaloriV2 → Agent Migration

## Что изменилось

### Новые файлы
- `agent.py` — ядро агента: ReAct loop + tool calling через Groq
- `memory.py` — хранение истории диалога per user
- `handlers/agent_handler.py` — единый обработчик текста и фото

### Изменённые файлы
- `bot.py` — убраны ConversationHandler, добавлен agent_handler и /clear команда

### Удалить можно (больше не нужны)
- `handlers/meal.py`
- `handlers/photo.py`
- `ai_service.py` — логика перенесена в agent.py

---

## Как задеплоить

1. Скопируй `agent.py`, `memory.py` в корень репо
2. Скопируй `handlers/agent_handler.py` в папку `handlers/`
3. Замени `bot.py` целиком
4. Задеплой на Railway — остальные файлы не трогай

---

## Что умеет агент

| Действие пользователя | Что делает агент |
|---|---|
| "съел гречку 200г с курицей" | analyze_food_text → save_meal → ответ с КБЖУ |
| [отправил фото еды] | vision анализ → save_meal → ответ с КБЖУ |
| "как я питался сегодня?" | get_today_meals → get_user_goal → сравнение |
| "покажи статистику за неделю" | get_week_summary → анализ динамики |
| "удали последнее" | delete_last_meal → подтверждение |
| "сколько мне ещё можно съесть?" | get_today_meals + get_user_goal → остаток |

---

## Новая команда

`/clear` — сбрасывает историю диалога. Полезно если агент "запутался".

---

## Инструменты агента (tools)

- `analyze_food_text` — парсит текст в КБЖУ (Llama 3.3 70b)
- `get_today_meals` — достаёт приёмы пищи за сегодня из БД
- `get_user_goal` — цели пользователя
- `save_meal` — сохраняет в БД
- `get_week_summary` — сводка за 7 дней
- `delete_last_meal` — удаление последней записи

---

## Как добавить новый tool

1. В `agent.py` добавь описание в список `TOOLS`
2. Напиши `async def _tool_имя(args: dict) -> dict`
3. Добавь в `TOOL_EXECUTORS`

Агент начнёт использовать его автоматически.

---

## Известные ограничения

- История диалога хранится в памяти — сбрасывается при рестарте Railway
- Фото обрабатываются через vision → текст → агент (два LLM вызова)
- Max 8 итераций в ReAct loop (защита от бесконечного цикла)
