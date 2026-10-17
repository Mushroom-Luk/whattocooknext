"""Rule-based meal planning, shopping aggregation and prep reminders.

The planner is fully deterministic: the same :class:`PlanRequest` always
produces the same plan (``variation`` is the knob the UI uses to shuffle).
There is no model call and no network access anywhere in this module.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .recipes import (
    CATEGORY_BLURB,
    CATEGORY_ORDER,
    MASS_UNITS,
    RECIPES,
    VOLUME_UNITS,
    Recipe,
    category_of,
    is_staple,
    shopping_hint,
)

#: How much extra to cook when a dish also has to cover a leftover lunch.
LEFTOVER_FACTOR = 1.75

#: A day with at most this many minutes of cooking is considered light.
QUICK_MINUTES = 30

#: At most this many leftover slots per plan.
MAX_LEFTOVER_DAYS = 3

_WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WEEKDAY_LONG = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)

_PLURALS = {
    "piece": "pieces",
    "clove": "cloves",
    "can": "cans",
    "bunch": "bunches",
    "slice": "slices",
    "stalk": "stalks",
    "head": "heads",
    "fillet": "fillets",
    "pinch": "pinches",
    "sheet": "sheets",
}

#: For ``piece`` units we pluralise the ingredient itself ("4 lemons",
#: "8 eggs") rather than saying "4 pieces of lemon". Mapped to
#: ``(singular, plural)``.
_COUNT_NOUNS = {
    "apple": ("apple", "apples"),
    "avocado": ("avocado", "avocados"),
    "banana": ("banana", "bananas"),
    "bell pepper": ("bell pepper", "bell peppers"),
    "carrot": ("carrot", "carrots"),
    "ciabatta roll": ("ciabatta roll", "ciabatta rolls"),
    "corn tortillas": ("corn tortilla", "corn tortillas"),
    "cucumber": ("cucumber", "cucumbers"),
    "eggs": ("egg", "eggs"),
    "flour tortillas": ("flour tortilla", "flour tortillas"),
    "jalapeño": ("jalapeño", "jalapeños"),
    "lemon": ("lemon", "lemons"),
    "lime": ("lime", "limes"),
    "mango": ("mango", "mangoes"),
    "onion": ("onion", "onions"),
    "pita bread": ("pita bread", "pita breads"),
    "potato": ("potato", "potatoes"),
    "red onion": ("red onion", "red onions"),
    "sweet potato": ("sweet potato", "sweet potatoes"),
    "tomatoes": ("tomato", "tomatoes"),
    "zucchini": ("zucchini", "zucchini"),
}

#: Proteins that are usually bought frozen and need a night to thaw.
_FREEZER_FRIENDLY = frozenset(
    {
        "beef strips", "chicken breast", "chicken thighs", "cod fillet", "ground beef",
        "ground lamb", "ground turkey", "pork chops", "salmon fillet", "shrimp",
    }
)

_GRAINS = frozenset({"jasmine rice", "basmati rice", "quinoa", "couscous", "risotto rice"})
_AROMATICS = frozenset({"garlic", "onion", "red onion", "ginger", "carrot", "celery"})


# --------------------------------------------------------------------------- #
# Request & results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlanRequest:
    """Everything the planner needs, straight from the Streamlit inputs."""

    servings: int
    days: tuple[date, ...]
    meal_slots: tuple[str, ...] = ("Dinner",)
    diets: tuple[str, ...] = ()
    cuisines: tuple[str, ...] = ()
    proteins: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    max_minutes: int = 60
    use_leftovers: bool = False
    variation: int = 0

    def key(self) -> tuple:
        """Hashable identity of the plan's structure (portions excluded)."""
        return (
            self.days,
            self.meal_slots,
            self.diets,
            self.cuisines,
            self.proteins,
            self.styles,
            self.keywords,
            self.avoid,
            self.max_minutes,
            self.use_leftovers,
            self.variation,
        )


