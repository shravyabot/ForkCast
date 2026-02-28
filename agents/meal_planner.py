"""Meal planning agent using OpenAI for optimization and adaptation."""

import json
from openai import OpenAI
import config


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEAL_TYPES = ["breakfast", "lunch", "dinner"]


class MealPlanner:
    """Creates and adapts weekly meal plans using OpenAI."""

    def __init__(self):
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def create_meal_plan(
        self,
        recipes: list[dict],
        dietary_preferences: str,
        household_size: int,
        budget: float,
        existing_ingredients: list[str] | None = None,
    ) -> list[dict]:
        """
        Create a 7-day meal plan from available recipes.
        Optimizes for shared ingredients and variety.

        Returns: [{"day": "Monday", "meal_type": "breakfast", "recipe": "..."}]
        """
        recipe_names = [r["name"] for r in recipes]
        recipe_summary = json.dumps(
            [
                {
                    "name": r["name"],
                    "cuisine": r.get("cuisine", ""),
                    "prep_time": r.get("prep_time", 0),
                    "ingredients": [i["name"] for i in r.get("ingredients", [])],
                }
                for r in recipes
            ],
            indent=2,
        )

        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a meal planning expert. Create a 7-day meal plan "
                        "(breakfast, lunch, dinner) from the given recipes. "
                        "RULES:\n"
                        "1. Maximize ingredient sharing across meals to reduce waste\n"
                        "2. Ensure variety - don't repeat the same recipe in 2 days\n"
                        "3. Balance cuisines across the week\n"
                        "4. Keep prep time reasonable for breakfast (< 20 min)\n"
                        "5. Use ONLY recipes from the provided list\n"
                        "Return a JSON array of objects with: day, meal_type, recipe_name. "
                        "Days: Monday-Sunday. meal_type: breakfast/lunch/dinner. "
                        "Return ONLY valid JSON, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Create a meal plan for {household_size} people, "
                        f"budget ${budget}/week, preferences: {dietary_preferences}.\n\n"
                        f"Available recipes:\n{recipe_summary}"
                        + (
                            f"\n\nPRIORITY: The user already has these ingredients at home. "
                            f"Strongly prefer recipes that use these: {existing_ingredients}"
                            if existing_ingredients
                            else ""
                        )
                    ),
                },
            ],
            temperature=0.7,
        )

        try:
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            plan = json.loads(text)
            # Validate recipe names
            valid_plan = []
            for entry in plan:
                if entry.get("recipe_name") in recipe_names:
                    valid_plan.append(entry)
                else:
                    # Find closest match
                    for rn in recipe_names:
                        if rn.lower() in entry.get("recipe_name", "").lower() or \
                           entry.get("recipe_name", "").lower() in rn.lower():
                            entry["recipe_name"] = rn
                            valid_plan.append(entry)
                            break
            return valid_plan
        except (json.JSONDecodeError, IndexError):
            return []

    def suggest_substitution(
        self,
        unavailable_ingredient: str,
        affected_recipes: list[str],
        dietary_preferences: str,
    ) -> dict:
        """
        Suggest a substitute ingredient or replacement recipe when
        an ingredient is unavailable.

        Returns: {"action": "substitute"/"replace", "substitute_ingredient": "...",
                  "replacement_recipe": {...}, "reasoning": "..."}
        """
        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a culinary expert. An ingredient is unavailable. "
                        "Suggest either:\n"
                        "1. A substitute ingredient (preferred if the dish still works)\n"
                        "2. A completely new replacement recipe\n\n"
                        "Return JSON with:\n"
                        "- action: 'substitute' or 'replace'\n"
                        "- substitute_ingredient: string (if substitute)\n"
                        "- replacement_recipe: {name, cuisine, prep_time, instructions, "
                        "  ingredients: [{name, quantity}]} (if replace)\n"
                        "- reasoning: brief explanation\n"
                        "Return ONLY valid JSON, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Unavailable ingredient: {unavailable_ingredient}\n"
                        f"Affected recipes: {affected_recipes}\n"
                        f"Dietary preferences: {dietary_preferences}\n\n"
                        f"What should we do?"
                    ),
                },
            ],
            temperature=0.5,
        )

        try:
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return {
                "action": "substitute",
                "substitute_ingredient": f"alternative to {unavailable_ingredient}",
                "reasoning": "Could not determine best substitution.",
            }
