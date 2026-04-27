"""
Nutritionist PDF parser — Canva-style layout.

Each recipe follows this structure:
  WORD                   ← first line of title (ALL CAPS)
  REST OF TITLE          ← second line of title (ALL CAPS)
  1 RACIÓN  12-15 MINUTOS  ← metadata to skip
  INGREDIENTES           ← header to skip
  • 70g Arroz blanco
  • Especias al gusto    ← no quantity — still an ingredient
  PREPARACIÓN            ← marks end of ingredient list; skip everything after
"""
import re
import io
import os
import fitz
import pdfplumber
from PIL import Image
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

MEAL_SECTIONS: dict[str, str] = {
    "DESAYUNOS": "desayuno", "DESAYUNO": "desayuno",
    "COMIDAS": "comida",     "COMIDA": "comida",
    "CENAS": "cena",         "CENA": "cena",
    "SNACKS": "snack",       "SNACK": "snack",
    "MERIENDA": "snack",     "MERIENDAS": "snack",
}

SKIP_SECTIONS: set[str] = {
    "INTERCAMBIOS", "INTERCAMBIO",
    "GUARNICIONES", "GUARNICION", "GUARNICIÓN",
}

KNOWN_SUBTIPOS: set[str] = {
    "AVENA", "PAN", "ARROZ", "PASTA", "PATATA", "PATATAS",
    "LEGUMBRES", "FRUTA", "FRUTAS", "TORTITAS", "TOSTADAS",
    "CEREALES", "QUINOA", "MIJO", "BONIATO", "COPOS",
}

# Headers that appear inside a recipe layout but are NOT titles
RECIPE_HEADERS: set[str] = {"INGREDIENTES", "INGREDIENTES:"}

# Lines that mark start of preparation instructions — skip until next title
PREP_HEADERS: set[str] = {
    "PREPARACIÓN", "PREPARACION", "ELABORACIÓN", "ELABORACION",
    "PREPARACIÓN:", "PREPARACION:",
}

# Matches time / portion metadata lines like "1 RACIÓN", "12-15 MINUTOS"
METADATA_RE = re.compile(
    r"^\d[\d\-]*\s*(MINUTOS?|HORAS?|MIN\.?|RACIONES?|RACIÓN|RACION|PORCIONES?|PORCIÓN)",
    re.IGNORECASE,
)

UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(g|gr|gramos?|ml|l|litros?|kg|kilogramos?|"
    r"unidades?|u\.?|cucharadas?|cdas?\.?|"
    r"piezas?|pza?\.?|latas?|sobres?|paquetes?)",
    re.IGNORECASE,
)

MIN_IMAGE_DIM = 150


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str, photos_dir: str) -> list[dict]:
    os.makedirs(photos_dir, exist_ok=True)
    page_images = _extract_images(pdf_path, photos_dir)
    recipes = _parse_text(pdf_path)
    _associate_images(recipes, page_images)
    return recipes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _caps_ratio(s: str) -> float:
    alpha = [c for c in s if c.isalpha()]
    if not alpha:
        return 0.0
    return sum(1 for c in alpha if c.isupper()) / len(alpha)


def _match_section(lu: str) -> Optional[str]:
    for key, val in MEAL_SECTIONS.items():
        if lu == key or lu.startswith(key + " "):
            return val
    return None


def _is_subsection_line(lu: str, line: str, current_sub: Optional[str]) -> bool:
    """True only if this is a NEW subsection (different from current_sub)."""
    clean = re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", lu).strip()
    if clean not in KNOWN_SUBTIPOS:
        return False
    if len(line) >= 25:
        return False
    current_clean = re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", (current_sub or "").upper()).strip()
    return clean != current_clean  # only a NEW subsection


def _is_ingredient_line(line: str) -> bool:
    return bool(UNIT_RE.search(line))


def _parse_ingredient(line: str) -> Optional[dict]:
    match = UNIT_RE.search(line)
    if not match:
        return None
    cantidad = float(match.group(1).replace(",", "."))
    unidad = _norm_unit(match.group(2))
    before = line[: match.start()].strip()
    after = line[match.end():].strip()
    nombre = before if before else after
    nombre = re.sub(r"^[-:•·\s]+|[-:•·\s]+$", "", nombre).strip().lower()
    if not nombre:
        return None
    return {"nombre": nombre, "cantidad": cantidad, "unidad": unidad}


def _norm_unit(raw: str) -> str:
    raw = raw.lower().rstrip(".")
    return {
        "gr": "g", "gramo": "g", "gramos": "g",
        "mililitro": "ml", "mililitros": "ml",
        "litro": "l", "litros": "l",
        "kilogramo": "kg", "kilogramos": "kg",
        "unidades": "unidad", "u": "unidad",
        "cucharadas": "cucharada", "cdas": "cucharada", "cda": "cucharada",
        "piezas": "pieza", "pza": "pieza", "pz": "pieza",
        "latas": "lata", "sobres": "sobre", "paquetes": "paquete",
    }.get(raw, raw)


# ── Text parser ───────────────────────────────────────────────────────────────

