"""Grocery order placement agent with simulated checkout."""

import json
from datetime import datetime
from openai import OpenAI
import config


class OrderPlacer:
    """Generates consolidated grocery orders and simulates checkout."""

    def __init__(self):
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def consolidate_order(
        self,
        shopping_list: list[dict],
        household_size: int,
        existing_ingredients: list[str] | None = None,
    ) -> dict:
        """
        Take the raw shopping list and consolidate into an optimized order.
        Groups by store, adjusts quantities for household size,
        and calculates totals.

        Returns: {
            "stores": [
                {
                    "name": "Walmart",
                    "items": [{"ingredient": ..., "quantity": ..., "price": ...}],
                    "subtotal": 45.99
                }
            ],
            "total": 89.99,
            "estimated_delivery": "...",
            "savings_tips": "..."
        }
        """
        response = self.openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a smart grocery shopping assistant. "
                        "Consolidate a shopping list into store-grouped orders. "
                        "Rules:\n"
                        "1. Group items by store\n"
                        "2. Adjust quantities based on household size\n"
                        "3. Identify potential bulk savings\n"
                        "4. Estimate total cost per store and overall\n"
                        "5. Add estimated delivery time\n"
                        "6. Include 1-2 savings tips\n\n"
                        "Return JSON with structure:\n"
                        "{\n"
                        '  "stores": [{"name": str, "items": [{ingredient, quantity, '
                        '    price, unit_price}], "subtotal": float}],\n'
                        '  "total": float,\n'
                        '  "estimated_delivery": str,\n'
                        '  "savings_tips": str\n'
                        "}\n"
                        "Return ONLY valid JSON, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Consolidate this shopping list for {household_size} people:\n"
                        f"{json.dumps(shopping_list, indent=2)}"
                        + (
                            f"\n\nIMPORTANT: The user ALREADY HAS these ingredients at home, "
                            f"DO NOT include them in the order: {existing_ingredients}"
                            if existing_ingredients
                            else ""
                        )
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
            return self._fallback_consolidation(shopping_list)

    def place_order(self, consolidated_order: dict) -> dict:
        """
        Simulate placing the grocery order.
        Returns order confirmation details.
        """
        import uuid

        order_id = f"CT-{str(uuid.uuid4())[:8].upper()}"
        now = datetime.now()

        return {
            "order_id": order_id,
            "status": "confirmed",
            "placed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "estimated_delivery": consolidated_order.get(
                "estimated_delivery", "Within 2 hours"
            ),
            "total": consolidated_order.get("total", 0),
            "stores": [s["name"] for s in consolidated_order.get("stores", [])],
            "item_count": sum(
                len(s.get("items", []))
                for s in consolidated_order.get("stores", [])
            ),
            "confirmation_message": (
                f"🛒 Order {order_id} confirmed! "
                f"Your groceries from {len(consolidated_order.get('stores', []))} "
                f"store(s) will arrive "
                f"{consolidated_order.get('estimated_delivery', 'soon')}. "
                f"Total: ${consolidated_order.get('total', 0):.2f}"
            ),
        }

    def _fallback_consolidation(self, shopping_list: list[dict]) -> dict:
        """Fallback if OpenAI parsing fails."""
        items = []
        total = 0
        for item in shopping_list:
            price = item.get("price", 3.99)
            total += price
            items.append(
                {
                    "ingredient": item.get("ingredient", "unknown"),
                    "quantity": item.get("quantities", ["1"])[0] if item.get("quantities") else "1",
                    "price": price,
                }
            )
        return {
            "stores": [{"name": "Local Grocery", "items": items, "subtotal": total}],
            "total": round(total, 2),
            "estimated_delivery": "Within 2 hours",
            "savings_tips": "Buy in bulk for frequently used ingredients.",
        }
