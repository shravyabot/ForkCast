"""Recipe and grocery deal search agent using Tavily."""

import json
from tavily import TavilyClient
from openai import OpenAI
import config


class RecipeSearcher:
    """Searches for recipes and grocery deals using Tavily."""

    def __init__(self):
        self.tavily = TavilyClient(api_key=config.TAVILY_API_KEY)
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def search_recipes(
        self,
        dietary_preferences: str,
        cuisine_preferences: str = "",
        num_recipes: int = 14,
    ) -> list[dict]:
        """
        Search for recipes matching dietary preferences.
        Returns structured recipe data parsed by OpenAI.
        """
        queries = self._build_recipe_queries(dietary_preferences, cuisine_preferences)
        raw_results = []

        for query in queries:
            results = self.tavily.search(
                query=query,
                search_depth="advanced",
                max_results=5,
            )
            for result in results.get("results", []):
                raw_results.append(
                    {
                        "title": result.get("title", ""),
                        "content": result.get("content", ""),
                        "url": result.get("url", ""),
                    }
                )

        # Use OpenAI to parse raw search results into structured recipes
        recipes = self._parse_recipes(raw_results, dietary_preferences, num_recipes)
        return recipes

    def search_grocery_deals(self, location: str, ingredients: list[str]) -> list[dict]:
        """Search for grocery deals on specific ingredients near a location."""
        deals = []
        # Batch ingredients into groups to minimize API calls
        batch_size = 5
        for i in range(0, len(ingredients), batch_size):
            batch = ingredients[i : i + batch_size]
            query = f"grocery deals prices {' '.join(batch)} near {location}"
            results = self.tavily.search(
                query=query,
                search_depth="basic",
                max_results=3,
            )
            for result in results.get("results", []):
                deals.append(
                    {
                        "content": result.get("content", ""),
                        "url": result.get("url", ""),
                        "title": result.get("title", ""),
                    }
                )

        # Parse deals into structured format
        parsed_deals = self._parse_deals(deals, ingredients)
        return parsed_deals

    def _build_recipe_queries(
        self, dietary_preferences: str, cuisine_preferences: str
    ) -> list[str]:
        """Build search queries strictly filtered by cuisine preferences."""
        base = f"{dietary_preferences} recipes"
        if cuisine_preferences:
            # ALL queries must include cuisine to enforce the preference
            cuisines = [c.strip() for c in cuisine_preferences.split(",")]
            queries = []
            for cuisine in cuisines:
                queries.append(f"easy {cuisine} {base} with common ingredients")
                queries.append(f"budget friendly {cuisine} {base} dinner lunch breakfast")
            return queries[:4]  # cap at 4 queries
        return [
            f"easy {base} with common ingredients",
            f"healthy {base} meal prep weekly",
            f"budget friendly {base} dinner ideas",
        ]

    def _parse_recipes(
        self, raw_results: list[dict], preferences: str, num_recipes: int
    ) -> list[dict]:
        """Use OpenAI to extract structured recipe data from search results."""
        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a recipe parser. Extract structured recipe data from "
                        "search results. Return a JSON array of recipe objects. Each "
                        "recipe must have: name, cuisine, prep_time (minutes as int), "
                        "instructions (brief), ingredients (array of {name, quantity}). "
                        "STRICT RULES:\n"
                        "- Ensure ingredients use common names (e.g., 'chicken breast' "
                        "not 'boneless skinless chicken breast halves').\n"
                        "- Maximize ingredient overlap between recipes to reduce waste.\n"
                        "- Keep each recipe to 6-8 ingredients MAX (simple, practical recipes).\n"
                        "- Include a mix of breakfast, lunch, and dinner-appropriate recipes.\n"
                        "Return ONLY valid JSON, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Extract {num_recipes} diverse recipes from these search results "
                        f"that fit '{preferences}' dietary preferences. "
                        f"IMPORTANT: ALL recipes MUST strictly belong to the specified "
                        f"cuisine(s). Do NOT include recipes from other cuisines. "
                        f"Maximize shared ingredients across recipes.\n\n"
                        f"Search results:\n{json.dumps(raw_results[:20], indent=2)}"
                    ),
                },
            ],
            temperature=0.7,
        )
        try:
            text = response.choices[0].message.content.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return []

    def _parse_deals(
        self, raw_deals: list[dict], ingredients: list[str]
    ) -> list[dict]:
        """Use OpenAI to parse grocery deals into structured format."""
        if not raw_deals:
            return []

        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a grocery deal parser. Extract pricing info from "
                        "search results. Return a JSON array of objects with: "
                        "ingredient (lowercase), store, price (float in USD), "
                        "available (boolean). If you can't determine a price, "
                        "estimate a reasonable one. Return ONLY valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Parse deals for these ingredients: {ingredients}\n\n"
                        f"Search results:\n{json.dumps(raw_deals[:10], indent=2)}"
                    ),
                },
            ],
            temperature=0.3,
        )
        try:
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return []
