def validate_meal_data(data: dict):
    required = ["name", "weight", "calories", "protein", "fat", "carbs"]
    if not all(f in data for f in required):
        return None
    try:
        return {
            "name": str(data["name"]),
            "weight": float(data["weight"]),
            "calories": float(data["calories"]),
            "protein": float(data["protein"]),
            "fat": float(data["fat"]),
            "carbs": float(data["carbs"]),
        }
    except:
        return None