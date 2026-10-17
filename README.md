# What to cook next

A Streamlit meal planner that turns three inputs — how many people, which days, and what
you like to eat — into a week of dinners (or breakfast, lunch and dinner), one merged
shopping list, and the prep that makes the week actually fit.

Everything is generated **locally** from the recipe library in `utils/recipes.py` using a
scoring planner. No model calls, no API keys, no accounts, nothing leaves the machine.

## What you get

1. **Suggested meal plan** — a day-by-day menu with a description, cook time, diet tags and
   portions scaled to your table. Each dish opens to its own scaled ingredient list.
2. **Master grocery shopping list** — grouped into Produce, Proteins & Meat and Pantry &
   Dairy, with duplicate ingredients merged and added up across every meal (all the garlic
   in the week becomes one line). Counts round up to what you actually buy, pantry staples
   can be hidden, and the list downloads as a plain-text shopping checklist.
3. **Preparation & cooking reminders** — what to marinate, soak or defrost the night before,
   what to batch cook and how to store it, plus efficiency tips derived from the plan
   itself (heaviest day, grains worth cooking once, aromatics worth chopping once).

## Inputs

| Input | Notes |
| --- | --- |
| Number of people | Scales every portion and every shopping quantity. |
| Weekdays or date range | Pick a working week, or any calendar range (up to 14 days). |
| Meals to plan | Dinner only, lunch + dinner, or all three meals. |
| Time on your busiest night | Hard ceiling on cooking time. |
| Dietary needs | Hard filters: Vegetarian, Vegan, Pescatarian, Gluten-free, Dairy-free, Low-carb, High-protein, Nut-free. |
| Cuisines, proteins, dish styles | Preferences that bias the planner rather than filtering it. |
| Craving something specific? | Comma-separated words (`curry, tacos, traybake`) that boost matching recipes. |
| Avoid ingredients | Anything nobody will eat, or an allergy to route around. |
| Let some dinners cover a lunch | Cook once, eat twice: a few dinners become bigger batches that fill the next lunch. |

The plan is deterministic: the same inputs always give the same week. **Shuffle the plan**
bumps a variation counter when you want a different draw.

## Running it

Prerequisite: install [`uv`](https://docs.astral.sh/uv/).

```
uv sync
uv run streamlit run streamlit_app.py
```

No `uv`? A virtual environment works just as well:

```
python -m venv .venv
.venv\Scripts\pip install streamlit      # Windows
.venv/bin/pip install streamlit          # macOS / Linux
.venv\Scripts\streamlit run streamlit_app.py
```

## How the planner decides

1. **Filter** the library down to recipes that suit the meal slot, satisfy every dietary
   need, avoid your excluded ingredients and fit inside the time limit.
2. **Score** the survivors: preferred proteins, cuisines and dish styles add points, your
   keywords add more, and repeated proteins, cuisines, styles and dishes lose points so the
   week stays varied. A seed from the request keeps tie-breaks stable.
3. **Assign** greedily, day by day and slot by slot, converting some lunches into leftovers
   of an earlier dinner when that option is on.
4. **Merge** every ingredient into the shopping list (unit-aware, so `2 tbsp` and `1 tsp`
   of the same spice become `5 tsp`), then derive the reminders from what the plan actually
   contains.

## Project layout

```
streamlit_app.py     Streamlit UI: inputs, the three output sections, downloads
utils/recipes.py     Recipe library, diet/unit vocabulary, shopping categories, validation
utils/planner.py     Selection, scaling, shopping aggregation, reminders, Markdown export
verify_data.py       Dev check: validates the library and smoke-tests the planner
```

### Adding a recipe

Append a `Recipe(...)` to `_RAW_RECIPES` in `utils/recipes.py`. Ingredients are authored
for **one serving**, using canonical shopping names (`garlic`, not "2 cloves of garlic"),
which is what lets the shopping list merge duplicates. Then run:

```
uv run python verify_data.py
```

It fails loudly if an ingredient has no shopping category, a diet tag is unknown, one
ingredient is measured two different ways, or a storage note is missing.

## Assistant brief

The app is the implementation of this brief, kept here so the behaviour stays documented.

> You are an AI culinary assistant and meal planner embedded in a Streamlit app. Your goal
> is to generate tailored meal plans, structured grocery lists and preparation reminders
> from the user's inputs.
>
> **Inputs:** number of people; target weekdays or date range; dietary preferences and dish
> types (cuisines, restrictions, preferred proteins, specific dishes).
>
> **Output:** (1) a day-by-day meal plan with names, descriptions, portions scaled to the
> number of people and diet tags; (2) a grocery list split into Produce, Proteins & Meat and
> Pantry & Dairy, with duplicate ingredients combined and quantities scaled for the people
> and days requested; (3) preparation and cooking reminders covering advance prep and
> defrosting, batch cooking and storage, and cooking efficiency.
>
> **Behaviour:** be practical and specific, scale portions honestly, never invent an
> ingredient list that does not match the plan, and surface the trade-offs when a request
> cannot be met (for example, a combination of dietary filters that leaves no recipes).
>
> **Tone:** warm, direct and kitchen-practical. Talk to the cook, not about food. Prefer
> short, concrete instructions over prose, skip the hype and the health sermonising, and
> flag anything uncertain instead of bluffing it.

Because the plan is generated by rules rather than a language model, this behaviour is
enforced in code: quantities come from the same recipe data the plan uses, and conflicting
filters produce an explicit warning with a suggestion for which filter to relax.
