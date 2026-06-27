import os
import json
import hmac
import hashlib
from datetime import datetime
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, and_

from database import async_session
from models import User, Meal, Goal
from config import TELEGRAM_TOKEN

app = FastAPI(title="CaloriV2 Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


def verify_init_data(init_data: str) -> dict | None:
    """Проверяем HMAC-подпись Telegram WebApp initData"""
    try:
        parsed = parse_qs(init_data)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        items = sorted([f"{k}={v[0]}" for k, v in parsed.items() if k != "hash"])
        data_check_string = "\n".join(items)

        secret_key = hmac.new(
            b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash == received_hash:
            user_json = parsed.get("user", [None])[0]
            if user_json:
                return json.loads(user_json)
        return None
    except Exception:
        return None


# ==================== СТРАНИЦЫ ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")


# ==================== API ====================

@app.get("/api/me")
async def get_me(init_data: str = Query(None)):
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data required")
    user_data = verify_init_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid init data")

    telegram_id = user_data.get("id")
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": db_user.id,
            "telegram_id": db_user.telegram_id,
            "first_name": db_user.first_name,
            "username": db_user.username,
            "is_pro": db_user.is_pro,
        }


@app.get("/api/stats/{telegram_id}")
async def get_stats(telegram_id: int, date: str = Query(None)):
    target_date = date or datetime.now().strftime("%Y-%m-%d")

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        result = await session.execute(
            select(Goal).where(Goal.user_id == db_user.id)
        )
        goal = result.scalar_one_or_none()

        result = await session.execute(
            select(
                func.sum(Meal.calories),
                func.sum(Meal.protein),
                func.sum(Meal.fat),
                func.sum(Meal.carbs),
            ).where(and_(Meal.user_id == db_user.id, Meal.date == target_date))
        )
        total = result.first()

        result = await session.execute(
            select(Meal.meal_type, func.sum(Meal.calories))
            .where(and_(Meal.user_id == db_user.id, Meal.date == target_date))
            .group_by(Meal.meal_type)
        )
        meal_stats = {row[0]: row[1] or 0 for row in result.all()}

        return {
            "date": target_date,
            "calories": total[0] or 0,
            "protein": total[1] or 0,
            "fat": total[2] or 0,
            "carbs": total[3] or 0,
            "goal": {
                "calories": goal.calories if goal else 2000,
                "protein": goal.protein if goal else 100,
                "fat": goal.fat if goal else 70,
                "carbs": goal.carbs if goal else 250,
            },
            "by_meal_type": meal_stats,
        }


@app.get("/api/meals/{telegram_id}")
async def get_meals(telegram_id: int, date: str = Query(None)):
    target_date = date or datetime.now().strftime("%Y-%m-%d")

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        result = await session.execute(
            select(Meal)
            .where(and_(Meal.user_id == db_user.id, Meal.date == target_date))
            .order_by(Meal.created_at.desc())
        )
        meals = result.scalars().all()

        return [
            {
                "id": m.id,
                "name": m.name,
                "weight": m.weight,
                "calories": m.calories,
                "protein": m.protein,
                "fat": m.fat,
                "carbs": m.carbs,
                "meal_type": m.meal_type,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in meals
        ]


@app.get("/api/goal/{telegram_id}")
async def get_goal(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        result = await session.execute(
            select(Goal).where(Goal.user_id == db_user.id)
        )
        goal = result.scalar_one_or_none()
        if not goal:
            goal = Goal(user_id=db_user.id)
            session.add(goal)
            await session.commit()

        return {
            "calories": goal.calories,
            "protein": goal.protein,
            "fat": goal.fat,
            "carbs": goal.carbs,
        }