@dataclass
class PlannedMeal:
    slot: str
    recipe: Recipe
    cook_servings: float
    leftover_from: str | None = None
    covers_leftover: bool = False

    @property
    def is_leftover(self) -> bool:
        return self.leftover_from is not None

    @property
    def scale(self) -> float:
        """Multiplier for the recipe's per-serving quantities (0 = reheat only)."""
        return 0.0 if self.is_leftover else self.cook_servings


@dataclass
class PlannedDay:
    day: date
    weekday: str
    weekday_long: str
    label: str
    meals: list[PlannedMeal] = field(default_factory=list)

    @property
    def cooking_minutes(self) -> int:
        return sum(meal.recipe.minutes for meal in self.meals if not meal.is_leftover)

    @property
    def is_heavy(self) -> bool:
        return self.cooking_minutes >= 60


@dataclass
class Plan:
    request: PlanRequest
    days: list[PlannedDay] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def meals(self) -> list[PlannedMeal]:
        return [meal for day in self.days for meal in day.meals]

    @property
    def cooked_meals(self) -> list[PlannedMeal]:
        return [meal for meal in self.meals if not meal.is_leftover]

    @property
    def recipe_count(self) -> int:
        return len({meal.recipe.id for meal in self.cooked_meals})

    @property
    def total_minutes(self) -> int:
        return sum(day.cooking_minutes for day in self.days)

    @property
    def average_minutes(self) -> int:
        active = [day.cooking_minutes for day in self.days if day.cooking_minutes]
        return round(sum(active) / len(active)) if active else 0

    @property
    def cuisines(self) -> list[str]:
        seen: list[str] = []
        for meal in self.cooked_meals:
            if meal.recipe.cuisine not in seen:
                seen.append(meal.recipe.cuisine)
        return seen

    @property
    def heaviest_day(self) -> PlannedDay | None:
        active = [day for day in self.days if day.cooking_minutes]
        return max(active, key=lambda day: day.cooking_minutes, default=None)


@dataclass
class ShoppingItem:
    name: str
    category: str
    amount: float
    kind: str  # "mass" | "volume" | "count"
    unit: str
    display: str
    meals: tuple[str, ...]
    note: str
    hint: str
    staple: bool


@dataclass
class Reminders:
    advance: list[str] = field(default_factory=list)
    batch: list[str] = field(default_factory=list)
    efficiency: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #


def _trim(value: float, decimals: int = 2) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def _base_amount(qty: float, unit: str) -> tuple[float, str, str]:
    """Convert ``qty`` in ``unit`` to ``(amount, kind, base_unit)`` for merging.

    Volume keeps two buckets so the display can stay in the unit the recipe
    was written in: metric (``ml``/``l``) versus spoons (``tsp``/``tbsp``/``cup``).
    """
    if unit in MASS_UNITS:
        return qty * MASS_UNITS[unit], "mass", "g"
    if unit in VOLUME_UNITS:
        return qty * VOLUME_UNITS[unit], "volume", "ml" if unit in ("ml", "l") else "spoon"
    return qty, "count", unit


def _round_up(value: float) -> float:
    """Round a count up so it works as a shopping amount (you buy whole lemons)."""
    if value <= 2:
        return math.ceil(value * 2) / 2
    return float(math.ceil(value))


