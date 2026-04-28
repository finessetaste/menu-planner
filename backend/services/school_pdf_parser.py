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

# Lines that signal END of main dish — stop collecting here
STOP_RES = [
    re.compile(r"\bFRUTA\b", re.IGNORECASE),           # fruit of any kind
    re.compile(r"\d+\s*[Kk]cal"),                      # calorie line
    re.compile(r"\bPAN\b.*\bAGUA\b", re.IGNORECASE),
    re.compile(r"\bY\s+AGUA\b", re.IGNORECASE),
    re.compile(r"\bPAN\s+INTEGRAL\b", re.IGNORECASE),
    re.compile(r"\bYOGUR\b", re.IGNORECASE),
    re.compile(r"\bNATILLAS\b|\bHELADO\b|\bGELATINA\b|\bFLAN\b|\bMACEDONIA\b", re.IGNORECASE),
    re.compile(r"EN\s+TODAS\s+LAS\s+CENAS", re.IGNORECASE),
]

# Lines to SKIP entirely (don't stop, just drop this line)
SKIP_RES = [
    re.compile(r"DÍA\s+(MUNDIAL|INTERNACIONAL|NACIONAL|DEL)\b", re.IGNORECASE),
    re.compile(r"VACACIONES\b", re.IGNORECASE),
    re.compile(r"DÍA\s+NO\s+LECTIVO\b", re.IGNORECASE),
    re.compile(r"^\s*[\d\s]+$"),   # only digits/spaces
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
        # Pre-scan ALL pages to find month/year — handles PDFs where
        # the dinner page has no month header of its own
        all_text = " ".join(p.extract_text() or "" for p in pdf.pages)
        global_yr, global_month = _detect_year_month(all_text, year)

        for page_idx, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            yr, month = _detect_year_month(page_text, year)
            # Fall back to PDF-wide detection if this page has no month
            if not month:
                yr, month = global_yr, global_month
            if not month:
                continue

            meal_type = force_meal_type or _detect_meal_type(page_text, page_idx)
            first_monday = _first_monday_of_grid(yr, month)

            # Try standard table extraction first; fall back to word-grid
            tables = page.extract_tables()
            valid_tables = [t for t in tables if _find_day_columns(t)]
            if not valid_tables:
                # Fallback: reconstruct grid from word bounding boxes
                word_table = _words_to_table(page)
                if word_table:
                    tables = [word_table]
                    valid_tables = [word_table]
                else:
                    continue

            for table in valid_tables:
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


def _words_to_table(page) -> list[list] | None:
    """
    Reconstruct LUNES-VIERNES calendar grid from word bounding boxes.
    Used when extract_tables() finds no valid table (colour-background PDFs).
    Returns a 2-D list compatible with extract_tables() output, or None.
    """
    words = page.extract_words(keep_blank_chars=True, x_tolerance=3, y_tolerance=3)
    if not words:
        return None

    # ── 1. Cluster words into columns by x-midpoint ───────────────────────────
    # Find column centres by looking at the x-midpoints of day-header words first
    day_header_words = [
        w for w in words
        if _norm_cell(w["text"]) in DAY_COLS
    ]

    if len(day_header_words) < 3:
        # Can't identify columns — give up
        return None

    # Sort headers left-to-right; their x-midpoints define column centres
    day_header_words.sort(key=lambda w: w["x0"])
    col_centres = [(w["x0"] + w["x1"]) / 2 for w in day_header_words]

    # Tolerance: half the minimum gap between adjacent centres
    gaps = [col_centres[i+1] - col_centres[i] for i in range(len(col_centres)-1)]
    tol = min(gaps) * 0.45 if gaps else 60

    def _nearest_col(x_mid):
        dists = [abs(x_mid - c) for c in col_centres]
        best = min(dists)
        return dists.index(best) if best <= tol else None

    # ── 2. Cluster words into rows by top (y) coordinate ─────────────────────
    # Group words whose tops are within ROW_TOL of each other
    ROW_TOL = 6  # px — words on same visual line
    words_sorted_y = sorted(words, key=lambda w: w["top"])

    rows_y: list[list[dict]] = []
    for w in words_sorted_y:
        placed = False
        for row in rows_y:
            if abs(w["top"] - row[0]["top"]) <= ROW_TOL:
                row.append(w)
                placed = True
                break
        if not placed:
            rows_y.append([w])

    # ── 3. Build 2-D table: rows × columns ───────────────────────────────────
    n_cols = len(col_centres)
    table: list[list[str | None]] = []

    for row_words in rows_y:
        cells: list[str | None] = [None] * n_cols
        for w in row_words:
            x_mid = (w["x0"] + w["x1"]) / 2
            ci = _nearest_col(x_mid)
            if ci is None:
                continue
            txt = w["text"].strip()
            if not txt:
                continue
            if cells[ci] is None:
                cells[ci] = txt
            else:
                cells[ci] += " " + txt
        table.append(cells)

    if not table:
        return None

    # ── 4. Merge nearby rows into single multi-line cells ────────────────────
    # Calendar cells span multiple text rows; merge rows that belong to the
    # same cell block.  We split on rows where a day-header token appears.
    # Strategy: find which row-indices are "header rows" (contain LUNES etc),
    # then merge runs between headers into one logical row of joined text.
    header_row_indices = set()
    for ri, row in enumerate(table):
        hits = sum(1 for c in row if c and _norm_cell(c) in DAY_COLS)
        if hits >= 3:
            header_row_indices.add(ri)

    if not header_row_indices:
        # No header row found — return flat table anyway (may still work)
        return table if len(table) > 1 else None

    # Find the first header row index
    first_header = min(header_row_indices)

    # Everything after the first header is data; group by visual cell blocks.
    # We separate blocks wherever the leftmost non-None column cell starts with
    # a 1-2 digit number (day number for lunch PDFs) OR by y-gap heuristic.
    # Simpler: merge consecutive data rows into blocks of ~CELL_ROWS each.
    # Use y-gap: find large gaps between row groups.
    data_rows_raw = table[first_header + 1:]

    # Calculate y-top for each raw row (use first word's top in that row — approximate)
    # We'll use index-based merging: collect until a row looks like a new cell start.
    # A new cell starts when ANY non-None cell matches r"^\s*\d{1,2}\b" (day number)
    # or when all non-None cells are DAY_NAMES (shouldn't happen in data).

    merged_data: list[list[str | None]] = []
    current: list[str | None] = [None] * n_cols

    def _is_cell_start(row):
        """True if this row starts a new calendar cell (has a day number in col 0)."""
        non_none = [c for c in row if c]
        if not non_none:
            return False
        first_non_none = non_none[0]
        return bool(re.match(r"^\s*\d{1,2}\b", first_non_none))

    def _merge_into(target, src):
        for i, val in enumerate(src):
            if val:
                if target[i] is None:
                    target[i] = val
                else:
                    target[i] += "\n" + val

    for row in data_rows_raw:
        if _is_cell_start(row) and any(c is not None for c in current):
            merged_data.append(current)
            current = [None] * n_cols
        _merge_into(current, row)

    if any(c is not None for c in current):
        merged_data.append(current)

    # If merging produced nothing useful, fall back to raw data rows
    if not merged_data:
        merged_data = data_rows_raw

    # Return header row + merged data rows
    return [table[first_header]] + merged_data


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
    """
    Keep only the main dish — stop at first fruit/dessert/calorie line.
    Skip event-header lines without stopping.
    """
    lines = text.splitlines()
    cleaned: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip-only lines (event headers etc.)
        if any(p.search(line) for p in SKIP_RES):
            continue
        if re.fullmatch(r"\d{1,2}", line):   # bare day number
            continue
        if len(line) < 3:
            continue

        # Stop collecting at fruit/dessert/calorie
        if any(p.search(line) for p in STOP_RES):
            break

        cleaned.append(line)

    desc = " ".join(cleaned).strip()
    desc = re.sub(r"^\d{1,2}\s+", "", desc).strip()   # remove leading day number
    desc = re.sub(r"\s{2,}", " ", desc)
    return desc if len(desc) > 3 else ""
