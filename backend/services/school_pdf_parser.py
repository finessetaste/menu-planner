"""
School PDF parser — monthly LUNES–VIERNES calendar grid.

Confirmed formats:
  LUNCH  — cells start with day number, have calorie line at bottom
  DINNER — cells have NO day number; dates calculated from grid position

Auto-detects meal type from page text ("cena/cenas" → dinner, else → lunch).
"""
import re
from datetime import date, timedelta
import pdfplumber

# ── Constants ─────────────────────────────────────────────────────────────────

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

DAY_COLS = {
    "LUNES": 0, "MARTES": 1,
    "MIÉRCOLES": 2, "MIERCOLES": 2,
    "JUEVES": 3, "VIERNES": 4,
}

DINNER_KEYWORDS = {"cena", "cenas", "dinner", "merienda-cena"}
LUNCH_KEYWORDS  = {"comida", "comidas", "almuerzo", "lunch", "comedor"}

# Patterns to REMOVE from cell text
STRIP_RES = [
    re.compile(r"\d+\s*[Kk]cal.*"),                          # calorie lines
    re.compile(r"\bFRUTA\s+DE\s+TEMPORADA.*", re.IGNORECASE),
    re.compile(r"^FRUTA$", re.IGNORECASE | re.MULTILINE),    # standalone FRUTA
    re.compile(r"\bPAN\s+INTEGRAL.*", re.IGNORECASE),
    re.compile(r"\bPAN\b.*\bAGUA\b.*", re.IGNORECASE),
    re.compile(r"\bY\s+AGUA\b.*", re.IGNORECASE),
    re.compile(r"EN\s+TODAS\s+LAS\s+CENAS.*", re.IGNORECASE),
    re.compile(r"DÍA\s+(MUNDIAL|INTERNACIONAL|NACIONAL|DEL).*", re.IGNORECASE),
    re.compile(r"VACACIONES.*", re.IGNORECASE),
    re.compile(r"DÍA\s+NO\s+LECTIVO.*", re.IGNORECASE),
    re.compile(r"^\s*[\d\s]+$"),                              # lines of only digits/spaces
]

KCAL_RE    = re.compile(r"\d+\s*[Kk]cal")
DAY_NUM_RE = re.compile(r"^\s*(\d{1,2})\b")


# ── Public API ────────────────────────────────────────────────────────────────

def parse_school_pdf(
    pdf_path: str,
    year: int | None = None,
    force_meal_type: str | None = None,
) -> list[dict]:
    results: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            yr, month = _detect_year_month(page_text, year)
            if not month:
                continue

            meal_type = force_meal_type or _detect_meal_type(page_text, page_idx)
            first_monday = _first_monday_of_grid(yr, month)

            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                col_map = _find_day_columns(table)
                if not col_map:
                    continue

                header_row_idx = _find_header_row_idx(table)
                data_rows = table[header_row_idx + 1:]

                for row_idx, row in enumerate(data_rows):
                    for col_idx, weekday in col_map.items():
                        if col_idx >= len(row):
                            continue
                        cell = row[col_idx]
                        if not cell:
                            continue

                        cell_text = _normalize_cell(cell)

                        # ── Date from grid position ──────────────────────────
                        grid_date = first_monday + timedelta(days=row_idx * 7 + weekday)
                        if grid_date.month != month:
                            continue  # outside this month

                        # ── Validate with day number if present ──────────────
                        day_num = _extract_day_number(cell_text)
                        if day_num and day_num != grid_date.day:
                            # Try to find the matching row where day_num fits
                            # (handles months that don't start on Monday)
                            try:
                                explicit = date(yr, month, day_num)
                                if explicit.weekday() == weekday:
                                    grid_date = explicit
                                else:
                                    continue  # mismatch — skip
                            except ValueError:
                                continue

                        description = _extract_description(cell_text)
                        if description:
                            results.append({
                                "date": grid_date.isoformat(),
                                "meal_type": meal_type,
                                "description": description,
                            })

    # Deduplicate
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for r in results:
        k = (r["date"], r["meal_type"])
        if k not in seen:
            seen.add(k)
            deduped.append(r)

    return sorted(deduped, key=lambda x: x["date"])


# ── Internal helpers ──────────────────────────────────────────────────────────

def _detect_year_month(text: str, override_year: int | None) -> tuple[int, int | None]:
    tl = text.lower()
    yr_m = re.search(r"\b(20\d{2})\b", tl)
    yr = int(yr_m.group(1)) if yr_m else (override_year or date.today().year)
    for name, num in MONTHS_ES.items():
        if name in tl:
            return yr, num
    return yr, None


def _detect_meal_type(text: str, page_idx: int) -> str:
    tl = text.lower()
    if any(kw in tl for kw in DINNER_KEYWORDS):
        return "dinner"
    if any(kw in tl for kw in LUNCH_KEYWORDS):
        return "lunch"
    return "lunch" if page_idx == 0 else "dinner"


def _first_monday_of_grid(yr: int, month: int) -> date:
    """Monday of the week containing the 1st of the month."""
    first = date(yr, month, 1)
    return first - timedelta(days=first.weekday())


def _find_header_row_idx(table: list[list]) -> int:
    for i, row in enumerate(table or []):
        if not row:
            continue
        hits = sum(1 for c in row if _norm_cell(c) in DAY_COLS)
        if hits >= 3:
            return i
    return 0


def _find_day_columns(table: list[list]) -> dict[int, int]:
    for row in (table or []):
        if not row:
            continue
        mapping: dict[int, int] = {}
        for i, cell in enumerate(row):
            n = _norm_cell(cell)
            if n in DAY_COLS:
                mapping[i] = DAY_COLS[n]
        if len(mapping) >= 3:
            return mapping
    return {}


def _norm_cell(cell) -> str:
    if not cell:
        return ""
    s = str(cell).strip().upper()
    # Normalise common accent variants for matching
    return (s.replace("É", "É")   # keep — already in DAY_COLS
             .replace("\n", " "))


def _normalize_cell(cell) -> str:
    """Convert cell to clean multi-line string."""
    if not cell:
        return ""
    # pdfplumber sometimes uses \n literally inside cells
    return str(cell).replace("\\n", "\n").strip()


def _extract_day_number(text: str) -> int | None:
    m = DAY_NUM_RE.match(text.strip())
    if m:
        n = int(m.group(1))
        if 1 <= n <= 31:
            return n
    return None


def _extract_description(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        skip = False
        for pat in STRIP_RES:
            if pat.search(line):
                skip = True
                break
        if skip:
            continue
        if re.fullmatch(r"\d{1,2}", line):   # bare day number
            continue
        if len(line) < 3:
            continue
        cleaned.append(line)

    desc = " ".join(cleaned).strip()
    # Remove any leading day number
    desc = re.sub(r"^\d{1,2}\s+", "", desc).strip()
    desc = re.sub(r"\s{2,}", " ", desc)
    return desc if len(desc) > 3 else ""