def format_amount(amount: float, kind: str, unit: str, name: str = "") -> str:
    """Turn a base amount into something readable on a shopping list."""
    if amount <= 0:
        return "to taste"

    if kind == "mass":
        if amount >= 1000:
            return f"{_trim(round(amount / 1000, 1), 1)} kg"
        if amount >= 20:
            rounded = round(amount / 5) * 5
        elif amount >= 5:
            rounded = float(round(amount))
        else:
            rounded = round(amount, 1)
        return f"{_trim(rounded)} g"

    if kind == "volume":
        if unit == "spoon":
            # Written in spoons: keep spoons while that reads naturally.
            if amount >= 120:
                return f"{_trim(round(amount / 10) * 10)} ml"
            if amount >= 22.5 and math.isclose(amount % 7.5, 0, abs_tol=1e-6):
                return f"{_trim(amount / 15)} tbsp"
            if amount >= 40:
                return f"{_trim(round(amount / 5) * 5)} ml"
            if amount >= 2.5 and math.isclose(amount % 2.5, 0, abs_tol=1e-6):
                return f"{_trim(amount / 5)} tsp"
            if amount >= 15:
                return f"{_trim(round(amount / 15, 1), 1)} tbsp"
            return f"{_trim(round(amount, 1), 1)} ml"
        # Written in ml/l: stay metric.
        if amount >= 1000:
            return f"{_trim(round(amount / 1000, 1), 1)} L"
        if amount >= 100:
            return f"{_trim(round(amount / 10) * 10)} ml"
        return f"{_trim(round(amount))} ml"

    rounded = _round_up(amount)
    if unit == "piece" and name:
        singular, plural = _COUNT_NOUNS.get(name, (name, f"{name}s"))
        return f"1 {singular}" if rounded == 1 else f"{_trim(rounded)} {plural}"
    if rounded == 1:
        return f"1 {unit}"
    return f"{_trim(rounded)} {_PLURALS.get(unit, unit + 's')}"


def ingredient_label(name: str, quantity: str) -> str:
    """Join an amount to its ingredient without saying "1 lemon lemon"."""
    head = name.replace("canned ", "").split()[-1].rstrip("s").lower()
    if head and head in quantity.lower():
        return quantity
    if "can" in quantity.lower():
        return f"{quantity} {name.replace('canned ', '')}"
    return f"{quantity} {name}"


def scaled_ingredients(meal: PlannedMeal) -> list[tuple[str, str, str]]:
    """``(name, quantity, note)`` for one meal, scaled to what you cook."""
    if meal.is_leftover:
        return []
    rows = []
    for item in meal.recipe.ingredients:
        amount, kind, unit = _base_amount(item.qty * meal.cook_servings, item.unit)
        rows.append((item.name, format_amount(amount, kind, unit, item.name), item.note))
    return rows


def day_label(day: date) -> str:
    return f"{_WEEKDAY_SHORT[day.weekday()]} {day.day} {day:%b}"


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def _is_avoided(ingredient_name: str, avoid: tuple[str, ...]) -> bool:
    name = ingredient_name.lower()
    return any(term in name or name in term for term in avoid)


def _exclusion_reason(
    recipe: Recipe,
    slot: str,
    diets: tuple[str, ...],
    avoid: tuple[str, ...],
    max_minutes: int,
) -> str | None:
    if not recipe.suits(slot):
        return "slot"
    if not set(diets).issubset(recipe.diets):
        return "diet"
    if any(_is_avoided(item.name, avoid) for item in recipe.ingredients):
        return "avoid"
    if recipe.minutes > max_minutes:
        return "time"
    return None


def eligible_recipes(
    slot: str,
    diets: tuple[str, ...],
    avoid: tuple[str, ...],
    max_minutes: int,
) -> list[Recipe]:
    """Recipes that fit the hard constraints for one meal slot."""
    return [
        recipe
        for recipe in RECIPES
        if _exclusion_reason(recipe, slot, diets, avoid, max_minutes) is None
    ]


def _conflict_hint(
    slot: str,
    diets: tuple[str, ...],
    avoid: tuple[str, ...],
    max_minutes: int,
) -> str:
    """Explain which choice closes the door when a meal slot has no options."""
    options: list[tuple[int, str]] = []

    for tag in diets:
        relaxed = tuple(t for t in diets if t != tag)
        size = len(eligible_recipes(slot, relaxed, avoid, max_minutes))
        options.append((size, f"relaxing “{tag}” would open up {size} more option(s)"))

    if max_minutes < 120:
        size = len(eligible_recipes(slot, diets, avoid, 120))
        options.append((size, f"allowing up to 120 minutes of cooking would open up {size} option(s)"))

    for term in avoid:
        fewer = tuple(t for t in avoid if t != term)
        size = len(eligible_recipes(slot, diets, fewer, max_minutes))
        options.append((size, f"dropping the “{term}” exclusion would open up {size} option(s)"))

    best = max(options, default=(0, "try removing one of your filters"))
    if best[0] == 0:
        return "nothing in the library fits this combination — try removing one of your filters"
    return best[1]


