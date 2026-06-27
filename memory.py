"""
memory.py — управление историей диалога для каждого пользователя.

Хранит последние N сообщений в памяти процесса (dict).
При рестарте Railway история сбрасывается — это нормально для MVP.
Если хочешь персистентность — замени на Redis.
"""

from collections import defaultdict, deque

# user_id → deque of {"role": "user/assistant", "content": "..."}
_histories: dict[int, deque] = defaultdict(lambda: deque(maxlen=20))


def get_history(user_id: int) -> list[dict]:
    """Возвращает историю диалога пользователя"""
    return list(_histories[user_id])


def add_message(user_id: int, role: str, content: str) -> None:
    """Добавляет сообщение в историю"""
    if content:  # не добавляем пустые
        _histories[user_id].append({"role": role, "content": content})


def clear_history(user_id: int) -> None:
    """Очищает историю пользователя"""
    _histories[user_id].clear()


def get_history_length(user_id: int) -> int:
    return len(_histories[user_id])
