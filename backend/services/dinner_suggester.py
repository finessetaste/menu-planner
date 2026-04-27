"""
No-repeat dinner suggestion engine.
Scores dinner options by overlap with the day's school lunch.
Lower score = fewer repeated main elements = better suggestion.
"""

PROTEINS = {
    "pollo", "pechuga", "muslo", "merluza", "salmón", "salmon",
    "atún", "atun", "ternera", "cerdo", "huevo", "huevos", "gambas",
    "bacalao", "dorada", "lubina", "sepia", "calamar", "calamares",
    "pavo", "cordero", "rape", "langostinos", "mejillones", "almejas",
}

CARBS = {
    "arroz", "pasta", "patata", "patatas", "pan", "lentejas",
    "garbanzos", "quinoa", "avena", "macarrones", "espagueti",
    "espaguetis", "fideos", "cuscús", "cous", "boniato",
}

VEGETABLES = {
    "zanahoria", "espinacas", "brócoli", "brocoli", "judías",
    "tomate", "tomates", "pimiento", "pimientos", "lechuga",
    "cebolla", "cebollas", "calabacín", "ensalada", "verduras",
    "menestra", "acelgas", "col", "coliflor", "alcachofa",
}

ALL_KEYWORDS = PROTEINS | CARBS | VEGETABLES


def extract_elements(text: str) -> set[str]:
    """Extract main food elements from a meal description."""
    tl = text.lower()
    return {kw for kw in ALL_KEYWORDS if re.search(rf"\b{re.escape(kw)}", tl)}


def conflict_score(lunch_text: str, dinner_text: str) -> int:
    """Number of main elements shared between lunch and dinner (lower = better)."""
    lunch_el = extract_elements(lunch_text)
    dinner_el = extract_elements(dinner_text)
    return len(lunch_el & dinner_el)


def rank_dinners(
    lunch_text: str,
    dinner_options: list[dict],
    suggested_date: str | None = None,
) -> list[dict]:
    """
    Rank dinner options for a given lunch.
    Each option: {"date": str, "description": str}
    Returns same dicts with added fields: score, conflicts, is_scheduled
    """
    ranked = []
    for opt in dinner_options:
        score = conflict_score(lunch_text, opt["description"])
        conflicts = extract_elements(lunch_text) & extract_elements(opt["description"])
        ranked.append({
            **opt,
            "score": score,
            "conflicts": sorted(conflicts),
            "is_scheduled": opt.get("date") == suggested_date,
        })

    # Sort: scheduled date first (tiebreak), then by score
    ranked.sort(key=lambda x: (x["score"], 0 if x["is_scheduled"] else 1))
    return ranked


import re  # noqa: E402 — needed for extract_elements
