"""Development check for the recipe library.

Run it after adding or editing recipes:

    uv run python verify_data.py

It exits non-zero when the library is inconsistent (an ingredient without a
shopping category, an unknown diet tag, one ingredient measured two different
ways, a missing storage note, and so on).
"""

from __future__ import annotations

import sys
from collections import Counter

from utils.planner import PlanRequest, build_plan, build_shopping_list
from utils.recipes import CATEGORY_ORDER, RECIPES, category_of, validate_library

DAYS = 7


def summarise() -> None:
    print(f"{len(RECIPES)} recipes")

    slots = Counter(slot for recipe in RECIPES for slot in recipe.meal_slots)
    for slot, count in slots.most_common():
        print(f"  {slot:<10} {count}")

    diets = Counter(tag for recipe in RECIPES for tag in recipe.diets)
    print("  diets:", ", ".join(f"{tag} {count}" for tag, count in diets.most_common()))

    cuisines = Counter(recipe.cuisine for recipe in RECIPES)
    print("  cuisines:", ", ".join(f"{name} {count}" for name, count in cuisines.most_common()))

    names = {item.name for recipe in RECIPES for item in recipe.ingredients}
    per_category = Counter(category_of(name) for name in names)
    print(f"  {len(names)} distinct ingredients")
    for category in CATEGORY_ORDER:
        print(f"    {category:<16} {per_category[category]} items")


def smoke_test() -> None:
    """Plan a week for a few awkward combinations and merge the shopping list."""
    from datetime import date, timedelta

    monday = date.today() - timedelta(days=date.today().weekday())
    week = tuple(monday + timedelta(days=offset) for offset in range(DAYS))

    cases = [
        PlanRequest(servings=4, days=week, meal_slots=("Lunch", "Dinner")),
        PlanRequest(servings=1, days=week, meal_slots=("Breakfast", "Lunch", "Dinner"),
                    diets=("Vegan", "Gluten-free"), use_leftovers=True),
        PlanRequest(servings=6, days=week, meal_slots=("Dinner",),
                    diets=("Vegetarian", "High-protein"), avoid=("mushrooms", "tofu")),
        PlanRequest(servings=2, days=week, meal_slots=("Dinner",),
                    diets=("Pescatarian", "Low-carb", "Dairy-free")),
    ]

    for request in cases:
        plan = build_plan(request)
        shopping = build_shopping_list(plan)
        planned = len(plan.meals)
        print(
            f"  {request.servings}p x {len(request.days)}d "
            f"{'/'.join(request.meal_slots)} "
            f"[{'/'.join(request.diets) if request.diets else 'anything'}]: "
            f"{planned} meals, {len(shopping)} shopping lines"
            + (f", issues={plan.issues}" if plan.issues else "")
        )


def main() -> int:
    problems = validate_library()
    for problem in problems:
        print(f"PROBLEM: {problem}")

    print("Recipe library")
    summarise()
    print("Smoke test")
    smoke_test()

    if problems:
        print(f"\n{len(problems)} problem(s) found.")
        return 1
    print("\nLibrary is consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
