"""
paws/backend/portions.py — ROUND 27: THE PORTION CALCULATOR (reviewer #7)
'Rex (35kg, 4yr, active) should eat ~X g/day of [the food you feed]'
- computed from weight, age, activity, and the food's calorie density.
Portion confusion is a top-3 pet-parent question; the weight × food ×
portion matrix is exactly what Hill's/Purina market against.
"""
import datetime

# maintenance energy: kcal per kg per day by life stage (simplified NRC)
ENERGY = {
    "puppy": 50.0,   # growing
    "adult": 30.0,   # maintenance
    "senior": 25.0,  # lighter
}

# activity multipliers
ACTIVITY = {"low": 0.85, "normal": 1.0, "high": 1.15}

# food energy density by type (kcal per 100g) — expandable via the catalog
DEFAULT_KCAL_PER_100G = {
    "dry": 350.0,
    "wet": 90.0,
    "treat": 400.0,
}


def life_stage(dob: str, species: str = "dog") -> str:
    """Adult at ~1yr (dog small) / 2yr (large dog) / 1yr (cat)."""
    try:
        d = datetime.date.fromisoformat(dob)
    except Exception:
        return "adult"
    months = ((datetime.date.today().year - d.year) * 12 +
              (datetime.date.today().month - d.month))
    if species == "cat":
        return "adult" if months >= 12 else "puppy"
    return "adult" if months >= 18 else "puppy"


def daily_grams(weight_kg: float, dob: str = "", activity: str = "normal",
                species: str = "dog", food_kcal_per_100g: float = None,
                food_type: str = "dry") -> dict:
    """Compute the daily feeding recommendation.
    - calories/day = weight × energy-per-kg × activity multiplier
    - grams/day    = calories / (kcal per 100g / 100)
    """
    stage = life_stage(dob, species)
    kcal_per_kg = ENERGY.get(stage, ENERGY["adult"])
    mult = ACTIVITY.get(activity.lower(), ACTIVITY["normal"])
    if food_kcal_per_100g is None:
        food_kcal_per_100g = DEFAULT_KCAL_PER_100G.get(food_type, 350.0)
    calories = weight_kg * kcal_per_kg * mult
    grams = calories / (food_kcal_per_100g / 100.0)
    return {
        "stage": stage,
        "calories_per_day": round(calories, 0),
        "grams_per_day": round(grams, 0),
        "grams_per_meal_2x": round(grams / 2, 0),
        "food_kcal_per_100g": food_kcal_per_100g,
        "note": (f"{'Puppy' if stage == 'puppy' else stage.capitalize()} · "
                 f"{activity} activity — feed ~{round(grams, 0)}g/day "
                 f"({round(grams / 2, 0)}g per meal if 2x/day). "
                 f"Adjust by body condition: ribs felt easily but not seen "
                 f"= ideal; ribs hard to feel = reduce; hips prominent = increase."),
    }
