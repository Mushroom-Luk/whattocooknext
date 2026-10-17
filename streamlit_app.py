"""What to cook next — a meal planner, shopping list and prep guide.

The whole answer is generated locally from the recipe library in
:mod:`utils.recipes` (rule-based scoring, no model calls, no API keys).
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from utils.planner import (
    PlanRequest,
    PlannedMeal,
    build_plan,
    build_reminders,
    build_shopping_list,
    group_shopping_list,
    ingredient_label,
    plan_markdown,
    scaled_ingredients,
    shopping_list_text,
)
from utils.recipes import (
    CATEGORY_BLURB,
    CATEGORY_ORDER,
    CUISINES,
    DIET_OPTIONS,
    PROTEIN_OPTIONS,
    RECIPES,
    STYLES,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULT_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")

MEAL_CHOICES: dict[str, tuple[str, ...]] = {
    "Dinner": ("Dinner",),
    "Lunch + dinner": ("Lunch", "Dinner"),
    "All meals": ("Breakfast", "Lunch", "Dinner"),
}

DIET_COLORS: dict[str, str] = {
    "Vegan": "green",
    "Vegetarian": "green",
    "Pescatarian": "blue",
    "Gluten-free": "orange",
    "Dairy-free": "violet",
    "Low-carb": "yellow",
    "High-protein": "primary",
    "Nut-free": "gray",
}

MAX_PLANNED_DAYS = 14


def ingredient_vocabulary() -> list[str]:
    """Every ingredient in the library, for the "avoid" picker."""
    return sorted({item.name for recipe in RECIPES for item in recipe.ingredients})


def diet_badges(recipe, selected: tuple[str, ...], limit: int = 4) -> list[str]:
    """Diet tags to show, prioritising the ones the user actually asked for."""
    ordered = [tag for tag in selected if tag in recipe.diets]
    ordered += [tag for tag in recipe.diets if tag not in ordered]
    return ordered[:limit]


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def pick_weekdays(anchor: date) -> tuple[date, ...]:
    """Days chosen from a normal working week."""
    week_start = anchor - timedelta(days=anchor.weekday())
    picked = st.pills(
        "Days to plan",
        WEEKDAYS,
        selection_mode="multi",
        default=DEFAULT_WEEKDAYS,
        key="weekday_picks",
    )
    return tuple(
        week_start + timedelta(days=index)
        for index, name in enumerate(WEEKDAYS)
        if name in (picked or ())
    )


def pick_date_range() -> tuple[date, ...]:
    """Days chosen from an explicit calendar range."""
    picked = st.date_input(
        "Date range",
        value=(date.today(), date.today() + timedelta(days=4)),
        format="YYYY/MM/DD",
        help="Pick the first and last day you want planned.",
    )
    if not isinstance(picked, (tuple, list)) or len(picked) != 2:
        st.caption("Pick a start and an end date.")
        return ()
    start, end = picked
    span = (end - start).days + 1
    if span > MAX_PLANNED_DAYS:
        st.caption(f"That is {span} days — planning the first {MAX_PLANNED_DAYS}.")
        span = MAX_PLANNED_DAYS
    return tuple(start + timedelta(days=offset) for offset in range(max(span, 0)))


def sidebar_inputs() -> PlanRequest:
    """Render every input control and return the resulting request."""
    vocabulary = ingredient_vocabulary()
    st.session_state.setdefault("variation", 0)

    with st.sidebar:
        st.header("Plan settings", icon=":material/tune:")

        servings = st.number_input(
            "Number of people",
            min_value=1,
            max_value=12,
            value=4,
            help="Every portion and quantity below is scaled to this.",
        )

        mode = st.segmented_control(
            "Plan by", ("Weekdays", "Date range"), default="Weekdays", key="day_mode"
        )
        if mode == "Date range":
            days = pick_date_range()
        else:
            anchor = st.date_input(
                "Week containing",
                value=date.today(),
                format="YYYY/MM/DD",
                help="Any date in the week you want to cook for.",
            )
            days = pick_weekdays(anchor)

        meal_choice = st.segmented_control(
            "Meals to plan",
            tuple(MEAL_CHOICES),
            default="Lunch + dinner",
            key="meal_choice",
        )
        meal_slots = MEAL_CHOICES.get(meal_choice or "Dinner", ("Dinner",))

        max_minutes = st.slider(
            "Time on your busiest night",
            min_value=15,
            max_value=90,
            value=45,
            step=5,
            format="%d min",
            help="Recipes that take longer are left out of the plan.",
        )

        use_leftovers = st.toggle(
            "Let some dinners cover a lunch",
            value=False,
            help="Cooks a bigger batch on a few evenings so the next lunch is already made.",
        )

        st.divider()
        st.markdown("**Dietary needs & tastes**")

        diets = st.pills(
            "Dietary needs",
            DIET_OPTIONS,
            selection_mode="multi",
            help="Hard filters: every planned meal must match all of them.",
        ) or ()
        cuisines = st.multiselect(
            "Cuisines you fancy", CUISINES, placeholder="Any cuisine"
        )
        proteins = st.pills(
            "Preferred proteins", PROTEIN_OPTIONS, selection_mode="multi"
        ) or ()
        styles = st.pills("Dish styles", STYLES, selection_mode="multi") or ()
        keywords = st.text_input(
            "Craving something specific?",
            placeholder="curry, tacos, traybake",
            help="Words to look for in the recipe library, separated by commas.",
        )
        avoid = st.multiselect(
            "Avoid ingredients",
            vocabulary,
            placeholder="Nothing to avoid",
            help="Useful for allergies and for the one thing nobody will eat.",
        )

        st.divider()
        if st.button("Shuffle the plan", icon=":material/casino:", width="stretch"):
            st.session_state["variation"] += 1

    terms = tuple(
        term.strip().lower()
        for term in keywords.replace(";", ",").split(",")
        if term.strip()
    )

    return PlanRequest(
        servings=servings,
        days=days,
        meal_slots=meal_slots,
        diets=tuple(diets),
        cuisines=tuple(cuisines),
        proteins=tuple(proteins),
        styles=tuple(styles),
        keywords=terms,
        avoid=tuple(term.lower() for term in avoid),
        max_minutes=max_minutes,
        use_leftovers=use_leftovers,
        variation=st.session_state["variation"],
    )


# --------------------------------------------------------------------------- #
# Output sections
# --------------------------------------------------------------------------- #


def render_meal(
    meal: PlannedMeal,
    servings: int,
    diet_filters: tuple[str, ...],
    widget_key: str,
) -> None:
    if meal.is_leftover:
        st.markdown(f"**{meal.slot} · {meal.recipe.name}**")
        st.caption(
            f"No cooking — reheat the portion you cooked on {meal.leftover_from}. {meal.recipe.storage}"
        )
        return

    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{meal.slot} · {meal.recipe.name}**")
        for tag in diet_badges(meal.recipe, diet_filters):
            st.badge(tag, color=DIET_COLORS.get(tag, "gray"))

    st.caption(meal.recipe.description)

    facts = [f"{meal.recipe.minutes} min", f"Serves {servings}", meal.recipe.cuisine]
    if meal.cook_servings > servings:
        facts.append(f"cook {meal.cook_servings:.0f} portions")
    st.caption(" · ".join(facts))

    with st.popover(
        "Scaled ingredients", icon=":material/list_alt:", key=f"ing-{widget_key}"
    ):
        rows = [
            {"Ingredient": name, "Amount": quantity, "Prep": note}
            for name, quantity, note in scaled_ingredients(meal)
        ]
        st.dataframe(
            rows,
            hide_index=True,
            key=f"ing-table-{widget_key}",
            column_config={
                "Ingredient": st.column_config.TextColumn(width="medium"),
                "Amount": st.column_config.TextColumn(width="small"),
                "Prep": st.column_config.TextColumn(width="large"),
            },
            alt=f"Ingredients for {meal.recipe.name} scaled to {servings} servings",
        )
        if meal.recipe.prep:
            st.caption("Advance prep: " + " ".join(meal.recipe.prep))
        st.caption("Storage: " + meal.recipe.storage)


def render_meal_plan(plan, servings: int, diet_filters: tuple[str, ...]) -> None:
    if plan.issues:
        for issue in plan.issues:
            st.warning(issue, icon=":material/report:")
    for note in plan.notes:
        st.info(note, icon=":material/lightbulb:")

    meals_planned = len(plan.meals)
    with st.container(horizontal=True):
        st.metric("People", servings, border=True)
        st.metric("Days", len(plan.days), border=True)
        st.metric(
            "Meals",
            meals_planned,
            delta=f"{len(plan.cooked_meals)} to cook" if plan.meals else None,
            delta_color="off",
            border=True,
            icon=":material/restaurant:",
        )
        st.metric(
            "Cooking time",
            f"{plan.total_minutes} min",
            help="Total hands-on cooking across the plan, by day.",
            border=True,
            icon=":material/schedule:",
            chart_data=[day.cooking_minutes for day in plan.days],
            chart_type="bar",
        )
        st.metric("Different dishes", plan.recipe_count, border=True)

    for day in plan.days:
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"#### {day.weekday_long} · {day.label}")
                st.badge(
                    f"{day.cooking_minutes} min cooking",
                    color="red" if day.is_heavy else "green",
                    icon=":material/schedule:",
                )
                st.badge(day.weekday, color="gray", icon=":material/calendar_today:")
            if not day.meals:
                st.caption("No recipes matched your filters for this day.")
                continue
            for meal in day.meals:
                render_meal(
                    meal,
                    servings,
                    diet_filters,
                    widget_key=f"{day.label}-{meal.slot}",
                )


def render_shopping_list(plan, shopping, reminders) -> None:
    hide_staples = st.toggle(
        "Hide the pantry staples I already own",
        value=True,
        help="Salt, pepper, oil, flour, sugar and butter.",
    )
    st.caption(
        f"Every quantity is scaled for {plan.request.servings} people across "
        f"{len(plan.days)} day(s), with repeat ingredients already added together. "
        "Counts are rounded up to what you actually buy."
    )

    grouped = group_shopping_list(shopping)
    for category in CATEGORY_ORDER:
        items = [
            item
            for item in grouped[category]
            if not (hide_staples and item.staple)
        ]
        if not items:
            continue
        with st.container(border=True):
            st.markdown(f"#### {category}")
            st.caption(f"{CATEGORY_BLURB[category]} · {len(items)} items")
            rows = []
            for item in items:
                used = len(item.meals)
                rows.append(
                    {
                        "Item": item.name + (" (staple)" if item.staple else ""),
                        "Quantity": item.display,
                        "Used in": f"{used} meal{'s' if used != 1 else ''}",
                        "Note": item.hint or item.note,
                    }
                )
            st.dataframe(
                rows,
                hide_index=True,
                key=f"shop-{category}",
                column_config={
                    "Item": st.column_config.TextColumn(width="medium"),
                    "Quantity": st.column_config.TextColumn(width="small"),
                    "Used in": st.column_config.TextColumn(width="small"),
                    "Note": st.column_config.TextColumn(width="large"),
                },
                alt=f"{category}: {len(items)} items to buy",
            )

    with st.container(horizontal=True):
        st.download_button(
            "Shopping list",
            data=shopping_list_text(shopping, hide_staples=hide_staples),
            file_name="shopping-list.txt",
            mime="text/plain",
            icon=":material/download:",
        )
        st.download_button(
            "Whole plan",
            data=plan_markdown(plan, shopping, reminders),
            file_name="meal-plan.md",
            mime="text/markdown",
            icon=":material/description:",
        )


def render_reminders(reminders) -> None:
    sections = (
        (
            "Advance prep & defrosting",
            ":material/kitchen:",
            "Get these done the night before and the cooking day gets much shorter.",
            reminders.advance,
        ),
        (
            "Batch cooking & storage",
            ":material/inventory_2:",
            "Cook once, eat twice — and keep what you make in good shape.",
            reminders.batch,
        ),
        (
            "Cooking efficiency",
            ":material/bolt:",
            "How to spend less time at the stove this week.",
            reminders.efficiency,
        ),
    )
    columns = st.columns(3, gap="medium")
    for column, (title, icon, blurb, entries) in zip(columns, sections):
        with column, st.container(border=True):
            st.markdown(f"**{icon} {title}**")
            st.caption(blurb)
            if entries:
                st.markdown("\n".join(f"- {entry}" for entry in entries))
            else:
                st.caption("Nothing needed this week.")


def render_empty_state() -> None:
    st.info(
        "Pick at least one day in the sidebar and your plan appears here.",
        icon=":material/calendar_month:",
    )
    columns = st.columns(3, gap="medium")
    for column, (title, icon, body) in zip(
        columns,
        (
            (
                "1 · The meal plan",
                ":material/restaurant_menu:",
                "A day-by-day menu with portions scaled to your table, cook times, "
                "diet tags and the ingredient list for each dish.",
            ),
            (
                "2 · The shopping list",
                ":material/shopping_cart:",
                "Repeat ingredients are merged into one line per item, grouped by aisle, "
                "so you shop once instead of five times.",
            ),
            (
                "3 · The prep plan",
                ":material/schedule:",
                "What to marinate, soak or defrost the night before, what to batch cook, "
                "and how to keep busy evenings short.",
            ),
        ),
    ):
        with column, st.container(border=True):
            st.markdown(f"**{icon} {title}**")
            st.caption(body)


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="What to cook next",
    page_icon=":material/restaurant:",
    layout="wide",
)

request = sidebar_inputs()

st.title("What to cook next", icon=":material/restaurant:")
st.caption(
    f"A weekly menu, one merged shopping list and the prep that makes it fit real evenings. "
    f"{len(RECIPES)} recipes, planned on your machine — no accounts, no API keys."
)

if not request.days:
    render_empty_state()
    st.stop()

plan = build_plan(request)
shopping = build_shopping_list(plan)
reminders = build_reminders(plan, shopping)

st.header("1. Suggested meal plan", icon=":material/restaurant_menu:", divider="gray")
render_meal_plan(plan, request.servings, request.diets)

st.header("2. Master grocery shopping list", icon=":material/shopping_cart:", divider="gray")
render_shopping_list(plan, shopping, reminders)

st.header("3. Preparation & cooking reminders", icon=":material/schedule:", divider="gray")
render_reminders(reminders)

st.divider()
st.caption(
    "Quantities are estimates scaled for the number of people above. "
    "Check labels if you are cooking for an allergy."
)