def _parse_text(pdf_path: str) -> list[dict]:
    """
    State machine:
      SCAN        — looking for titles / sections
      INGREDIENTS — inside ingredient list
      PREP        — inside preparation steps (skip until next ALL-CAPS title)
    """
    recipes: list[dict] = []
    current_section: Optional[str] = None
    current_subsection: Optional[str] = None
    current_recipe: Optional[dict] = None
    title_parts: list[str] = []
    skip_mode = False
    state = "SCAN"  # SCAN | INGREDIENTS | PREP

    def _finalize_title():
        if title_parts and current_recipe is not None:
            current_recipe["nombre"] = " ".join(title_parts).strip()
            title_parts.clear()

    def _save_recipe():
        nonlocal current_recipe
        _finalize_title()
        if current_recipe and current_recipe.get("nombre"):
            recipes.append(current_recipe)
        current_recipe = None

    def _new_recipe(page_num: int):
        nonlocal current_recipe, state
        _save_recipe()
        current_recipe = {
            "nombre": "",
            "tipo": current_section,
            "subtipo": current_subsection.lower() if current_subsection else None,
            "ingredientes": [],
            "foto": None,
            "page_number": page_num,
        }
        state = "SCAN"

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            # Strip bullet / dash prefixes
            lines = [re.sub(r"^[•·\-–—]\s*", "", ln) for ln in lines]

            for line in lines:
                lu = line.upper().strip()
                if not lu:
                    continue

                # ── Global: skip sections ────────────────────────────────────
                if any(sk in lu for sk in SKIP_SECTIONS):
                    skip_mode = True
                    _save_recipe()
                    state = "SCAN"
                    title_parts.clear()
                    continue

                # ── Global: main meal section ────────────────────────────────
                new_sec = _match_section(lu)
                if new_sec:
                    skip_mode = False
                    _save_recipe()
                    current_section = new_sec
                    current_subsection = None
                    state = "SCAN"
                    title_parts.clear()
                    continue

                if skip_mode or current_section is None:
                    continue

                # ── Global: PREPARACIÓN → enter PREP state ───────────────────
                if lu in PREP_HEADERS:
                    _finalize_title()
                    state = "PREP"
                    continue

                # ── PREP state: skip until new ALL-CAPS block ────────────────
                if state == "PREP":
                    if _caps_ratio(line) >= 0.8 and lu not in RECIPE_HEADERS and not METADATA_RE.search(lu):
                        # Could be new subsection or new recipe title
                        if _is_subsection_line(lu, line, current_subsection):
                            _save_recipe()
                            clean = re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", lu).strip()
                            current_subsection = clean.capitalize()
                            title_parts.clear()
                        else:
                            _new_recipe(page_num)
                            title_parts.append(line.strip())
                    continue

                # ── Global: recipe utility headers ───────────────────────────
                if lu in RECIPE_HEADERS:
                    _finalize_title()
                    state = "INGREDIENTS"
                    continue

                # ── Skip metadata lines (1 RACIÓN, 12-15 MINUTOS etc.) ───────
                if METADATA_RE.search(lu):
                    continue

                # ── Subsection header ────────────────────────────────────────
                if _is_subsection_line(lu, line, current_subsection) and not title_parts:
                    _save_recipe()
                    clean = re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", lu).strip()
                    current_subsection = clean.capitalize()
                    state = "SCAN"
                    continue

                # ── Ingredient with quantity ─────────────────────────────────
                if _is_ingredient_line(line):
                    if title_parts:
                        _finalize_title()
                        state = "INGREDIENTS"
                    if current_recipe:
                        ing = _parse_ingredient(line)
                        if ing:
                            current_recipe["ingredientes"].append(ing)
                    continue

                # ── INGREDIENTS state: handle no-quantity ingredients ─────────
                if state == "INGREDIENTS" and current_recipe:
                    if _caps_ratio(line) < 0.5 and len(line) > 2:
                        current_recipe["ingredientes"].append({
                            "nombre": line.strip().lower(),
                            "cantidad": None,
                            "unidad": None,
                        })
                    continue

                # ── ALL-CAPS line → recipe title (possibly multi-line) ────────
                if _caps_ratio(line) >= 0.8:
                    if title_parts:
                        # Continue buffering (second line of title)
                        title_parts.append(line.strip())
                    else:
                        # Start new recipe
                        _new_recipe(page_num)
                        title_parts.append(line.strip())

    _save_recipe()
    return [r for r in recipes if r.get("nombre")]


# ── Image extraction ──────────────────────────────────────────────────────────

def _extract_images(pdf_path: str, photos_dir: str) -> dict[int, list[str]]:
    page_images: dict[int, list[str]] = {}
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        saved: list[str] = []
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                pil = Image.open(io.BytesIO(base["image"]))
                w, h = pil.size
                if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
                    continue
                fname = f"p{page_num}_i{img_index + 1}.{base['ext']}"
                with open(os.path.join(photos_dir, fname), "wb") as f:
                    f.write(base["image"])
                saved.append(fname)
            except Exception:
                continue
        if saved:
            page_images[page_num] = saved
    doc.close()
    return page_images


def _associate_images(recipes: list[dict], page_images: dict[int, list[str]]) -> None:
    used: set[str] = set()
    for recipe in recipes:
        rp = recipe.get("page_number", 0)
        for offset in (0, 1, -1, 2, -2):
            tp = rp + offset
            if tp not in page_images:
                continue
            for fname in page_images[tp]:
                if fname not in used:
                    recipe["foto"] = fname
                    used.add(fname)
                    break
            if recipe["foto"]:
                break
