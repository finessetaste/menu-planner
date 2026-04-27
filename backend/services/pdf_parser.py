"""
Nutritionist PDF parser.
Uses pdfplumber for text + PyMuPDF for image extraction.
"""
import re
import io
import os
import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
from typing import Optional

# ── Section / subsection maps ─────────────────────────────────────────────────

MEAL_SECTIONS: dict[str, str] = {
    "DESAYUNOS": "desayuno",
    "DESAYUNO": "desayuno",
    "COMIDAS": "comida",
    "COMIDA": "comida",
    "CENAS": "cena",
    "CENA": "cena",
    "SNACKS": "snack",
    "SNACK": "snack",
    "MERIENDA": "snack",
    "MERIENDAS": "snack",
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

PREP_KEYWORDS = (
    "mezclar", "cocinar", "hervir", "cortar", "añadir", "batir",
    "calentar", "poner", "dejar", "remover", "servir", "preparar",
    "escurrir", "triturar", "machacar", "saltear", "hornear",
    "incorporar", "verter", "dejar reposar", "enfriar",
)

UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(g|gr|gramos?|ml|l|litros?|kg|kilogramos?|"
    r"unidades?|u\.?|cucharadas?|cdas?\.?|"
    r"piezas?|pza?\.?|latas?|sobres?|paquetes?)",
    re.IGNORECASE,
)

MIN_IMAGE_DIM = 150  # pixels — smaller images are decorative


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str, photos_dir: str) -> list[dict]:
    """Return list of recipe dicts parsed from nutritionist PDF."""
    os.makedirs(photos_dir, exist_ok=True)
    page_images = _extract_images(pdf_path, photos_dir)
    recipes = _parse_text(pdf_path)
    _associate_images(recipes, page_images)
    return recipes


# ── Text parsing ──────────────────────────────────────────────────────────────

def _parse_text(pdf_path: str) -> list[dict]:
    recipes: list[dict] = []
    current_section: Optional[str] = None
    current_subsection: Optional[str] = None
    current_recipe: Optional[dict] = None
    skip_mode = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            for line in lines:
                lu = line.upper().strip()

                # ── Skip sections ────────────────────────────────────────────
                if any(skip in lu for skip in SKIP_SECTIONS):
                    skip_mode = True
                    if current_recipe:
                        recipes.append(current_recipe)
                        current_recipe = None
                    continue

                # ── Main meal section headers ────────────────────────────────
                new_section = _match_section(lu)
                if new_section:
                    skip_mode = False
                    if current_recipe:
                        recipes.append(current_recipe)
                        current_recipe = None
                    current_section = new_section
                    current_subsection = None
                    continue

                if skip_mode or current_section is None:
                    continue

                # ── Subsection headers ───────────────────────────────────────
                clean = re.sub(r"[^A-ZÁÉÍÓÚÑ\s]", "", lu).strip()
                if clean in KNOWN_SUBTIPOS and len(line) < 30:
                    if current_recipe:
                        recipes.append(current_recipe)
                        current_recipe = None
                    current_subsection = line.strip().capitalize()
                    continue

                # ── Ingredient lines ─────────────────────────────────────────
                if _is_ingredient(line):
                    if current_recipe:
                        ing = _parse_ingredient(line)
                        if ing:
                            current_recipe["ingredientes"].append(ing)
                    continue

                # ── Recipe title ─────────────────────────────────────────────
                if _is_title(line):
                    if current_recipe:
                        recipes.append(current_recipe)
                    current_recipe = {
                        "nombre": line.strip(),
                        "tipo": current_section,
                        "subtipo": current_subsection.lower() if current_subsection else None,
                        "ingredientes": [],
                        "foto": None,
                        "page_number": page_num,
                    }

    if current_recipe:
        recipes.append(current_recipe)

    return recipes


def _match_section(lu: str) -> Optional[str]:
    for key, val in MEAL_SECTIONS.items():
        if lu == key or lu.startswith(key + " "):
            return val
    return None


def _is_ingredient(line: str) -> bool:
    return bool(UNIT_RE.search(line))


def _is_title(line: str) -> bool:
    if len(line) < 3 or len(line) > 80:
        return False
    if not any(c.isalpha() for c in line):
        return False
    if line.replace(".", "").replace(",", "").isdigit():
        return False
    ll = line.lower()
    if any(ll.startswith(kw) for kw in PREP_KEYWORDS):
        return False
    return True


def _parse_ingredient(line: str) -> Optional[dict]:
    match = UNIT_RE.search(line)
    if not match:
        return None

    cantidad = float(match.group(1).replace(",", "."))
    unidad = _norm_unit(match.group(2))

    before = line[: match.start()].strip()
    after = line[match.end() :].strip()
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


# ── Image extraction ──────────────────────────────────────────────────────────

def _extract_images(pdf_path: str, photos_dir: str) -> dict[int, list[str]]:
    """Return {page_num: [filename, ...]} for all recipe-sized images."""
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
                fpath = os.path.join(photos_dir, fname)
                with open(fpath, "wb") as f:
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
