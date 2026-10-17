"""Recipe library for the *What to cook next* meal planner.

This module is deliberately pure data plus a few lookup helpers, so the
planner (:mod:`utils.planner`) and the Streamlit UI stay focused on behaviour.

Conventions
-----------
* Every ingredient quantity is authored for **one serving** in the smallest
  practical unit (``g``, ``ml``, ``tsp``, ``tbsp``, ``piece``, ``clove`` ...).
  The planner multiplies by the number of servings, so scaling is linear.
* Ingredient names are *canonical shopping names*. The same name across
  recipes must mean the same thing (``garlic``, never "garlic cloves"), which
  is what lets the planner merge duplicates in the shopping list.
* Only shelf-stable and dairy items live in the pantry category; fresh
  vegetables, fruit and herbs are produce.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Categories, units and vocabularies
# --------------------------------------------------------------------------- #

PRODUCE = "Produce"
PROTEINS = "Proteins & Meat"
PANTRY = "Pantry & Dairy"
CATEGORY_ORDER: tuple[str, ...] = (PRODUCE, PROTEINS, PANTRY)

CATEGORY_BLURB: dict[str, str] = {
    PRODUCE: "Vegetables, fruit and fresh herbs",
    PROTEINS: "Poultry, seafood, tofu and meat",
    PANTRY: "Grains, sauces, oils, spices, dairy and eggs",
}

MEAL_SLOTS: tuple[str, ...] = ("Breakfast", "Lunch", "Dinner")

DIET_OPTIONS: tuple[str, ...] = (
    "Vegetarian",
    "Vegan",
    "Pescatarian",
    "Gluten-free",
    "Dairy-free",
    "Low-carb",
    "High-protein",
    "Nut-free",
)

CUISINES: tuple[str, ...] = (
    "American",
    "Chinese",
    "French",
    "Greek",
    "Indian",
    "Italian",
    "Japanese",
    "Korean",
    "Mediterranean",
    "Mexican",
    "Middle Eastern",
    "Thai",
    "Vietnamese",
)

PROTEIN_OPTIONS: tuple[str, ...] = (
    "Chicken",
    "Turkey",
    "Beef",
    "Pork",
    "Lamb",
    "Seafood",
    "Tofu",
    "Legumes",
    "Eggs",
    "Cheese & dairy",
    "Nuts & seeds",
)

STYLES: tuple[str, ...] = (
    "Bowl",
    "Curry",
    "Grill",
    "One-pot",
    "Pasta",
    "Salad",
    "Sandwich",
    "Soup",
    "Stir-fry",
    "Tacos",
    "Traybake",
)

#: Protein tags that are not pescatarian.
MEAT_PROTEINS: frozenset[str] = frozenset({"Chicken", "Turkey", "Beef", "Pork", "Lamb"})

#: Ingredients that make a recipe *not* nut-free (tree nuts and peanuts).
NUT_INGREDIENTS: frozenset[str] = frozenset(
    {"peanuts", "almonds", "walnuts", "pine nuts", "pesto", "granola", "almond butter", "peanut butter"}
)

#: Mass, volume and count units. Mass/volume are converted to a base unit so
#: recipes that measure the same thing differently still merge.
MASS_UNITS: dict[str, float] = {"g": 1.0, "kg": 1000.0}
VOLUME_UNITS: dict[str, float] = {"ml": 1.0, "l": 1000.0, "tsp": 5.0, "tbsp": 15.0, "cup": 240.0}
COUNT_UNITS: tuple[str, ...] = (
    "piece",
    "clove",
    "can",
    "bunch",
    "slice",
    "stalk",
    "head",
    "fillet",
    "pinch",
    "sheet",
)

#: Things most kitchens already have; flagged so the shopping list can hide them.
STAPLES: frozenset[str] = frozenset(
    {"salt", "black pepper", "olive oil", "vegetable oil", "all-purpose flour", "sugar", "butter"}
)

#: Practical buying hints shown next to a shopping line.
SHOPPING_HINTS: dict[str, str] = {
    "garlic": "1 head ≈ 10 cloves",
    "onion": "1 medium onion ≈ 150 g",
    "red onion": "1 medium onion ≈ 150 g",
    "ginger": "a thumb ≈ 20 g",
    "lemon": "1 lemon ≈ 45 ml juice",
    "lime": "1 lime ≈ 30 ml juice",
    "fresh parsley": "1 bunch ≈ 30 g",
    "fresh cilantro": "1 bunch ≈ 30 g",
    "fresh basil": "1 bunch ≈ 25 g",
    "fresh mint": "1 bunch ≈ 25 g",
    "fresh dill": "1 bunch ≈ 25 g",
    "fresh thyme": "1 bunch ≈ 20 g",
    "fresh rosemary": "1 bunch ≈ 20 g",
    "chicken breast": "1 large breast ≈ 200 g",
    "chicken thighs": "1 thigh ≈ 120 g",
    "salmon fillet": "1 fillet ≈ 150 g",
    "cod fillet": "1 fillet ≈ 170 g",
    "vegetable stock": "1 stock cube ≈ 500 ml",
}

# --------------------------------------------------------------------------- #
# Ingredient categories (the single source of truth for shopping aisles)
# --------------------------------------------------------------------------- #

_PRODUCE: frozenset[str] = frozenset(
    {
        "apple", "asparagus", "avocado", "baby spinach", "banana", "bell pepper",
        "broccoli", "cabbage", "carrot", "cauliflower", "celery", "cherry tomatoes",
        "cucumber", "fresh basil", "fresh cilantro", "fresh dill", "fresh mint",
        "fresh parsley", "fresh rosemary", "fresh thyme", "frozen peas", "garlic",
        "ginger", "green beans", "jalapeño", "lemon", "lime", "mango",
        "mixed berries", "mushrooms", "onion", "potato", "red onion",
        "romaine lettuce", "scallion", "sweet potato", "tomatoes", "zucchini",
    }
)

_PROTEINS: frozenset[str] = frozenset(
    {
        "beef strips", "canned tuna", "chicken breast", "chicken thighs", "cod fillet",
        "ground beef", "ground lamb", "ground turkey", "pork chops", "salmon fillet",
        "shrimp", "sliced turkey", "tofu",
    }
)

_PANTRY: frozenset[str] = frozenset(
    {
        "all-purpose flour", "almond butter", "almonds", "baking powder",
        "balsamic vinegar", "basmati rice", "black pepper", "brown sugar", "butter",
        "canned black beans", "canned chickpeas", "canned chopped tomatoes",
        "canned kidney beans", "canned lentils", "canned white beans", "capers",
        "cheddar cheese", "chia seeds", "chicken stock", "chili flakes",
        "chili powder", "ciabatta roll", "cinnamon", "coconut milk", "corn tortillas",
        "cornstarch", "couscous", "curry powder", "dijon mustard", "dried green lentils",
        "dried oregano", "egg noodles", "eggs", "feta cheese", "fish sauce",
        "flour tortillas", "garam masala", "gochujang", "granola", "green curry paste",
        "greek yogurt", "ground coriander", "ground cumin", "heavy cream", "honey",
        "jasmine rice", "kalamata olives", "maple syrup", "mayonnaise", "milk",
        "miso paste", "mozzarella cheese", "nutmeg", "oat milk", "olive oil",
        "oyster sauce", "paprika", "parmesan cheese", "peanut butter", "peanuts",
        "penne", "pesto", "pita bread", "pumpkin seeds", "quinoa", "red wine vinegar",
        "rice noodles", "rice vinegar", "risotto rice", "rolled oats", "salt",
        "sandwich bread", "sesame oil", "sesame seeds", "smoked paprika",
        "soba noodles", "soy sauce", "spaghetti", "sugar", "tahini", "tamari",
        "tomato paste", "turmeric", "vanilla extract", "vegetable oil",
        "vegetable stock",
    }
)

CATEGORY_OF: dict[str, str] = {}
for _name in _PRODUCE:
    CATEGORY_OF[_name] = PRODUCE
for _name in _PROTEINS:
    CATEGORY_OF[_name] = PROTEINS
for _name in _PANTRY:
    CATEGORY_OF[_name] = PANTRY
del _name


def category_of(ingredient_name: str) -> str:
    """Return the shopping category for a canonical ingredient name."""
    try:
        return CATEGORY_OF[ingredient_name]
    except KeyError:  # pragma: no cover - caught by verify_data()
        raise KeyError(
            f"Ingredient {ingredient_name!r} is not assigned to a shopping category."
        ) from None


def shopping_hint(ingredient_name: str) -> str:
    """Practical buying hint for an ingredient, or an empty string."""
    return SHOPPING_HINTS.get(ingredient_name, "")


def is_staple(ingredient_name: str) -> bool:
    """True for things most kitchens already have."""
    return ingredient_name in STAPLES


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Ingredient:
    """One ingredient in a recipe, measured per single serving."""

    name: str
    qty: float
    unit: str
    note: str = ""
    optional: bool = False

    @property
    def category(self) -> str:
        return category_of(self.name)

    @property
    def is_staple(self) -> bool:
        return self.name in STAPLES

    @property
    def hint(self) -> str:
        return SHOPPING_HINTS.get(self.name, "")


@dataclass(frozen=True)
class Recipe:
    """A single dish, with quantities authored for one serving."""

    id: str
    name: str
    cuisine: str
    meal_slots: tuple[str, ...]
    diets: tuple[str, ...]
    proteins: tuple[str, ...]
    styles: tuple[str, ...]
    minutes: int
    description: str
    ingredients: tuple[Ingredient, ...]
    prep: tuple[str, ...] = ()
    storage: str = ""
    keeps_days: int = 3
    freezes: bool = False

    def suits(self, slot: str) -> bool:
        return slot in self.meal_slots


def ing(name: str, qty: float, unit: str, note: str = "", optional: bool = False) -> Ingredient:
    """Shorthand constructor used by the recipe table below."""
    if unit not in MASS_UNITS and unit not in VOLUME_UNITS and unit not in COUNT_UNITS:
        raise ValueError(f"Unknown unit {unit!r} for {name!r}")
    return Ingredient(name=name, qty=qty, unit=unit, note=note, optional=optional)


# --------------------------------------------------------------------------- #
# The recipe table
# --------------------------------------------------------------------------- #

_RAW_RECIPES: tuple[Recipe, ...] = (
    # ------------------------------------------------------------------ breakfast
    Recipe(
        id="greek_yogurt_parfait",
        name="Greek yogurt parfait with berries",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegetarian", "Gluten-free", "High-protein"),
        proteins=("Cheese & dairy",),
        styles=(),
        minutes=10,
        description="Thick yogurt layered with berries, toasted oats and seeds — no cooking at all.",
        ingredients=(
            ing("greek yogurt", 200, "g", "thick, unsweetened"),
            ing("mixed berries", 80, "g", "fresh or frozen"),
            ing("granola", 40, "g"),
            ing("pumpkin seeds", 8, "g"),
            ing("honey", 1, "tsp", "or maple syrup"),
        ),
        prep=(),
        storage="Build the parfaits in jars tonight and keep the granola separate so it stays crunchy.",
        keeps_days=2,
    ),
    Recipe(
        id="spinach_feta_omelette",
        name="Spinach and feta omelette",
        cuisine="Mediterranean",
        meal_slots=("Breakfast",),
        diets=("Vegetarian", "Gluten-free", "Low-carb", "High-protein"),
        proteins=("Eggs", "Cheese & dairy"),
        styles=("One-pot",),
        minutes=15,
        description="A three-egg omelette folded around wilted spinach, feta and blistered tomatoes.",
        ingredients=(
            ing("eggs", 3, "piece"),
            ing("baby spinach", 50, "g"),
            ing("feta cheese", 25, "g", "crumbled"),
            ing("cherry tomatoes", 60, "g", "halved"),
            ing("butter", 0.5, "tbsp"),
            ing("scallion", 0.5, "stalk", "sliced"),
            ing("salt", 0.2, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Whisk the eggs in a jug and chop the spinach the night before — the pan does the rest.",),
        storage="Best eaten straight away; the filling can be prepped two days ahead.",
        keeps_days=1,
    ),
    Recipe(
        id="overnight_oats",
        name="Almond butter overnight oats",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegetarian", "Dairy-free", "High-protein"),
        proteins=("Nuts & seeds",),
        styles=(),
        minutes=10,
        description="Oats, chia and almond butter soaked overnight with banana — grab-and-go breakfast.",
        ingredients=(
            ing("rolled oats", 60, "g"),
            ing("oat milk", 200, "ml"),
            ing("almond butter", 1.5, "tbsp"),
            ing("banana", 1, "piece", "sliced"),
            ing("chia seeds", 1, "tsp"),
            ing("almonds", 10, "g", "chopped"),
            ing("maple syrup", 1, "tsp"),
            ing("cinnamon", 0.25, "tsp"),
        ),
        prep=("Soak the oats overnight in the fridge — two minutes tonight, breakfast ready when you wake up.",),
        storage="Keeps three days in the fridge, so make a jar for every breakfast day at once.",
        keeps_days=3,
    ),
    Recipe(
        id="avocado_toast",
        name="Avocado toast with poached eggs",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegetarian", "Dairy-free", "High-protein"),
        proteins=("Eggs",),
        styles=("Sandwich",),
        minutes=15,
        description="Smashed avocado on toast with silky poached eggs, chilli and lemon.",
        ingredients=(
            ing("sandwich bread", 2, "slice", "sourdough if you have it"),
            ing("avocado", 1, "piece"),
            ing("eggs", 2, "piece"),
            ing("cherry tomatoes", 50, "g"),
            ing("lemon", 0.25, "piece"),
            ing("chili flakes", 0.25, "tsp"),
            ing("olive oil", 0.5, "tsp"),
            ing("salt", 0.2, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=(),
        storage="Assemble at the table — avocado browns as soon as it is cut.",
        keeps_days=1,
    ),
    Recipe(
        id="banana_oat_pancakes",
        name="Banana oat pancakes",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegetarian", "Dairy-free"),
        proteins=("Eggs",),
        styles=(),
        minutes=20,
        description="Blender pancakes made from oats and banana, piled with berries and maple syrup.",
        ingredients=(
            ing("banana", 1, "piece"),
            ing("rolled oats", 60, "g"),
            ing("eggs", 2, "piece"),
            ing("oat milk", 60, "ml"),
            ing("baking powder", 0.5, "tsp"),
            ing("cinnamon", 0.25, "tsp"),
            ing("vegetable oil", 0.5, "tsp", "for the pan"),
            ing("maple syrup", 1, "tbsp"),
            ing("mixed berries", 60, "g"),
        ),
        prep=("Blend the batter tonight and keep it covered in the fridge.",),
        storage="Cooked pancakes keep three days and perk up in a toaster.",
        keeps_days=3,
    ),
    Recipe(
        id="breakfast_burritos",
        name="Freezer breakfast burritos",
        cuisine="Mexican",
        meal_slots=("Breakfast",),
        diets=("Vegetarian",),
        proteins=("Eggs", "Legumes", "Cheese & dairy"),
        styles=("Sandwich",),
        minutes=25,
        description="Scrambled eggs, black beans and cheddar rolled up and frozen for busy mornings.",
        ingredients=(
            ing("flour tortillas", 1.5, "piece", "large"),
            ing("eggs", 2, "piece"),
            ing("canned black beans", 0.4, "can", "drained"),
            ing("cheddar cheese", 30, "g", "grated"),
            ing("bell pepper", 0.3, "piece", "diced"),
            ing("onion", 0.2, "piece", "diced"),
            ing("tomatoes", 0.5, "piece"),
            ing("chili powder", 0.25, "tsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("fresh cilantro", 3, "g"),
        ),
        prep=("Cook the filling and roll the burritos tonight so mornings are a microwave job.",),
        storage="Wrap in foil, freeze up to two months, reheat from frozen for two minutes.",
        keeps_days=4,
        freezes=True,
    ),
    Recipe(
        id="chia_pudding",
        name="Mango chia pudding",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free"),
        proteins=("Nuts & seeds",),
        styles=(),
        minutes=10,
        description="Coconut-soaked chia seeds topped with mango and lime — set it and forget it.",
        ingredients=(
            ing("chia seeds", 3, "tbsp"),
            ing("coconut milk", 200, "ml"),
            ing("mango", 0.5, "piece", "diced"),
            ing("maple syrup", 2, "tsp"),
            ing("lime", 0.25, "piece"),
            ing("almonds", 10, "g", "toasted"),
        ),
        prep=("Stir the chia pudding tonight — it needs a few hours in the fridge to set.",),
        storage="Keeps four days; add the fruit just before eating.",
        keeps_days=4,
    ),
    Recipe(
        id="smoothie_bowl",
        name="Berry smoothie bowl",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free"),
        proteins=("Nuts & seeds",),
        styles=("Bowl",),
        minutes=10,
        description="A thick blended bowl of berries and banana with oats, seeds and almond butter on top.",
        ingredients=(
            ing("banana", 1, "piece", "frozen"),
            ing("mixed berries", 150, "g", "frozen"),
            ing("oat milk", 150, "ml"),
            ing("almond butter", 1, "tbsp"),
            ing("rolled oats", 30, "g"),
            ing("pumpkin seeds", 10, "g"),
            ing("maple syrup", 1, "tsp"),
        ),
        prep=("Portion the fruit into freezer bags so blending is a two-minute job.",),
        storage="Best fresh; frozen fruit keeps for months.",
        keeps_days=1,
    ),
    Recipe(
        id="french_toast",
        name="Cinnamon french toast",
        cuisine="French",
        meal_slots=("Breakfast",),
        diets=("Vegetarian",),
        proteins=("Eggs", "Cheese & dairy"),
        styles=(),
        minutes=20,
        description="Eggy cinnamon bread fried in butter, with banana and berries on the side.",
        ingredients=(
            ing("sandwich bread", 2, "slice", "day-old is ideal"),
            ing("eggs", 2, "piece"),
            ing("milk", 60, "ml"),
            ing("cinnamon", 0.5, "tsp"),
            ing("vanilla extract", 0.25, "tsp"),
            ing("butter", 1, "tbsp"),
            ing("maple syrup", 1.5, "tbsp"),
            ing("banana", 0.5, "piece"),
            ing("mixed berries", 50, "g"),
        ),
        prep=(),
        storage="Cook the whole batch and reheat in a dry pan — better than the microwave.",
        keeps_days=2,
    ),
    Recipe(
        id="baked_egg_cups",
        name="Baked egg and vegetable cups",
        cuisine="American",
        meal_slots=("Breakfast",),
        diets=("Vegetarian", "Gluten-free", "Low-carb", "High-protein"),
        proteins=("Eggs", "Cheese & dairy"),
        styles=(),
        minutes=30,
        description="Muffin-tin eggs with spinach, peppers and cheddar — bake once, eat all week.",
        ingredients=(
            ing("eggs", 2, "piece"),
            ing("milk", 30, "ml"),
            ing("cheddar cheese", 20, "g", "grated"),
            ing("baby spinach", 40, "g", "chopped"),
            ing("bell pepper", 0.3, "piece", "diced"),
            ing("onion", 0.2, "piece", "diced"),
            ing("olive oil", 0.5, "tsp", "for greasing"),
            ing("salt", 0.2, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Bake a tray on Sunday and refrigerate — 40 seconds in the microwave each morning.",),
        storage="Fridge four days, freezer two months.",
        keeps_days=4,
        freezes=True,
    ),
    # ---------------------------------------------------------------------- lunch
    Recipe(
        id="mediterranean_quinoa_bowl",
        name="Mediterranean quinoa bowl",
        cuisine="Mediterranean",
        meal_slots=("Lunch",),
        diets=("Vegetarian", "Gluten-free", "High-protein"),
        proteins=("Legumes", "Cheese & dairy"),
        styles=("Bowl", "Salad"),
        minutes=25,
        description="Quinoa, chickpeas, cucumber and feta with a lemon-oregano dressing.",
        ingredients=(
            ing("quinoa", 70, "g"),
            ing("canned chickpeas", 0.5, "can", "drained"),
            ing("cucumber", 0.3, "piece", "diced"),
            ing("cherry tomatoes", 100, "g", "halved"),
            ing("red onion", 0.2, "piece", "thinly sliced"),
            ing("feta cheese", 25, "g"),
            ing("kalamata olives", 15, "g"),
            ing("olive oil", 1, "tbsp"),
            ing("lemon", 0.5, "piece"),
            ing("dried oregano", 0.5, "tsp"),
            ing("fresh parsley", 5, "g", "chopped"),
        ),
        prep=("Cook a big pot of quinoa once, then portion it into lunch boxes for the week.",),
        storage="Keeps four days; dress just before eating so nothing goes soggy.",
        keeps_days=4,
    ),
    Recipe(
        id="chicken_caesar_wraps",
        name="Chicken caesar wraps",
        cuisine="American",
        meal_slots=("Lunch",),
        diets=(),
        proteins=("Chicken",),
        styles=("Sandwich",),
        minutes=20,
        description="Sliced chicken, crisp romaine and a sharp homemade caesar in a soft wrap.",
        ingredients=(
            ing("chicken breast", 120, "g"),
            ing("flour tortillas", 1.5, "piece", "large"),
            ing("romaine lettuce", 0.2, "head", "shredded"),
            ing("parmesan cheese", 15, "g", "grated"),
            ing("mayonnaise", 1.5, "tbsp"),
            ing("dijon mustard", 0.5, "tsp"),
            ing("lemon", 0.25, "piece"),
            ing("garlic", 0.5, "clove", "crushed"),
            ing("olive oil", 0.5, "tbsp"),
            ing("sandwich bread", 0.5, "slice", "torn into croutons"),
        ),
        prep=("Grill and slice the chicken tonight so lunch is pure assembly.",),
        storage="Wrap in the morning; the dressing keeps five days in a jar.",
        keeps_days=2,
    ),
    Recipe(
        id="tuna_white_bean_salad",
        name="Tuna and white bean salad",
        cuisine="Mediterranean",
        meal_slots=("Lunch",),
        diets=("Gluten-free", "Dairy-free", "High-protein", "Low-carb"),
        proteins=("Seafood", "Legumes"),
        styles=("Salad",),
        minutes=15,
        description="Store-cupboard tuna and beans turned into a bright, lemony lunch.",
        ingredients=(
            ing("canned tuna", 1, "can", "in olive oil, drained"),
            ing("canned white beans", 0.6, "can", "drained"),
            ing("red onion", 0.2, "piece", "finely chopped"),
            ing("cherry tomatoes", 80, "g"),
            ing("cucumber", 0.3, "piece"),
            ing("romaine lettuce", 0.2, "head"),
            ing("olive oil", 1, "tbsp"),
            ing("lemon", 0.5, "piece"),
            ing("dijon mustard", 0.5, "tsp"),
            ing("fresh parsley", 5, "g"),
        ),
        prep=(),
        storage="Tastes better after an hour; keeps two days in the fridge.",
        keeps_days=2,
    ),
    Recipe(
        id="tomato_soup_grilled_cheese",
        name="Tomato basil soup with grilled cheese",
        cuisine="American",
        meal_slots=("Lunch", "Dinner"),
        diets=("Vegetarian",),
        proteins=("Cheese & dairy",),
        styles=("Soup",),
        minutes=35,
        description="Slow-simmered tomato basil soup with a properly crisp cheddar sandwich.",
        ingredients=(
            ing("canned chopped tomatoes", 250, "g"),
            ing("onion", 0.3, "piece"),
            ing("garlic", 1, "clove"),
            ing("vegetable stock", 150, "ml"),
            ing("heavy cream", 1, "tbsp"),
            ing("fresh basil", 5, "g"),
            ing("olive oil", 0.5, "tbsp"),
            ing("sandwich bread", 2, "slice"),
            ing("cheddar cheese", 30, "g", "sliced"),
            ing("butter", 1, "tbsp"),
        ),
        prep=("Simmer the soup tonight — it only gets better by tomorrow.",),
        storage="Soup keeps four days and freezes three months; grill the sandwich fresh.",
        keeps_days=4,
        freezes=True,
    ),
    Recipe(
        id="falafel_pita",
        name="Falafel pita pockets",
        cuisine="Middle Eastern",
        meal_slots=("Lunch", "Dinner"),
        diets=("Vegan", "Vegetarian", "Dairy-free", "High-protein"),
        proteins=("Legumes",),
        styles=("Sandwich",),
        minutes=35,
        description="Herby chickpea falafel in warm pita with tahini, cucumber and tomato.",
        ingredients=(
            ing("canned chickpeas", 1, "can", "drained, dried well"),
            ing("onion", 0.3, "piece"),
            ing("garlic", 1, "clove"),
            ing("fresh parsley", 10, "g"),
            ing("ground cumin", 1, "tsp"),
            ing("ground coriander", 0.5, "tsp"),
            ing("all-purpose flour", 1.5, "tbsp"),
            ing("olive oil", 1, "tbsp", "for shallow frying"),
            ing("pita bread", 1, "piece"),
            ing("tahini", 1.5, "tbsp"),
            ing("cucumber", 0.3, "piece"),
            ing("tomatoes", 0.5, "piece"),
            ing("red onion", 0.2, "piece"),
            ing("lemon", 0.5, "piece"),
            ing("romaine lettuce", 0.15, "head"),
        ),
        prep=("Blitz and chill the falafel mix tonight — it holds together far better cold.",),
        storage="Falafel keeps three days; reheat in a dry pan to get the crust back.",
        keeps_days=3,
    ),
    Recipe(
        id="turkey_avocado_club",
        name="Turkey avocado club sandwich",
        cuisine="American",
        meal_slots=("Lunch",),
        diets=("Dairy-free", "High-protein"),
        proteins=("Turkey",),
        styles=("Sandwich",),
        minutes=15,
        description="A tall layered sandwich with turkey, avocado, tomato and a mustard mayo.",
        ingredients=(
            ing("sandwich bread", 3, "slice", "toasted"),
            ing("sliced turkey", 100, "g"),
            ing("avocado", 0.5, "piece", "sliced"),
            ing("tomatoes", 0.5, "piece"),
            ing("romaine lettuce", 0.15, "head"),
            ing("mayonnaise", 1, "tbsp"),
            ing("dijon mustard", 0.5, "tsp"),
            ing("olive oil", 0.5, "tsp"),
        ),
        prep=("Toast the bread and slice the tomato in the morning; keep the avocado whole until lunch.",),
        storage="Best the same day.",
        keeps_days=1,
    ),
    Recipe(
        id="soba_noodle_salad",
        name="Sesame soba noodle salad",
        cuisine="Japanese",
        meal_slots=("Lunch",),
        diets=("Vegan", "Vegetarian", "Dairy-free"),
        proteins=("Tofu", "Nuts & seeds"),
        styles=("Salad",),
        minutes=25,
        description="Cold soba tossed with crisp vegetables, sesame tofu and a soy-ginger dressing.",
        ingredients=(
            ing("soba noodles", 90, "g"),
            ing("tofu", 120, "g", "firm, cubed"),
            ing("carrot", 0.5, "piece", "ribboned"),
            ing("cucumber", 0.3, "piece"),
            ing("scallion", 0.5, "stalk"),
            ing("sesame seeds", 1, "tsp"),
            ing("tamari", 1, "tbsp"),
            ing("rice vinegar", 1, "tbsp"),
            ing("sesame oil", 1, "tsp"),
            ing("maple syrup", 1, "tsp"),
            ing("ginger", 5, "g", "grated"),
        ),
        prep=("Cook the noodles and pan-fry the tofu tonight; dress the salad cold tomorrow.",),
        storage="Keeps three days — loosen with a splash of vinegar before serving.",
        keeps_days=3,
    ),
    Recipe(
        id="caprese_panini",
        name="Caprese panini",
        cuisine="Italian",
        meal_slots=("Lunch",),
        diets=("Vegetarian",),
        proteins=("Cheese & dairy",),
        styles=("Sandwich",),
        minutes=20,
        description="Mozzarella, tomato and basil pressed until the cheese just starts to melt.",
        ingredients=(
            ing("ciabatta roll", 1, "piece"),
            ing("mozzarella cheese", 60, "g", "torn"),
            ing("tomatoes", 1, "piece", "sliced"),
            ing("fresh basil", 6, "g"),
            ing("olive oil", 1, "tbsp"),
            ing("balsamic vinegar", 1, "tsp"),
            ing("garlic", 0.5, "clove", "for the oil"),
            ing("salt", 0.2, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=(),
        storage="Assemble and press just before eating.",
        keeps_days=1,
    ),
    Recipe(
        id="burrito_bowl",
        name="Black bean burrito bowl",
        cuisine="Mexican",
        meal_slots=("Lunch", "Dinner"),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free", "High-protein"),
        proteins=("Legumes",),
        styles=("Bowl",),
        minutes=30,
        description="Spiced black beans over rice with peppers, avocado, lime and coriander.",
        ingredients=(
            ing("jasmine rice", 70, "g"),
            ing("canned black beans", 0.6, "can", "drained"),
            ing("bell pepper", 0.4, "piece"),
            ing("onion", 0.2, "piece"),
            ing("garlic", 0.5, "clove"),
            ing("avocado", 0.5, "piece"),
            ing("lime", 0.5, "piece"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("ground cumin", 0.5, "tsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("fresh cilantro", 5, "g"),
        ),
        prep=("Cook the rice and beans in one batch; assemble the bowls cold for lunches.",),
        storage="Keeps four days — add avocado and lime at serving time.",
        keeps_days=4,
    ),
    Recipe(
        id="pesto_pasta_salad",
        name="Chicken pesto pasta salad",
        cuisine="Italian",
        meal_slots=("Lunch",),
        diets=(),
        proteins=("Chicken",),
        styles=("Pasta", "Salad"),
        minutes=25,
        description="Penne, grilled chicken and tomatoes tossed in pesto with little mozzarella pearls.",
        ingredients=(
            ing("penne", 90, "g"),
            ing("chicken breast", 120, "g"),
            ing("pesto", 2, "tbsp"),
            ing("cherry tomatoes", 100, "g"),
            ing("mozzarella cheese", 30, "g", "bocconcini"),
            ing("cucumber", 0.3, "piece"),
            ing("olive oil", 0.5, "tbsp"),
            ing("lemon", 0.25, "piece"),
            ing("fresh basil", 4, "g"),
        ),
        prep=("Boil the pasta and grill the chicken on the weekend; toss the salad cold.",),
        storage="Keeps three days; add basil and mozzarella on the day.",
        keeps_days=3,
    ),
    Recipe(
        id="roasted_veg_couscous",
        name="Roasted vegetable couscous salad",
        cuisine="Middle Eastern",
        meal_slots=("Lunch",),
        diets=("Vegan", "Vegetarian", "Dairy-free", "High-protein"),
        proteins=("Legumes",),
        styles=("Salad",),
        minutes=30,
        description="Cumin-roasted courgette and pepper folded through couscous with chickpeas and herbs.",
        ingredients=(
            ing("couscous", 80, "g"),
            ing("zucchini", 0.5, "piece"),
            ing("bell pepper", 0.5, "piece"),
            ing("red onion", 0.25, "piece"),
            ing("canned chickpeas", 0.5, "can", "drained"),
            ing("olive oil", 1, "tbsp"),
            ing("ground cumin", 0.5, "tsp"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("lemon", 0.5, "piece"),
            ing("fresh mint", 4, "g"),
            ing("fresh parsley", 4, "g"),
        ),
        prep=("Roast a large tray of vegetables and soak the couscous the night before.",),
        storage="Keeps four days; a squeeze of lemon wakes it up.",
        keeps_days=4,
    ),
    Recipe(
        id="lentil_feta_salad",
        name="Lentil and feta salad",
        cuisine="Mediterranean",
        meal_slots=("Lunch",),
        diets=("Vegetarian", "Gluten-free", "High-protein"),
        proteins=("Legumes", "Cheese & dairy"),
        styles=("Salad",),
        minutes=20,
        description="Lentils, spinach, tomato and feta with a red wine vinegar dressing.",
        ingredients=(
            ing("canned lentils", 0.7, "can", "drained and rinsed"),
            ing("feta cheese", 30, "g"),
            ing("cherry tomatoes", 100, "g"),
            ing("cucumber", 0.3, "piece"),
            ing("red onion", 0.2, "piece"),
            ing("baby spinach", 40, "g"),
            ing("olive oil", 1, "tbsp"),
            ing("red wine vinegar", 1, "tsp"),
            ing("dried oregano", 0.5, "tsp"),
            ing("fresh parsley", 5, "g"),
        ),
        prep=("Simmer the lentils (or open a can) and chop the vegetables tonight.",),
        storage="Keeps three days and travels well in a lunch box.",
        keeps_days=3,
    ),
    # --------------------------------------------------------------------- dinner
    Recipe(
        id="lemon_garlic_chicken",
        name="Lemon garlic chicken with roast potatoes",
        cuisine="Mediterranean",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "High-protein"),
        proteins=("Chicken",),
        styles=("Traybake", "One-pot"),
        minutes=40,
        description="Chicken thighs roasted with lemon, garlic and baby potatoes — the pan juices do the work.",
        ingredients=(
            ing("chicken thighs", 180, "g", "skin on, bone in"),
            ing("potato", 250, "g", "halved"),
            ing("lemon", 0.5, "piece", "zest and juice"),
            ing("garlic", 2, "clove", "smashed"),
            ing("olive oil", 0.75, "tbsp"),
            ing("dried oregano", 0.5, "tsp"),
            ing("smoked paprika", 0.25, "tsp"),
            ing("fresh parsley", 5, "g"),
            ing("salt", 0.25, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Marinate the chicken in the lemon, garlic and oregano tonight for a deeper flavour.",),
        storage="Roast extra potatoes and chicken: three days in the fridge, reheated uncovered at 200 °C.",
        keeps_days=3,
    ),
    Recipe(
        id="thai_green_curry",
        name="Thai green chicken curry",
        cuisine="Thai",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free"),
        proteins=("Chicken",),
        styles=("Curry", "One-pot"),
        minutes=30,
        description="A fast, fragrant coconut curry with chicken, peppers, courgette and Thai basil.",
        ingredients=(
            ing("chicken thighs", 150, "g", "sliced"),
            ing("green curry paste", 1.5, "tbsp"),
            ing("coconut milk", 200, "ml"),
            ing("bell pepper", 0.5, "piece"),
            ing("zucchini", 0.5, "piece"),
            ing("green beans", 60, "g"),
            ing("jasmine rice", 80, "g"),
            ing("fish sauce", 0.5, "tbsp"),
            ing("lime", 0.5, "piece"),
            ing("fresh basil", 5, "g"),
        ),
        prep=("Cut the chicken and vegetables tonight and keep them together in one container.",),
        storage="Curry keeps four days and freezes well; cook rice fresh or reheat with a splash of water.",
        keeps_days=4,
        freezes=True,
    ),
    Recipe(
        id="beef_broccoli_stirfry",
        name="Beef and broccoli stir-fry",
        cuisine="Chinese",
        meal_slots=("Dinner",),
        diets=("Dairy-free",),
        proteins=("Beef",),
        styles=("Stir-fry",),
        minutes=25,
        description="Velveted beef and crunchy broccoli in a glossy garlic-ginger sauce over rice.",
        ingredients=(
            ing("beef strips", 150, "g"),
            ing("broccoli", 150, "g", "small florets"),
            ing("garlic", 1, "clove"),
            ing("ginger", 8, "g"),
            ing("soy sauce", 1, "tbsp", "tamari for gluten-free"),
            ing("oyster sauce", 1, "tsp"),
            ing("sesame oil", 0.5, "tsp"),
            ing("cornstarch", 1, "tsp"),
            ing("jasmine rice", 80, "g"),
            ing("scallion", 0.5, "stalk"),
        ),
        prep=("Slice the beef and whisk the sauce tonight — keep them separate so the beef can marinate.",),
        storage="Best fresh but fine for two days; stir-fries lose their crunch when reheated.",
        keeps_days=2,
    ),
    Recipe(
        id="spaghetti_bolognese",
        name="Slow-simmered spaghetti bolognese",
        cuisine="Italian",
        meal_slots=("Dinner",),
        diets=(),
        proteins=("Beef",),
        styles=("Pasta", "One-pot"),
        minutes=45,
        description="A soffritto-based bolognese simmered down and served with spaghetti and parmesan.",
        ingredients=(
            ing("ground beef", 150, "g"),
            ing("spaghetti", 100, "g"),
            ing("canned chopped tomatoes", 200, "g"),
            ing("onion", 0.5, "piece"),
            ing("carrot", 0.5, "piece"),
            ing("celery", 1, "stalk"),
            ing("garlic", 1, "clove"),
            ing("tomato paste", 1, "tbsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("dried oregano", 0.5, "tsp"),
            ing("parmesan cheese", 10, "g"),
            ing("salt", 0.25, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Chop the soffritto tonight, or make the whole sauce now and reheat it on the night.",),
        storage="The sauce keeps four days and freezes three months — double it while you are there.",
        keeps_days=4,
        freezes=True,
    ),
    Recipe(
        id="mushroom_risotto",
        name="Creamy mushroom risotto",
        cuisine="Italian",
        meal_slots=("Dinner",),
        diets=("Vegetarian", "Gluten-free"),
        proteins=("Cheese & dairy",),
        styles=("One-pot",),
        minutes=40,
        description="Slow-stirred arborio rice with golden mushrooms, thyme and parmesan.",
        ingredients=(
            ing("risotto rice", 90, "g"),
            ing("mushrooms", 150, "g", "sliced"),
            ing("onion", 0.5, "piece", "finely diced"),
            ing("garlic", 1, "clove"),
            ing("vegetable stock", 500, "ml", "kept hot"),
            ing("parmesan cheese", 20, "g"),
            ing("butter", 1, "tbsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("fresh thyme", 3, "g"),
            ing("salt", 0.2, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Warm the stock and slice the mushrooms ahead; risotto needs your attention once it starts.",),
        storage="Eat it fresh — leftover risotto is best shallow-fried into crisp cakes the next day.",
        keeps_days=2,
    ),
    Recipe(
        id="chickpea_spinach_curry",
        name="Chickpea and spinach coconut curry",
        cuisine="Indian",
        meal_slots=("Dinner",),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free", "High-protein"),
        proteins=("Legumes",),
        styles=("Curry", "One-pot"),
        minutes=30,
        description="A 30-minute curry of chickpeas and spinach in a spiced coconut tomato sauce.",
        ingredients=(
            ing("canned chickpeas", 0.75, "can", "drained"),
            ing("baby spinach", 80, "g"),
            ing("coconut milk", 150, "ml"),
            ing("canned chopped tomatoes", 100, "g"),
            ing("onion", 0.5, "piece"),
            ing("garlic", 1, "clove"),
            ing("ginger", 8, "g"),
            ing("curry powder", 1, "tsp"),
            ing("ground cumin", 0.5, "tsp"),
            ing("turmeric", 0.25, "tsp"),
            ing("basmati rice", 80, "g"),
            ing("olive oil", 0.5, "tbsp"),
        ),
        prep=("Dice the onion, garlic and ginger tonight and refrigerate — the cooking then takes 20 minutes.",),
        storage="Keeps four days and freezes for three months; the flavour improves overnight.",
        keeps_days=4,
        freezes=True,
    ),
    Recipe(
        id="sheet_pan_salmon",
        name="Sheet-pan salmon with asparagus and lemon",
        cuisine="Mediterranean",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "Low-carb", "High-protein"),
        proteins=("Seafood",),
        styles=("Traybake",),
        minutes=25,
        description="Salmon, asparagus and blistered tomatoes roasted on one tray with garlic and lemon.",
        ingredients=(
            ing("salmon fillet", 150, "g"),
            ing("asparagus", 150, "g", "woody ends snapped"),
            ing("cherry tomatoes", 100, "g"),
            ing("lemon", 0.5, "piece", "sliced"),
            ing("garlic", 1, "clove", "sliced"),
            ing("olive oil", 0.75, "tbsp"),
            ing("dried oregano", 0.5, "tsp"),
            ing("salt", 0.25, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Move the salmon to the fridge tonight if it is frozen — it needs a full day to thaw safely.",),
        storage="Best fresh; cold salmon flakes nicely into tomorrow's salad.",
        keeps_days=2,
    ),
    Recipe(
        id="miso_salmon_rice",
        name="Miso-glazed salmon rice bowl",
        cuisine="Japanese",
        meal_slots=("Dinner",),
        diets=("Dairy-free", "High-protein"),
        proteins=("Seafood",),
        styles=("Bowl",),
        minutes=30,
        description="Sticky miso-honey salmon over rice with quick-pickled cucumber and carrot.",
        ingredients=(
            ing("salmon fillet", 150, "g"),
            ing("miso paste", 1, "tbsp"),
            ing("honey", 1, "tsp"),
            ing("jasmine rice", 80, "g"),
            ing("cucumber", 0.3, "piece"),
            ing("carrot", 0.5, "piece"),
            ing("scallion", 0.5, "stalk"),
            ing("rice vinegar", 1, "tsp"),
            ing("sesame oil", 0.5, "tsp"),
            ing("sesame seeds", 0.5, "tsp"),
        ),
        prep=("Whisk the miso glaze and marinate the salmon tonight; pickle the vegetables in the same go.",),
        storage="Glaze keeps a week; cooked rice keeps two days in the fridge.",
        keeps_days=2,
    ),
    Recipe(
        id="tofu_pad_thai",
        name="Tofu pad thai",
        cuisine="Thai",
        meal_slots=("Dinner",),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free"),
        proteins=("Tofu",),
        styles=("Stir-fry",),
        minutes=35,
        description="Rice noodles tossed with crisp tofu, tamarind-style sweet-sour sauce and peanuts.",
        ingredients=(
            ing("tofu", 150, "g", "firm, pressed"),
            ing("rice noodles", 80, "g"),
            ing("carrot", 0.5, "piece"),
            ing("bell pepper", 0.5, "piece"),
            ing("scallion", 0.5, "stalk"),
            ing("garlic", 1, "clove"),
            ing("tamari", 1, "tbsp"),
            ing("brown sugar", 1, "tsp"),
            ing("lime", 0.5, "piece"),
            ing("peanuts", 10, "g", "crushed"),
            ing("vegetable oil", 1, "tbsp"),
            ing("fresh cilantro", 4, "g"),
        ),
        prep=("Press the tofu tonight under a weighted plate so it crisps properly tomorrow.",),
        storage="Keeps two days; refresh with lime juice and a splash of water in the pan.",
        keeps_days=2,
    ),
    Recipe(
        id="beef_tacos",
        name="Beef tacos with pico de gallo",
        cuisine="Mexican",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free"),
        proteins=("Beef",),
        styles=("Tacos",),
        minutes=30,
        description="Spiced beef in warm corn tortillas with fresh pico de gallo and lime.",
        ingredients=(
            ing("ground beef", 150, "g"),
            ing("corn tortillas", 3, "piece"),
            ing("onion", 0.3, "piece"),
            ing("tomatoes", 1, "piece", "diced"),
            ing("jalapeño", 0.25, "piece"),
            ing("lime", 0.5, "piece"),
            ing("garlic", 1, "clove"),
            ing("ground cumin", 0.5, "tsp"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("chili powder", 0.5, "tsp"),
            ing("vegetable oil", 0.5, "tbsp"),
            ing("fresh cilantro", 5, "g"),
        ),
        prep=("Make the pico de gallo tonight — an hour in the fridge makes it taste far better.",),
        storage="Beef keeps three days; warm the tortillas to order.",
        keeps_days=3,
    ),
    Recipe(
        id="black_bean_tacos",
        name="Black bean and sweet potato tacos",
        cuisine="Mexican",
        meal_slots=("Dinner",),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free", "High-protein"),
        proteins=("Legumes",),
        styles=("Tacos", "Traybake"),
        minutes=35,
        description="Smoky roasted sweet potato and black beans with avocado and lime in corn tortillas.",
        ingredients=(
            ing("canned black beans", 0.75, "can", "drained"),
            ing("sweet potato", 150, "g", "cubed"),
            ing("corn tortillas", 3, "piece"),
            ing("red onion", 0.25, "piece"),
            ing("avocado", 0.5, "piece"),
            ing("lime", 0.5, "piece"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("ground cumin", 0.5, "tsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("fresh cilantro", 5, "g"),
        ),
        prep=("Roast the sweet potato tonight; reheat in a pan tomorrow and dinner is 10 minutes.",),
        storage="Filling keeps four days; add avocado and coriander fresh.",
        keeps_days=4,
    ),
    Recipe(
        id="chicken_shawarma_bowls",
        name="Chicken shawarma bowls",
        cuisine="Middle Eastern",
        meal_slots=("Dinner",),
        diets=("Dairy-free", "High-protein"),
        proteins=("Chicken",),
        styles=("Bowl",),
        minutes=35,
        description="Cumin-spiced chicken over couscous with cucumber, tomato and tahini sauce.",
        ingredients=(
            ing("chicken breast", 150, "g", "cut into strips"),
            ing("couscous", 70, "g"),
            ing("cucumber", 0.3, "piece"),
            ing("tomatoes", 1, "piece"),
            ing("red onion", 0.2, "piece"),
            ing("garlic", 1, "clove"),
            ing("ground cumin", 0.5, "tsp"),
            ing("ground coriander", 0.5, "tsp"),
            ing("paprika", 0.5, "tsp"),
            ing("turmeric", 0.25, "tsp"),
            ing("olive oil", 1, "tbsp"),
            ing("lemon", 0.5, "piece"),
            ing("tahini", 1, "tbsp"),
        ),
        prep=("Toss the chicken in the spices and oil tonight — it will be better for the rest, and cooking is 12 minutes.",),
        storage="Chicken keeps three days; whisk the tahini sauce fresh or keep it a week in a jar.",
        keeps_days=3,
    ),
    Recipe(
        id="greek_lamb_meatballs",
        name="Greek lamb meatballs with tzatziki",
        cuisine="Greek",
        meal_slots=("Dinner",),
        diets=(),
        proteins=("Lamb",),
        styles=("Grill",),
        minutes=40,
        description="Oregano lamb meatballs with cool cucumber tzatziki and warm pita.",
        ingredients=(
            ing("ground lamb", 150, "g"),
            ing("pita bread", 1, "piece"),
            ing("greek yogurt", 100, "g"),
            ing("cucumber", 0.3, "piece", "grated"),
            ing("garlic", 1, "clove"),
            ing("fresh mint", 4, "g"),
            ing("ground cumin", 0.5, "tsp"),
            ing("dried oregano", 0.5, "tsp"),
            ing("lemon", 0.5, "piece"),
            ing("olive oil", 0.5, "tbsp"),
            ing("red onion", 0.2, "piece"),
            ing("tomatoes", 0.5, "piece"),
        ),
        prep=("Roll the meatballs tonight and chill them — they hold their shape much better.",),
        storage="Meatballs keep three days and freeze well; tzatziki keeps four days.",
        keeps_days=3,
        freezes=True,
    ),
    Recipe(
        id="shakshuka",
        name="Shakshuka",
        cuisine="Middle Eastern",
        meal_slots=("Breakfast", "Dinner"),
        diets=("Vegetarian", "Gluten-free", "Low-carb", "High-protein"),
        proteins=("Eggs", "Cheese & dairy"),
        styles=("One-pot",),
        minutes=30,
        description="Eggs poached in a smoky pepper and tomato sauce, finished with feta and herbs.",
        ingredients=(
            ing("eggs", 2, "piece"),
            ing("canned chopped tomatoes", 200, "g"),
            ing("bell pepper", 0.5, "piece"),
            ing("onion", 0.4, "piece"),
            ing("garlic", 1, "clove"),
            ing("ground cumin", 0.5, "tsp"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("chili flakes", 0.25, "tsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("feta cheese", 20, "g"),
            ing("sandwich bread", 1, "slice", "for mopping"),
            ing("fresh parsley", 4, "g"),
        ),
        prep=("Simmer the sauce tonight, then crack the eggs in and finish it in 8 minutes tomorrow.",),
        storage="Sauce keeps four days and freezes; poach eggs fresh each time.",
        keeps_days=4,
    ),
    Recipe(
        id="lentil_lemon_soup",
        name="Lemon lentil soup",
        cuisine="Mediterranean",
        meal_slots=("Lunch", "Dinner"),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free", "High-protein", "Nut-free"),
        proteins=("Legumes",),
        styles=("Soup", "One-pot"),
        minutes=40,
        description="A thick lentil soup sharpened with lemon and finished with spinach.",
        ingredients=(
            ing("dried green lentils", 80, "g", "rinsed"),
            ing("carrot", 0.5, "piece"),
            ing("celery", 1, "stalk"),
            ing("onion", 0.5, "piece"),
            ing("garlic", 1, "clove"),
            ing("vegetable stock", 400, "ml"),
            ing("ground cumin", 0.5, "tsp"),
            ing("turmeric", 0.25, "tsp"),
            ing("lemon", 0.5, "piece"),
            ing("baby spinach", 40, "g"),
            ing("olive oil", 0.5, "tbsp"),
        ),
        prep=("No soaking needed for green lentils, but making the soup tonight means the flavours settle.",),
        storage="Keeps five days and freezes three months — this is the best batch-cook recipe here.",
        keeps_days=5,
        freezes=True,
    ),
    Recipe(
        id="chicken_tikka_masala",
        name="Chicken tikka masala",
        cuisine="Indian",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "High-protein"),
        proteins=("Chicken",),
        styles=("Curry",),
        minutes=40,
        description="Yogurt-marinated chicken in a tomato and cream sauce with warm spices.",
        ingredients=(
            ing("chicken breast", 150, "g", "cubed"),
            ing("greek yogurt", 45, "g"),
            ing("canned chopped tomatoes", 150, "g"),
            ing("heavy cream", 2, "tbsp"),
            ing("onion", 0.4, "piece"),
            ing("garlic", 1, "clove"),
            ing("ginger", 8, "g"),
            ing("garam masala", 1, "tsp"),
            ing("ground cumin", 0.5, "tsp"),
            ing("turmeric", 0.25, "tsp"),
            ing("basmati rice", 80, "g"),
            ing("olive oil", 0.5, "tbsp"),
        ),
        prep=("Marinate the chicken in the yogurt and spices tonight — that is where the flavour comes from.",),
        storage="Keeps four days and freezes well; it is even better on day two.",
        keeps_days=4,
        freezes=True,
    ),
    Recipe(
        id="pork_chops_apple",
        name="Pork chops with apple and sage",
        cuisine="American",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "Low-carb"),
        proteins=("Pork",),
        styles=("Grill", "One-pot"),
        minutes=30,
        description="Pan-seared pork chops with caramelised apple, mustard pan sauce and green beans.",
        ingredients=(
            ing("pork chops", 180, "g"),
            ing("apple", 1, "piece", "wedged"),
            ing("green beans", 120, "g"),
            ing("onion", 0.4, "piece"),
            ing("garlic", 1, "clove"),
            ing("fresh rosemary", 3, "g"),
            ing("dijon mustard", 1, "tsp"),
            ing("vegetable stock", 100, "ml"),
            ing("olive oil", 1, "tbsp"),
        ),
        prep=("Salt the chops tonight and leave them uncovered in the fridge for a better crust.",),
        storage="Keeps three days; slice cold into a salad or reheat gently with a splash of stock.",
        keeps_days=3,
    ),
    Recipe(
        id="bibimbap",
        name="Korean beef bibimbap",
        cuisine="Korean",
        meal_slots=("Dinner",),
        diets=("Dairy-free",),
        proteins=("Beef", "Eggs"),
        styles=("Bowl",),
        minutes=40,
        description="Rice bowls topped with marinated beef, sesame vegetables and a fried egg.",
        ingredients=(
            ing("beef strips", 130, "g"),
            ing("jasmine rice", 80, "g"),
            ing("carrot", 0.5, "piece", "julienned"),
            ing("baby spinach", 60, "g"),
            ing("mushrooms", 60, "g"),
            ing("eggs", 1, "piece", "fried, to finish"),
            ing("gochujang", 1, "tbsp"),
            ing("tamari", 1, "tbsp"),
            ing("garlic", 1, "clove"),
            ing("sesame oil", 0.5, "tsp"),
            ing("sesame seeds", 0.5, "tsp"),
        ),
        prep=("Marinate the beef in the tamari, garlic and sesame oil tonight; blanch the spinach too.",),
        storage="Components keep four days separately; assemble and add the egg when you eat.",
        keeps_days=4,
    ),
    Recipe(
        id="veggie_lo_mein",
        name="Vegetable lo mein",
        cuisine="Chinese",
        meal_slots=("Dinner",),
        diets=("Vegetarian", "Dairy-free"),
        proteins=("Eggs",),
        styles=("Stir-fry",),
        minutes=25,
        description="Egg noodles tossed with cabbage, pepper and carrot in a savoury soy sauce.",
        ingredients=(
            ing("egg noodles", 80, "g"),
            ing("cabbage", 100, "g", "shredded"),
            ing("carrot", 0.5, "piece"),
            ing("bell pepper", 0.5, "piece"),
            ing("scallion", 0.5, "stalk"),
            ing("garlic", 1, "clove"),
            ing("ginger", 6, "g"),
            ing("soy sauce", 1, "tbsp", "tamari for gluten-free"),
            ing("sesame oil", 0.5, "tsp"),
            ing("vegetable oil", 0.5, "tbsp"),
        ),
        prep=("Shred the vegetables tonight and store them in a bag; the stir-fry itself takes 8 minutes.",),
        storage="Keeps two days; reheat in a hot pan rather than the microwave.",
        keeps_days=2,
    ),
    Recipe(
        id="turkey_chili",
        name="Turkey and kidney bean chili",
        cuisine="American",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "High-protein"),
        proteins=("Turkey", "Legumes"),
        styles=("One-pot",),
        minutes=45,
        description="A big pot of smoky turkey chili — perfect for cooking once and eating twice.",
        ingredients=(
            ing("ground turkey", 150, "g"),
            ing("canned kidney beans", 0.75, "can", "drained"),
            ing("canned chopped tomatoes", 150, "g"),
            ing("onion", 0.4, "piece"),
            ing("bell pepper", 0.5, "piece"),
            ing("garlic", 1, "clove"),
            ing("chili powder", 1, "tsp"),
            ing("ground cumin", 0.5, "tsp"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("tomato paste", 1, "tbsp"),
            ing("vegetable stock", 150, "ml"),
            ing("olive oil", 0.5, "tbsp"),
        ),
        prep=("Chop the onion and pepper tonight — after that it is a one-pot simmer.",),
        storage="Keeps five days and freezes three months; portion leftovers for a busy night.",
        keeps_days=5,
        freezes=True,
    ),
    Recipe(
        id="garlic_shrimp_spaghetti",
        name="Garlic shrimp spaghetti",
        cuisine="Italian",
        meal_slots=("Dinner",),
        diets=("Dairy-free",),
        proteins=("Seafood",),
        styles=("Pasta",),
        minutes=25,
        description="Prawns, blistered tomatoes, garlic and chilli tossed through spaghetti.",
        ingredients=(
            ing("shrimp", 150, "g", "peeled"),
            ing("spaghetti", 100, "g"),
            ing("cherry tomatoes", 100, "g"),
            ing("garlic", 2, "clove"),
            ing("chili flakes", 0.25, "tsp"),
            ing("lemon", 0.5, "piece"),
            ing("olive oil", 1, "tbsp"),
            ing("fresh parsley", 5, "g"),
            ing("salt", 0.25, "tsp"),
            ing("black pepper", 1, "pinch"),
        ),
        prep=("Defrost the prawns in the fridge tonight; the dish itself is 15 minutes of work.",),
        storage="Best fresh — prawns toughen on reheating.",
        keeps_days=1,
    ),
    Recipe(
        id="turkey_zoodles",
        name="Turkey meatballs with courgette noodles",
        cuisine="Italian",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "Low-carb", "High-protein"),
        proteins=("Turkey",),
        styles=("One-pot",),
        minutes=35,
        description="Lean turkey meatballs in tomato sauce over spiralised courgette — light but filling.",
        ingredients=(
            ing("ground turkey", 150, "g"),
            ing("zucchini", 1.5, "piece", "spiralised"),
            ing("canned chopped tomatoes", 150, "g"),
            ing("onion", 0.4, "piece"),
            ing("garlic", 1, "clove"),
            ing("eggs", 0.5, "piece", "to bind"),
            ing("dried oregano", 0.5, "tsp"),
            ing("olive oil", 0.75, "tbsp"),
            ing("fresh basil", 4, "g"),
        ),
        prep=("Roll the meatballs tonight and chill them; salty courgette releases water, so salt it just before cooking.",),
        storage="Meatballs and sauce keep three days; cook the courgette fresh or it goes watery.",
        keeps_days=3,
        freezes=True,
    ),
    Recipe(
        id="stuffed_peppers",
        name="Quinoa and feta stuffed peppers",
        cuisine="Mediterranean",
        meal_slots=("Dinner",),
        diets=("Vegetarian", "Gluten-free", "High-protein"),
        proteins=("Legumes", "Cheese & dairy"),
        styles=("Traybake",),
        minutes=50,
        description="Roasted peppers filled with quinoa, chickpeas, tomato and feta.",
        ingredients=(
            ing("bell pepper", 1, "piece", "halved"),
            ing("quinoa", 70, "g"),
            ing("canned chickpeas", 0.4, "can", "drained"),
            ing("feta cheese", 30, "g"),
            ing("onion", 0.3, "piece"),
            ing("garlic", 1, "clove"),
            ing("canned chopped tomatoes", 100, "g"),
            ing("ground cumin", 0.5, "tsp"),
            ing("olive oil", 0.5, "tbsp"),
            ing("fresh parsley", 4, "g"),
        ),
        prep=("Cook the quinoa and make the filling tonight; tomorrow just fill and bake.",),
        storage="Keeps three days and reheats well; they also eat well cold in a lunch box.",
        keeps_days=3,
    ),
    Recipe(
        id="cauliflower_chickpea_traybake",
        name="Spiced cauliflower and chickpea traybake",
        cuisine="Middle Eastern",
        meal_slots=("Dinner",),
        diets=("Vegan", "Vegetarian", "Gluten-free", "Dairy-free"),
        proteins=("Legumes",),
        styles=("Traybake",),
        minutes=40,
        description="Cumin-roasted cauliflower and chickpeas with tahini, lemon and warm pita.",
        ingredients=(
            ing("cauliflower", 250, "g", "florets"),
            ing("canned chickpeas", 0.5, "can", "drained"),
            ing("red onion", 0.3, "piece"),
            ing("garlic", 1, "clove"),
            ing("ground cumin", 0.5, "tsp"),
            ing("ground coriander", 0.5, "tsp"),
            ing("smoked paprika", 0.5, "tsp"),
            ing("olive oil", 1, "tbsp"),
            ing("lemon", 0.5, "piece"),
            ing("tahini", 1, "tbsp"),
            ing("pita bread", 1, "piece"),
            ing("fresh parsley", 4, "g"),
        ),
        prep=("Cut the cauliflower and mix the spice oil tonight so the tray goes straight in the oven.",),
        storage="Keeps four days; eat cold in a wrap or reheat in a hot oven.",
        keeps_days=4,
    ),
    Recipe(
        id="chicken_souvlaki",
        name="Chicken souvlaki with pita",
        cuisine="Greek",
        meal_slots=("Dinner",),
        diets=("High-protein",),
        proteins=("Chicken",),
        styles=("Grill",),
        minutes=35,
        description="Lemon-oregano chicken skewers stuffed into pita with tzatziki and crunchy salad.",
        ingredients=(
            ing("chicken breast", 150, "g", "cubed"),
            ing("pita bread", 1, "piece"),
            ing("greek yogurt", 60, "g"),            ing("cucumber", 0.3, "piece"),
            ing("tomatoes", 1, "piece"),
            ing("red onion", 0.2, "piece"),
            ing("romaine lettuce", 0.15, "head"),
            ing("garlic", 1, "clove"),
            ing("dried oregano", 0.5, "tsp"),
            ing("lemon", 0.5, "piece"),
            ing("olive oil", 1, "tbsp"),
        ),
        prep=("Marinate the chicken in lemon, oregano, garlic and oil tonight.",),
        storage="Chicken keeps three days; tzatziki four — build the pitas when you eat.",
        keeps_days=3,
    ),
    Recipe(
        id="veg_egg_fried_rice",
        name="Vegetable egg fried rice",
        cuisine="Chinese",
        meal_slots=("Lunch", "Dinner"),
        diets=("Vegetarian", "Dairy-free"),
        proteins=("Eggs",),
        styles=("Stir-fry",),
        minutes=20,
        description="Day-old rice fried hard with egg, peas and carrot — dinner in 20 minutes.",
        ingredients=(
            ing("jasmine rice", 80, "g", "cooked and chilled"),
            ing("eggs", 2, "piece"),
            ing("frozen peas", 60, "g"),
            ing("carrot", 0.5, "piece", "diced"),
            ing("scallion", 0.5, "stalk"),
            ing("garlic", 1, "clove"),
            ing("soy sauce", 1, "tbsp", "tamari for gluten-free"),
            ing("sesame oil", 0.5, "tsp"),
            ing("vegetable oil", 0.5, "tbsp"),
        ),
        prep=("Cook extra rice tonight and chill it — cold rice is what makes fried rice work.",),
        storage="Keeps two days; reheat in a hot pan with a splash of water.",
        keeps_days=2,
    ),
    Recipe(
        id="baked_cod_tomatoes",
        name="Baked cod with tomatoes and olives",
        cuisine="Mediterranean",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "Low-carb", "High-protein"),
        proteins=("Seafood",),
        styles=("Traybake", "One-pot"),
        minutes=30,
        description="Cod baked over a quick tomato, olive and caper sauce with green beans.",
        ingredients=(
            ing("cod fillet", 170, "g"),
            ing("cherry tomatoes", 150, "g"),
            ing("kalamata olives", 15, "g"),
            ing("capers", 1, "tsp"),
            ing("garlic", 1, "clove"),
            ing("green beans", 100, "g"),
            ing("olive oil", 1, "tbsp"),
            ing("lemon", 0.5, "piece"),
            ing("fresh parsley", 5, "g"),
        ),
        prep=("Defrost the cod in the fridge overnight and make the tomato sauce ahead if you like.",),
        storage="Best fresh, but the sauce keeps four days and is good over pasta.",
        keeps_days=2,
    ),
    Recipe(
        id="lemongrass_chicken",
        name="Lemongrass chicken with rice",
        cuisine="Vietnamese",
        meal_slots=("Dinner",),
        diets=("Gluten-free", "Dairy-free", "High-protein"),
        proteins=("Chicken",),
        styles=("Stir-fry", "Bowl"),
        minutes=30,
        description="Sticky lemongrass and lime chicken with rice, cucumber and plenty of herbs.",
        ingredients=(
            ing("chicken thighs", 150, "g", "diced"),
            ing("jasmine rice", 80, "g"),
            ing("lime", 0.5, "piece"),
            ing("fish sauce", 0.5, "tbsp"),
            ing("garlic", 1, "clove"),
            ing("ginger", 6, "g"),
            ing("brown sugar", 1, "tsp"),
            ing("cucumber", 0.3, "piece"),
            ing("scallion", 0.5, "stalk"),
            ing("fresh cilantro", 5, "g"),
            ing("sesame oil", 0.5, "tsp"),
            ing("vegetable oil", 0.5, "tbsp"),
        ),
        prep=("Marinate the chicken in the lime, fish sauce, sugar and aromatics tonight.",),
        storage="Keeps three days; the cucumber and herbs are best added fresh.",
        keeps_days=3,
    ),
)


# --------------------------------------------------------------------------- #
# Derived metadata
# --------------------------------------------------------------------------- #


def _finalise(recipe: Recipe) -> Recipe:
    """Add clearly implied diet tags so filters never miss an obvious fit."""
    diets = set(recipe.diets)
    unknown = diets - set(DIET_OPTIONS)
    if unknown:
        raise ValueError(f"{recipe.id}: unknown diet tag(s) {sorted(unknown)}")

    if "Vegan" in diets:
        diets.update({"Vegetarian", "Dairy-free", "Pescatarian"})
    if "Vegetarian" in diets:
        diets.add("Pescatarian")
    if not (set(recipe.proteins) & MEAT_PROTEINS):
        diets.add("Pescatarian")
    if not {i.name for i in recipe.ingredients} & NUT_INGREDIENTS:
        diets.add("Nut-free")

    # Keep the canonical vocabulary order for stable display.
    ordered = tuple(tag for tag in DIET_OPTIONS if tag in diets)
    return Recipe(
        id=recipe.id,
        name=recipe.name,
        cuisine=recipe.cuisine,
        meal_slots=recipe.meal_slots,
        diets=ordered,
        proteins=recipe.proteins,
        styles=recipe.styles,
        minutes=recipe.minutes,
        description=recipe.description,
        ingredients=recipe.ingredients,
        prep=recipe.prep,
        storage=recipe.storage,
        keeps_days=recipe.keeps_days,
        freezes=recipe.freezes,
    )


RECIPES: tuple[Recipe, ...] = tuple(_finalise(recipe) for recipe in _RAW_RECIPES)
RECIPES_BY_ID: dict[str, Recipe] = {recipe.id: recipe for recipe in RECIPES}


def validate_library() -> list[str]:
    """Return a list of data problems. Empty means the library is consistent.

    Used by the development checks; the app itself does not need to call it.
    """
    problems: list[str] = []
    seen_ids: set[str] = set()

    for recipe in RECIPES:
        if recipe.id in seen_ids:
            problems.append(f"duplicate recipe id: {recipe.id}")
        seen_ids.add(recipe.id)

        if recipe.cuisine not in CUISINES:
            problems.append(f"{recipe.id}: unknown cuisine {recipe.cuisine!r}")
        if not recipe.meal_slots:
            problems.append(f"{recipe.id}: no meal slots")
        for slot in recipe.meal_slots:
            if slot not in MEAL_SLOTS:
                problems.append(f"{recipe.id}: unknown meal slot {slot!r}")
        for tag in recipe.proteins:
            if tag not in PROTEIN_OPTIONS:
                problems.append(f"{recipe.id}: unknown protein tag {tag!r}")
        for style in recipe.styles:
            if style not in STYLES:
                problems.append(f"{recipe.id}: unknown style {style!r}")
        if recipe.minutes <= 0:
            problems.append(f"{recipe.id}: minutes must be positive")
        if not recipe.ingredients:
            problems.append(f"{recipe.id}: no ingredients")

        names = [item.name for item in recipe.ingredients]
        for name in sorted(set(names)):
            if names.count(name) > 1:
                problems.append(f"{recipe.id}: ingredient listed twice: {name!r}")
            if name not in CATEGORY_OF:
                problems.append(f"{recipe.id}: ingredient without a category: {name!r}")

        if not recipe.storage:
            problems.append(f"{recipe.id}: missing storage note")

    # The same ingredient must be measured the same way everywhere, or the
    # shopping list has to show it as two separate lines.
    families: dict[str, set[str]] = {}
    for recipe in RECIPES:
        for item in recipe.ingredients:
            if item.unit in MASS_UNITS:
                family = "mass"
            elif item.unit in ("ml", "l"):
                family = "metric volume"
            elif item.unit in VOLUME_UNITS:
                family = "spoon volume"
            else:
                family = f"count:{item.unit}"
            families.setdefault(item.name, set()).add(family)

    for name, used in sorted(families.items()):
        kinds = {f.split(":")[0] for f in used}
        if len(kinds) > 1:
            problems.append(f"{name!r} is measured inconsistently: {sorted(used)}")
        elif "count" in kinds and len(used) > 1:
            problems.append(f"{name!r} uses several count units: {sorted(used)}")

    return problems
