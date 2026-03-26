"""Neo4j graph manager for the meal plan dependency graph."""

from neo4j import GraphDatabase
import config


class GraphManager:
    """Manages the Neo4j recipe/ingredient/meal-plan graph."""

    def __init__(self):
        self.connected = False
        try:
            self.driver = GraphDatabase.driver(
                config.NEO4J_URI,
                auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
            )
            self.driver.verify_connectivity()
            self.database = config.NEO4J_DATABASE
            self.connected = True
        except Exception as e:
            self.driver = None
            self.database = None
            print(f"⚠️ Neo4j unavailable ({e}). Running without graph DB.")

    def close(self):
        if self.driver:
            self.driver.close()

    def _run(self, query, **kwargs):
        """Execute a query, returning empty result if disconnected."""
        if not self.connected:
            return [], None, None
        return self.driver.execute_query(query, database_=self.database, **kwargs)

    def clear_graph(self):
        """Remove all nodes and relationships (fresh start)."""
        self._run("MATCH (n) DETACH DELETE n")

    # ── Recipe & Ingredient nodes ──────────────────────────────────

    def add_recipe(self, recipe: dict):
        """
        Add a recipe and its ingredients to the graph.

        recipe = {
            "name": "Chicken Stir Fry",
            "cuisine": "Asian",
            "prep_time": 30,
            "instructions": "...",
            "ingredients": [
                {"name": "chicken breast", "quantity": "500g"},
                {"name": "soy sauce", "quantity": "2 tbsp"},
            ]
        }
        """
        self._run(
            """
            MERGE (r:Recipe {name: $name})
            SET r.cuisine = $cuisine,
                r.prep_time = $prep_time,
                r.instructions = $instructions
            """,
            name=recipe["name"],
            cuisine=recipe.get("cuisine", ""),
            prep_time=recipe.get("prep_time", 0),
            instructions=recipe.get("instructions", ""),
        )
        for ing in recipe.get("ingredients", []):
            self._run(
                """
                MERGE (i:Ingredient {name: $ing_name})
                WITH i
                MATCH (r:Recipe {name: $recipe_name})
                MERGE (r)-[req:REQUIRES]->(i)
                SET req.quantity = $quantity
                """,
                ing_name=ing["name"].lower(),
                recipe_name=recipe["name"],
                quantity=ing.get("quantity", ""),
            )

    # ── Meal Plan scheduling ───────────────────────────────────────

    def schedule_recipe(self, day: str, meal_type: str, recipe_name: str):
        """Schedule a recipe for a specific day and meal type."""
        self._run(
            """
            MERGE (d:Day {name: $day})
            MERGE (m:Meal {type: $meal_type, day: $day})
            MERGE (d)-[:HAS_MEAL]->(m)
            WITH m
            MATCH (r:Recipe {name: $recipe_name})
            MERGE (m)-[:SCHEDULED]->(r)
            """,
            day=day,
            meal_type=meal_type,
            recipe_name=recipe_name,
        )

    # ── Availability & Stores ──────────────────────────────────────

    def set_ingredient_availability(
        self, ingredient_name: str, store: str, price: float, available: bool
    ):
        """Record that an ingredient is available at a store with a price."""
        self._run(
            """
            MERGE (i:Ingredient {name: $ing_name})
            MERGE (s:Store {name: $store})
            MERGE (i)-[a:AVAILABLE_AT]->(s)
            SET a.price = $price, a.available = $available
            """,
            ing_name=ingredient_name.lower(),
            store=store,
            price=price,
            available=available,
        )

    def mark_unavailable(self, ingredient_name: str):
        """Mark an ingredient as unavailable at all stores."""
        self._run(
            """
            MATCH (i:Ingredient {name: $ing_name})-[a:AVAILABLE_AT]->(s)
            SET a.available = false
            """,
            ing_name=ingredient_name.lower(),
        )

    def add_substitution(self, original: str, substitute: str):
        """Record that one ingredient can substitute another."""
        self._run(
            """
            MERGE (o:Ingredient {name: $original})
            MERGE (s:Ingredient {name: $substitute})
            MERGE (o)-[:SUBSTITUTES]->(s)
            """,
            original=original.lower(),
            substitute=substitute.lower(),
        )

    # ── Queries ────────────────────────────────────────────────────

    def get_affected_recipes(self, ingredient_name: str) -> list[str]:
        """Find all recipes that require a given ingredient."""
        records, _, _ = self._run(
            """
            MATCH (r:Recipe)-[:REQUIRES]->(i:Ingredient {name: $ing_name})
            RETURN r.name AS recipe_name
            """,
            ing_name=ingredient_name.lower(),
        )
        return [r["recipe_name"] for r in (records or [])]

    def get_all_ingredients(self) -> list[dict]:
        """Return all ingredients with their associated recipes."""
        records, _, _ = self._run(
            """
            MATCH (r:Recipe)-[req:REQUIRES]->(i:Ingredient)
            RETURN i.name AS ingredient, req.quantity AS quantity,
                   collect(r.name) AS recipes
            """,
        )
        return [dict(r) for r in (records or [])]

    def get_shopping_list(self) -> list[dict]:
        """
        Get a consolidated shopping list with quantities, prices, and stores.
        Groups by ingredient, sums up needs across recipes.
        """
        records, _, _ = self._run(
            """
            MATCH (r:Recipe)-[req:REQUIRES]->(i:Ingredient)
            OPTIONAL MATCH (i)-[a:AVAILABLE_AT]->(s:Store)
            WHERE a.available = true
            RETURN i.name AS ingredient,
                   collect(DISTINCT req.quantity) AS quantities,
                   collect(DISTINCT r.name) AS used_in,
                   CASE WHEN s IS NOT NULL THEN s.name ELSE 'TBD' END AS store,
                   CASE WHEN a IS NOT NULL THEN a.price ELSE 0 END AS price
            ORDER BY ingredient
            """,
        )
        return [dict(r) for r in (records or [])]

    def get_meal_plan(self) -> list[dict]:
        """Get the full weekly meal plan."""
        records, _, _ = self._run(
            """
            MATCH (d:Day)-[:HAS_MEAL]->(m:Meal)-[:SCHEDULED]->(r:Recipe)
            RETURN d.name AS day, m.type AS meal_type, r.name AS recipe,
                   r.cuisine AS cuisine, r.prep_time AS prep_time
            ORDER BY d.name, m.type
            """,
        )
        return [dict(r) for r in (records or [])]

    def get_graph_data(self) -> dict:
        """Get all nodes and relationships for visualization."""
        nodes_records, _, _ = self._run(
            """
            MATCH (n)
            RETURN id(n) AS id, labels(n) AS labels, properties(n) AS props
            """,
        )
        rels_records, _, _ = self._run(
            """
            MATCH (a)-[r]->(b)
            RETURN id(a) AS source, id(b) AS target, type(r) AS type,
                   properties(r) AS props
            """,
        )
        return {
            "nodes": [dict(r) for r in (nodes_records or [])],
            "relationships": [dict(r) for r in (rels_records or [])],
        }

    # ── Order ──────────────────────────────────────────────────────

    def create_order(self, order_items: list[dict]) -> str:
        """
        Create an Order node linked to ingredients.

        order_items = [{"ingredient": "chicken", "quantity": "500g",
                        "store": "Walmart", "price": 5.99}]
        """
        import uuid

        order_id = str(uuid.uuid4())[:8]
        self._run(
            """
            CREATE (o:Order {order_id: $order_id, status: 'placed',
                             created_at: datetime()})
            """,
            order_id=order_id,
        )
        for item in order_items:
            self._run(
                """
                MATCH (o:Order {order_id: $order_id})
                MERGE (i:Ingredient {name: $ing_name})
                MERGE (o)-[c:CONTAINS]->(i)
                SET c.quantity = $quantity, c.price = $price, c.store = $store
                """,
                order_id=order_id,
                ing_name=item["ingredient"].lower(),
                quantity=item.get("quantity", ""),
                price=item.get("price", 0),
                store=item.get("store", ""),
            )
        return order_id