def _keyword_hits(recipe: Recipe, keywords: tuple[str, ...]) -> int:
    if not keywords:
        return 0
    haystack = " ".join(
        (
            recipe.name,
            recipe.cuisine,
            recipe.description,
            " ".join(recipe.styles),
            " ".join(recipe.proteins),
            " ".join(item.name for item in recipe.ingredients),
        )
    ).lower()
    name = recipe.name.lower()
    hits = 0
    for keyword in keywords:
        if keyword in name:
            hits += 2
        elif keyword in haystack:
            hits += 1
    return hits


def _score(
    recipe: Recipe,
    request: PlanRequest,
    used: Counter[str],
    history: list[Recipe],
    rng: random.Random,
) -> float:
    score = 0.0

    if request.proteins and set(recipe.proteins) & set(request.proteins):
        score += 3.0
    if request.cuisines and recipe.cuisine in request.cuisines:
        score += 2.5
    if request.styles and set(recipe.styles) & set(request.styles):
        score += 2.0
    score += 2.5 * _keyword_hits(recipe, request.keywords)

    # Variety: no dish twice while there is an alternative, and avoid
    # back-to-back proteins, cuisines and cooking styles.
    score -= 1.5 * used[recipe.id]
    recent_proteins = {tag for other in history[-2:] for tag in other.proteins}
    recent_cuisines = {other.cuisine for other in history[-3:]}
    if set(recipe.proteins) & recent_proteins:
        score -= 0.6
    if recipe.cuisine in recent_cuisines:
        score -= 0.5
    if history and set(recipe.styles) & set(history[-1].styles):
        score -= 0.4

    score -= 0.02 * recipe.minutes
    score += rng.random() * 1.2
    return score


def build_plan(request: PlanRequest) -> Plan:
    """Choose a dish for every day and meal slot in the request."""
    plan = Plan(request=request)
    if not request.days:
        plan.notes.append("No days selected yet — pick at least one day to plan.")
        return plan

    rng = random.Random(hashlib.sha256(repr(request.key()).encode()).hexdigest())

    pools: dict[str, list[Recipe]] = {}
    for slot in request.meal_slots:
        pool = eligible_recipes(slot, request.diets, request.avoid, request.max_minutes)
        if not pool:
            plan.issues.append(
                f"No {slot.lower()} recipes match your filters — "
                f"{_conflict_hint(slot, request.diets, request.avoid, request.max_minutes)}."
            )
        pools[slot] = pool

    used: Counter[str] = Counter()
    history: list[Recipe] = []
    leftovers_planned = 0

    for day in request.days:
        planned = PlannedDay(
            day=day,
            weekday=_WEEKDAY_SHORT[day.weekday()],
            weekday_long=_WEEKDAY_LONG[day.weekday()],
            label=day_label(day),
        )

        for slot in request.meal_slots:
            pool = pools[slot]
            if not pool:
                continue

            if slot == "Lunch" and request.use_leftovers and leftovers_planned < MAX_LEFTOVER_DAYS:
                source = _leftover_source(plan.days)
                if source is not None and rng.random() < 0.55:
                    meal, source_label = source
                    meal.covers_leftover = True
                    meal.cook_servings = math.ceil(request.servings * LEFTOVER_FACTOR)
                    planned.meals.append(
                        PlannedMeal(
                            slot=slot,
                            recipe=meal.recipe,
                            cook_servings=0.0,
                            leftover_from=source_label,
                        )
                    )
                    leftovers_planned += 1
                    continue

            fresh = [recipe for recipe in pool if used[recipe.id] == 0] or pool
            chosen = max(fresh, key=lambda r: _score(r, request, used, history, rng))

            planned.meals.append(
                PlannedMeal(slot=slot, recipe=chosen, cook_servings=float(request.servings))
            )
            used[chosen.id] += 1
            history.append(chosen)

        plan.days.append(planned)

    for recipe_id, count in used.items():
        if count > 1:
            name = next(r.name for r in RECIPES if r.id == recipe_id)
            plan.notes.append(
                f"{name} appears {count} times — cook it once and carry the second portion over."
            )
    if request.use_leftovers and not leftovers_planned:
        plan.notes.append("No leftover days fitted this week, so every meal is a fresh cook.")

    return plan


