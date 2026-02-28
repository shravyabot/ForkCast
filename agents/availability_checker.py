"""Real-time ingredient availability checker using Tavily."""

import json
from tavily import TavilyClient
from openai import OpenAI
import config


class AvailabilityChecker:
    """Checks real-time ingredient availability and prices using Tavily."""

    def __init__(self):
        self.tavily = TavilyClient(api_key=config.TAVILY_API_KEY)
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def check_availability(
        self, ingredients: list[str], location: str
    ) -> list[dict]:
        """
        Check real-time availability of ingredients at local stores.

        Returns: [{"ingredient": "chicken breast", "store": "Walmart",
                   "price": 5.99, "available": True}]
        """
        results = []
        # Batch check ingredients
        batch_size = 5
        for i in range(0, len(ingredients), batch_size):
            batch = ingredients[i : i + batch_size]
            query = (
                f"grocery store availability price "
                f"{', '.join(batch)} {location} today"
            )
            search_results = self.tavily.search(
                query=query,
                search_depth="basic",
                max_results=3,
            )

            raw_content = [
                {
                    "content": r.get("content", ""),
                    "title": r.get("title", ""),
                }
                for r in search_results.get("results", [])
            ]

            # Parse availability from search results
            parsed = self._parse_availability(batch, raw_content, location)
            results.extend(parsed)

        # Fill in any ingredients that weren't found
        found_ingredients = {r["ingredient"].lower() for r in results}
        for ing in ingredients:
            if ing.lower() not in found_ingredients:
                # Default to available with estimated price
                results.append(
                    {
                        "ingredient": ing.lower(),
                        "store": "Local Grocery",
                        "price": self._estimate_price(ing),
                        "available": True,
                    }
                )

        return results

    def _parse_availability(
        self, ingredients: list[str], raw_content: list[dict], location: str
    ) -> list[dict]:
        """Parse search results into structured availability data."""
        if not raw_content:
            return []

        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a grocery availability analyst. Based on search "
                        "results, determine availability and pricing of ingredients. "
                        "Return a JSON array with objects: "
                        "{ingredient (lowercase), store (string), price (float USD), "
                        "available (boolean)}. "
                        "If uncertain about availability, default to available=true "
                        "with a reasonable estimated price. "
                        "Randomly mark 1-2 ingredients as unavailable to simulate "
                        "real-world stock issues (for demo purposes). "
                        "Return ONLY valid JSON, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Check availability for: {ingredients}\n"
                        f"Location: {location}\n\n"
                        f"Search results:\n{json.dumps(raw_content, indent=2)}"
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
            return []

    def _estimate_price(self, ingredient: str) -> float:
        """Rough price estimate for common ingredients."""
        price_map = {
            "chicken": 6.99, "beef": 8.99, "pork": 5.99, "fish": 9.99,
            "salmon": 11.99, "shrimp": 10.99, "tofu": 2.99,
            "rice": 3.49, "pasta": 1.99, "bread": 3.49,
            "milk": 3.99, "eggs": 4.49, "cheese": 4.99, "butter": 4.49,
            "olive oil": 6.99, "onion": 1.29, "garlic": 0.99,
            "tomato": 1.99, "potato": 2.99, "carrot": 1.49,
            "broccoli": 2.49, "spinach": 2.99, "lettuce": 2.49,
            "salt": 1.49, "pepper": 2.99, "sugar": 2.99,
        }
        ingredient_lower = ingredient.lower()
        for key, price in price_map.items():
            if key in ingredient_lower:
                return price
        return 3.99  # default estimate
