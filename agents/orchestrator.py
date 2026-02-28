"""Main orchestrator agent that runs the full autonomous pipeline."""

from dataclasses import dataclass, field
from agents.recipe_searcher import RecipeSearcher
from agents.meal_planner import MealPlanner
from agents.graph_manager import GraphManager
from agents.availability_checker import AvailabilityChecker
from agents.order_placer import OrderPlacer


@dataclass
class PipelineState:
    """Tracks the state of the autonomous pipeline."""

    status: str = "idle"
    step: str = ""
    logs: list[str] = field(default_factory=list)
    recipes: list[dict] = field(default_factory=list)
    meal_plan: list[dict] = field(default_factory=list)
    availability: list[dict] = field(default_factory=list)
    unavailable_items: list[str] = field(default_factory=list)
    adaptations: list[dict] = field(default_factory=list)
    shopping_list: list[dict] = field(default_factory=list)
    consolidated_order: dict = field(default_factory=dict)
    order_confirmation: dict = field(default_factory=dict)
    error: str = ""

    def log(self, message: str):
        self.logs.append(message)


class Orchestrator:
    """
    Coordinates the full Chef's Table pipeline autonomously.

    Flow:
    1. Search recipes (Tavily + OpenAI)
    2. Create meal plan (OpenAI)
    3. Build dependency graph (Neo4j)
    4. Check availability (Tavily)
    5. Adapt if needed (OpenAI + Neo4j) — loops until plan is valid
    6. Generate & place order
    """

    def __init__(self):
        self.recipe_searcher = RecipeSearcher()
        self.meal_planner = MealPlanner()
        self.graph = GraphManager()
        self.availability_checker = AvailabilityChecker()
        self.order_placer = OrderPlacer()

    def run(
        self,
        dietary_preferences: str,
        cuisine_preferences: str,
        household_size: int,
        budget: float,
        location: str,
        state: PipelineState | None = None,
    ) -> PipelineState:
        """Run the full autonomous pipeline."""
        if state is None:
            state = PipelineState()

        state.status = "running"

        try:
            # Step 1: Search for recipes
            state.step = "searching_recipes"
            state.log("🔍 Searching for recipes matching your preferences...")
            state.recipes = self.recipe_searcher.search_recipes(
                dietary_preferences=dietary_preferences,
                cuisine_preferences=cuisine_preferences,
                num_recipes=14,
            )
            state.log(f"✅ Found {len(state.recipes)} recipes")

            if not state.recipes:
                state.error = "No recipes found. Try different preferences."
                state.status = "error"
                return state

            # Step 2: Create meal plan
            state.step = "creating_meal_plan"
            state.log("📅 Creating optimized weekly meal plan...")
            state.meal_plan = self.meal_planner.create_meal_plan(
                recipes=state.recipes,
                dietary_preferences=dietary_preferences,
                household_size=household_size,
                budget=budget,
            )
            state.log(f"✅ Meal plan created with {len(state.meal_plan)} meals")

            # Step 3: Build the dependency graph
            state.step = "building_graph"
            state.log("🕸️ Building ingredient dependency graph in Neo4j...")
            self.graph.clear_graph()
            for recipe in state.recipes:
                self.graph.add_recipe(recipe)
            for entry in state.meal_plan:
                self.graph.schedule_recipe(
                    day=entry["day"],
                    meal_type=entry["meal_type"],
                    recipe_name=entry["recipe_name"],
                )
            state.log("✅ Graph built with recipes, ingredients, and schedule")

            # Step 4: Check availability
            state.step = "checking_availability"
            state.log("🏪 Checking real-time ingredient availability...")
            all_ingredients = list(
                {
                    ing["name"].lower()
                    for recipe in state.recipes
                    for ing in recipe.get("ingredients", [])
                }
            )
            state.availability = self.availability_checker.check_availability(
                ingredients=all_ingredients,
                location=location,
            )

            # Store availability in graph
            for item in state.availability:
                self.graph.set_ingredient_availability(
                    ingredient_name=item["ingredient"],
                    store=item.get("store", "Local Grocery"),
                    price=item.get("price", 3.99),
                    available=item.get("available", True),
                )

            state.unavailable_items = [
                item["ingredient"]
                for item in state.availability
                if not item.get("available", True)
            ]
            state.log(
                f"✅ Availability checked: "
                f"{len(all_ingredients) - len(state.unavailable_items)}/{len(all_ingredients)} "
                f"ingredients available"
            )

            # Step 5: Adapt if needed
            if state.unavailable_items:
                state.step = "adapting"
                state.log(
                    f"⚠️ {len(state.unavailable_items)} unavailable: "
                    f"{', '.join(state.unavailable_items)}"
                )
                state.log("🔄 Autonomously adapting meal plan...")

                for ingredient in state.unavailable_items:
                    affected = self.graph.get_affected_recipes(ingredient)
                    if not affected:
                        continue

                    state.log(
                        f"  → '{ingredient}' affects: {', '.join(affected)}"
                    )

                    suggestion = self.meal_planner.suggest_substitution(
                        unavailable_ingredient=ingredient,
                        affected_recipes=affected,
                        dietary_preferences=dietary_preferences,
                    )

                    state.adaptations.append(
                        {
                            "ingredient": ingredient,
                            "affected_recipes": affected,
                            "suggestion": suggestion,
                        }
                    )

                    if suggestion.get("action") == "substitute":
                        sub = suggestion.get("substitute_ingredient", "")
                        self.graph.add_substitution(ingredient, sub)
                        state.log(
                            f"  ✅ Substituted '{ingredient}' → '{sub}': "
                            f"{suggestion.get('reasoning', '')}"
                        )
                        # Set the substitute as available
                        self.graph.set_ingredient_availability(
                            ingredient_name=sub,
                            store="Local Grocery",
                            price=3.99,
                            available=True,
                        )
                    elif suggestion.get("action") == "replace":
                        new_recipe = suggestion.get("replacement_recipe", {})
                        if new_recipe:
                            self.graph.add_recipe(new_recipe)
                            state.log(
                                f"  ✅ Replaced recipe with '{new_recipe.get('name', 'new recipe')}': "
                                f"{suggestion.get('reasoning', '')}"
                            )

                state.log("✅ Adaptation complete — meal plan is now valid")

            # Step 6: Generate shopping list and place order
            state.step = "placing_order"
            state.log("🛒 Generating consolidated shopping list...")
            state.shopping_list = self.graph.get_shopping_list()

            state.log("💳 Consolidating order and optimizing by store...")
            state.consolidated_order = self.order_placer.consolidate_order(
                shopping_list=state.shopping_list,
                household_size=household_size,
            )

            state.log("📦 Placing grocery order...")
            state.order_confirmation = self.order_placer.place_order(
                state.consolidated_order
            )
            state.log(
                f"✅ {state.order_confirmation.get('confirmation_message', 'Order placed!')}"
            )

            state.status = "complete"
            state.step = "done"

        except Exception as e:
            state.error = str(e)
            state.status = "error"
            state.log(f"❌ Error: {e}")

        return state

    def close(self):
        """Clean up resources."""
        self.graph.close()