def _leftover_source(planned_days: list[PlannedDay]) -> tuple[PlannedMeal, str] | None:
    """A recent, well-keeping dinner that has not already covered a lunch."""
    if not planned_days:
        return None
    for day in reversed(planned_days[-2:]):
        for meal in day.meals:
            if (
                meal.slot == "Dinner"
                and meal.recipe.keeps_days >= 3
                and not meal.is_leftover
                and not meal.covers_leftover
            ):
                return meal, day.label
    return None


# --------------------------------------------------------------------------- #
# Shopping list
# --------------------------------------------------------------------------- #


def build_shopping_list(plan: Plan) -> list[ShoppingItem]:
    """Merge every ingredient in the plan into one de-duplicated shopping list."""
    totals: dict[tuple[str, str, str], float] = {}
    meals_by_key: dict[tuple[str, str, str], list[str]] = {}
    notes: dict[tuple[str, str, str], str] = {}

    for day in plan.days:
        for meal in day.meals:
            if meal.is_leftover:
                continue
            for item in meal.recipe.ingredients:
                amount, kind, unit = _base_amount(item.qty * meal.scale, item.unit)
                key = (item.name, kind, unit)
                totals[key] = totals.get(key, 0.0) + amount
                meals_by_key.setdefault(key, []).append(meal.recipe.name)
                if item.note and key not in notes:
                    notes[key] = item.note

    items = []
    for (name, kind, unit), amount in totals.items():
        items.append(
            ShoppingItem(
                name=name,
                category=category_of(name),
                amount=amount,
                kind=kind,
                unit=unit,
                display=format_amount(amount, kind, unit, name),
                meals=tuple(dict.fromkeys(meals_by_key[(name, kind, unit)])),
                note=notes.get((name, kind, unit), ""),
                hint=shopping_hint(name),
                staple=is_staple(name),
            )
        )

    items.sort(key=lambda item: (CATEGORY_ORDER.index(item.category), item.name))
    return items


def group_shopping_list(items: list[ShoppingItem]) -> dict[str, list[ShoppingItem]]:
    """Split a shopping list into the three shopping aisles."""
    grouped: dict[str, list[ShoppingItem]] = {category: [] for category in CATEGORY_ORDER}
    for item in items:
        grouped[item.category].append(item)
    return grouped


