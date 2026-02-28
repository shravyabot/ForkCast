"""Calorie tracking agent with goals, personalization, and smart suggestions."""

import json
import base64
from datetime import datetime
from openai import OpenAI
import config


# Goal presets
GOAL_PRESETS = {
    "weight_loss": {"calorie_factor": 0.8, "protein_per_kg": 2.0, "label": "Weight Loss"},
    "maintenance": {"calorie_factor": 1.0, "protein_per_kg": 1.6, "label": "Maintenance"},
    "muscle_gain": {"calorie_factor": 1.15, "protein_per_kg": 2.2, "label": "Muscle Gain"},
}


def calculate_targets(weight_kg: float, height_cm: float, age: int, gender: str, goal: str, activity_level: str) -> dict:
    """Calculate personalized calorie and macro targets using Mifflin-St Jeor."""
    if gender == "Male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    activity_multipliers = {
        "Sedentary": 1.2,
        "Lightly Active": 1.375,
        "Moderately Active": 1.55,
        "Very Active": 1.725,
        "Extremely Active": 1.9,
    }
    tdee = bmr * activity_multipliers.get(activity_level, 1.55)

    preset = GOAL_PRESETS.get(goal, GOAL_PRESETS["maintenance"])
    calorie_target = int(tdee * preset["calorie_factor"])
    protein_target = int(weight_kg * preset["protein_per_kg"])
    fat_target = int(calorie_target * 0.25 / 9)
    carb_target = int((calorie_target - protein_target * 4 - fat_target * 9) / 4)

    return {
        "calorie_target": calorie_target,
        "protein_target": protein_target,
        "carb_target": max(carb_target, 50),
        "fat_target": fat_target,
        "bmr": int(bmr),
        "tdee": int(tdee),
    }


class CalorieTracker:
    """Analyzes food images and descriptions to estimate calories and macros."""

    def __init__(self):
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def analyze_meal(
        self,
        image_bytes: bytes | None = None,
        description: str = "",
        goal: str = "maintenance",
        remaining_calories: int | None = None,
    ) -> dict:
        """Analyze a meal from an image and/or description."""
        goal_context = ""
        if remaining_calories is not None:
            goal_context = (
                f"\n\nUser's goal: {GOAL_PRESETS.get(goal, {}).get('label', goal)}. "
                f"Remaining calorie budget today: {remaining_calories} cal. "
                f"Include a note about whether this meal fits their budget."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert nutritionist and food analyst. "
                    "Analyze the meal provided (from image and/or description) and "
                    "estimate detailed nutritional information.\n\n"
                    "Return a JSON object with:\n"
                    "- meal_name: string\n"
                    "- items: array of {name, portion, calories (int), "
                    "  protein (g, int), carbs (g, int), fat (g, int), "
                    "  fiber (g, int), sodium (mg, int), sugar (g, int)}\n"
                    "- total_calories: int\n"
                    "- total_protein: int (grams)\n"
                    "- total_carbs: int (grams)\n"
                    "- total_fat: int (grams)\n"
                    "- total_fiber: int (grams)\n"
                    "- total_sodium: int (mg)\n"
                    "- total_sugar: int (grams)\n"
                    "- health_score: float (1-10)\n"
                    "- sodium_warning: boolean (true if >800mg)\n"
                    "- sugar_warning: boolean (true if >25g)\n"
                    "- notes: string (health tips)"
                    + goal_context
                    + "\nReturn ONLY valid JSON, no markdown."
                ),
            }
        ]

        user_content = []
        if image_bytes:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}",
                        "detail": "high",
                    },
                }
            )

        text_prompt = "Analyze this meal and provide nutritional breakdown."
        if description:
            text_prompt += f"\n\nMeal description: {description}"
        if not image_bytes:
            text_prompt += "\n\nNo image provided — estimate based on the description only."

        user_content.append({"type": "text", "text": text_prompt})
        messages.append({"role": "user", "content": user_content})

        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            max_tokens=1000,
            temperature=0.3,
        )

        try:
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
            result["analyzed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return result
        except (json.JSONDecodeError, IndexError):
            return {
                "meal_name": description or "Unknown meal",
                "items": [],
                "total_calories": 0, "total_protein": 0, "total_carbs": 0,
                "total_fat": 0, "total_fiber": 0, "total_sodium": 0,
                "total_sugar": 0, "health_score": 0,
                "sodium_warning": False, "sugar_warning": False,
                "notes": "Could not analyze this meal.",
                "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def suggest_next_meal(
        self,
        remaining_calories: int,
        remaining_protein: int,
        remaining_carbs: int,
        remaining_fat: int,
        goal: str,
        dietary_preferences: str = "",
    ) -> str:
        """Suggest what to eat next based on remaining macros."""
        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a nutritionist. Suggest a specific meal based on "
                        "remaining macro budget. Be concise (2-3 sentences). "
                        "Include a specific meal idea with rough calorie count."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Goal: {GOAL_PRESETS.get(goal, {}).get('label', goal)}\n"
                        f"Remaining today: {remaining_calories} cal, "
                        f"{remaining_protein}g protein, {remaining_carbs}g carbs, "
                        f"{remaining_fat}g fat\n"
                        f"Preferences: {dietary_preferences or 'none specified'}"
                    ),
                },
            ],
            temperature=0.7,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()

    def get_daily_summary(self, meals: list[dict], targets: dict | None = None) -> dict:
        """Summarize daily intake with optional target comparison."""
        if not meals:
            return {
                "total_calories": 0, "total_protein": 0, "total_carbs": 0,
                "total_fat": 0, "total_fiber": 0, "total_sodium": 0,
                "total_sugar": 0, "meal_count": 0, "avg_health_score": 0,
            }

        totals = {
            "total_calories": sum(m.get("total_calories", 0) for m in meals),
            "total_protein": sum(m.get("total_protein", 0) for m in meals),
            "total_carbs": sum(m.get("total_carbs", 0) for m in meals),
            "total_fat": sum(m.get("total_fat", 0) for m in meals),
            "total_fiber": sum(m.get("total_fiber", 0) for m in meals),
            "total_sodium": sum(m.get("total_sodium", 0) for m in meals),
            "total_sugar": sum(m.get("total_sugar", 0) for m in meals),
            "meal_count": len(meals),
            "avg_health_score": round(
                sum(m.get("health_score", 0) for m in meals) / len(meals), 1
            ),
        }

        if targets:
            totals["calorie_remaining"] = targets["calorie_target"] - totals["total_calories"]
            totals["protein_remaining"] = targets["protein_target"] - totals["total_protein"]
            totals["carb_remaining"] = targets["carb_target"] - totals["total_carbs"]
            totals["fat_remaining"] = targets["fat_target"] - totals["total_fat"]

        return totals