def shopping_list_text(items: list[ShoppingItem], *, hide_staples: bool = True) -> str:
    """Plain-text shopping list for the download button."""
    lines: list[str] = []
    for category in CATEGORY_ORDER:
        group = [item for item in items if item.category == category]
        if hide_staples:
            group = [item for item in group if not item.staple]
        if not group:
            continue
        lines.append(f"{category.upper()} — {CATEGORY_BLURB[category]}")
        for item in group:
            hint = f"  ({item.hint})" if item.hint else ""
            lines.append(f"  [ ] {item.name} — {item.display}{hint}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #


def build_reminders(plan: Plan, shopping: list[ShoppingItem]) -> Reminders:
    """Advance prep, batch cooking and efficiency advice for a plan."""
    reminders = Reminders()
    if not plan.days:
        return reminders
    _add_advance_prep(plan, reminders)
    _add_batch_advice(plan, shopping, reminders)
    _add_efficiency_tips(plan, shopping, reminders)
    return reminders


def _add_advance_prep(plan: Plan, reminders: Reminders) -> None:
    first_label = plan.days[0].label

    for index, day in enumerate(plan.days):
        tasks: list[str] = []
        for meal in day.meals:
            if meal.is_leftover:
                continue
            tasks.extend((task, meal.recipe.name) for task in meal.recipe.prep)
        if not tasks:
            continue
        when = "**Before you start**" if index == 0 else f"**{plan.days[index - 1].label} evening**"
        for task, name in tasks:
            reminders.advance.append(f"{when} — {task} *({day.label}: {name})*")

    frozen = sorted(
        {
            item.name
            for meal in plan.cooked_meals
            for item in meal.recipe.ingredients
            if item.name in _FREEZER_FRIENDLY
        }
    )
    if frozen:
        reminders.advance.append(
            "**Defrost** — if any "
            + ", ".join(frozen)
            + " is in the freezer, move it to the fridge the night before; never thaw it on the counter."
        )

    if any(meal.slot == "Breakfast" for meal in plan.days[0].meals):
        reminders.advance.append(
            f"**{first_label} night before** — portion the grab-and-go breakfast so the first morning is calm."
        )

    reminders.advance = reminders.advance[:10]


def _add_batch_advice(plan: Plan, shopping: list[ShoppingItem], reminders: Reminders) -> None:
    for meal in (m for m in plan.meals if m.is_leftover):
        reminders.batch.append(
            f"Cook a **{_trim(LEFTOVER_FACTOR)}× batch** of {meal.recipe.name} on {meal.leftover_from} — "
            f"that is dinner plus the {meal.slot.lower()} it also covers. Portion it up while it cools."
        )

    for meal in [m for m in plan.cooked_meals if m.recipe.freezes][:3]:
        reminders.batch.append(
            f"{meal.recipe.name} freezes well — freeze what you will not eat within a few days."
        )

    for meal in [m for m in plan.cooked_meals if m.recipe.keeps_days >= 4][:3]:
        reminders.batch.append(
            f"{meal.recipe.name}: keeps {meal.recipe.keeps_days} days in the fridge. {meal.recipe.storage}"
        )

    for item in [i for i in shopping if len(i.meals) >= 3 and not i.staple][:4]:
        reminders.batch.append(
            f"{ingredient_label(item.name, item.display).capitalize()} appears in "
            f"{len(item.meals)} meals — buy it once and prep it on day one."
        )

    reminders.batch = reminders.batch[:8]


def _add_efficiency_tips(plan: Plan, shopping: list[ShoppingItem], reminders: Reminders) -> None:
    heaviest = plan.heaviest_day
    if heaviest and heaviest.cooking_minutes >= 45:
        light = [
            day for day in plan.days
            if day.cooking_minutes and day.cooking_minutes <= QUICK_MINUTES
        ]
        tip = f"{heaviest.label} is your heaviest day at {heaviest.cooking_minutes} minutes of cooking."
        if light:
            tip += (
                f" {light[0].label} is only {light[0].cooking_minutes} minutes, so swap dishes "
                "between those two days if the week feels tight."
            )
        else:
            tip += " Cook a double batch on the calmest evening so one night is just reheating."
        reminders.efficiency.append(tip)

    trays = [meal.recipe.name for meal in plan.cooked_meals if "Traybake" in meal.recipe.styles]
    if len(trays) >= 2:
        reminders.efficiency.append(
            f"{len(trays)} of your dinners are traybakes ({', '.join(trays[:3])}) — when the oven is on, "
            "roast two trays and refrigerate the second for a busy evening."
        )

    grains = [item for item in shopping if item.name in _GRAINS]
    if grains:
        total = ", ".join(ingredient_label(item.name, item.display) for item in grains[:3])
        reminders.efficiency.append(
            f"Cook grains once: the plan needs {total}. One pot now beats three separate batches later."
        )

    aromatics = [item for item in shopping if item.name in _AROMATICS]
    if aromatics:
        total = ", ".join(ingredient_label(item.name, item.display) for item in aromatics[:5])
        reminders.efficiency.append(
            f"Chop once, cook all week — {total}. Keep chopped onion, garlic and ginger in a covered box "
            "in the fridge for up to four days."
        )

    if plan.total_minutes:
        reminders.efficiency.append(
            f"The whole plan is about {plan.total_minutes} minutes of cooking "
            f"({plan.average_minutes} on an average cooking day). Read the day's recipe first and get "
            "every ingredient out before you turn on the heat."
        )

    leftovers = [meal for meal in plan.meals if meal.is_leftover]
    if leftovers:
        meal = leftovers[0]
        reminders.efficiency.append(
            f"{meal.leftover_from} already covers your {meal.slot.lower()} — reheat it gently with a splash "
            "of water or stock so it does not dry out."
        )

    reminders.efficiency = reminders.efficiency[:6]


# --------------------------------------------------------------------------- #
# Markdown export
# --------------------------------------------------------------------------- #


def plan_markdown(plan: Plan, shopping: list[ShoppingItem], reminders: Reminders) -> str:
    """Render the full assistant answer as Markdown (used by the download button)."""
    request = plan.request
    lines: list[str] = [
        "# Your meal plan",
        "",
        f"**{request.servings} people** · {len(plan.days)} day(s) · "
        f"{', '.join(request.meal_slots)} · about {plan.total_minutes} minutes of cooking",
        "",
    ]
    if request.diets:
        lines.append(f"**Dietary needs:** {', '.join(request.diets)}")
    if request.cuisines:
        lines.append(f"**Cuisines:** {', '.join(request.cuisines)}")
    if request.diets or request.cuisines:
        lines.append("")

    for note in plan.issues:
        lines += [f"> **Heads-up:** {note}", ""]
    for note in plan.notes:
        lines += [f"> {note}", ""]

    lines += ["## 1. Suggested meal plan", ""]
    for day in plan.days:
        lines.append(f"### {day.weekday_long} · {day.label}")
        lines.append("")
        if not day.meals:
            lines += ["_No meals could be planned for this day._", ""]
            continue
        lines.append(f"_About {day.cooking_minutes} minutes of cooking._")
        lines.append("")
        for meal in day.meals:
            if meal.is_leftover:
                lines += [
                    f"- **{meal.slot} — {meal.recipe.name}** (leftovers from {meal.leftover_from})",
                    f"  {meal.recipe.description}",
                    "",
                ]
                continue
            batch = (
                f" · cook {meal.cook_servings:.0f} portions"
                if meal.cook_servings > request.servings
                else ""
            )
            lines += [
                f"- **{meal.slot} — {meal.recipe.name}**",
                f"  {meal.recipe.description}",
                f"  Serves {request.servings}{batch} · {meal.recipe.cuisine} · {meal.recipe.minutes} minutes",
            ]
            if meal.recipe.diets:
                lines.append(f"  _Tags: {', '.join(meal.recipe.diets[:4])}_")
            lines += ["", "  Ingredients:", ""]
            for name, quantity, note in scaled_ingredients(meal):
                suffix = f" — {note}" if note else ""
                lines.append(f"  - {ingredient_label(name, quantity)}{suffix}")
            lines.append("")

    lines += ["## 2. Master grocery shopping list", ""]
    for category in CATEGORY_ORDER:
        items = [item for item in shopping if item.category == category]
        if not items:
            continue
        lines += [f"### {category} — {CATEGORY_BLURB[category]}", ""]
        for item in items:
            count = len(item.meals)
            suffix = f" _(for {count} meal{'s' if count != 1 else ''})_"
            if item.staple:
                suffix += " _— pantry staple_"
            hint = f" ({item.hint})" if item.hint else ""
            lines.append(f"- **{item.name}** — {item.display}{hint}{suffix}")
        lines.append("")

    lines += ["## 3. Preparation & cooking reminders", ""]
    for heading, entries, empty in (
        ("Advance prep & defrosting", reminders.advance, "Nothing to prep in advance this week."),
        ("Batch cooking & storage", reminders.batch, "No batch cooking needed this week."),
        ("Cooking efficiency", reminders.efficiency, "A light week — nothing to optimise."),
    ):
        lines += [f"### {heading}", ""]
        lines += [f"- {entry}" for entry in entries] if entries else [f"- {empty}"]
        lines.append("")

    lines += [
        "---",
        "",
        "_Quantities are estimates scaled for the number of people above. "
        "Check labels if you are cooking for an allergy._",
    ]
    return "\n".join(lines)
