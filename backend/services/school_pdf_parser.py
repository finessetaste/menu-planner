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

MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
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
    re.compile(r"\bFRUTA\b", re.IGNORECASE),
    re.compile(r"\d+\s*[Kk]cal"),
    re.compile(r"\bPAN\b.*\bAGUA\b", re.IGNORECASE),
    re.compile(r"\bY\s+AGUA\b", re.IGNORECASE),
    re.compile(r"\bPAN\s+INTEGRAL\b", re.IGNORECASE),
    re.compile(r"\bYOGUR\b", re.IGNORECASE),
    re.compile(r"\bNATILLAS?\b|\bHELADO\b|\bGELATINA\b|\bFLAN\b|\bMACEDONIA\b", re.IGNORECASE),
    re.compile(r"\bMELOCOTÓN\b|\bCUAJADA\b|\bCOMPOTA\b", re.IGNORECASE),
    re.compile(r"EN\s+TODAS\s+LAS\s+CENAS", re.IGNORECASE),
]

# Skip + eat next orphan line (event headers like "DÍA MUNDIAL DE LA" → "SALUD")
EVENT_SKIP_RES = [
    re.compile(r"D[IÍ]A\s+(MUNDIAL|INTERNACIONAL|NACIONAL|DEL)\b", re.IGNORECASE),  # DÍA or DIA
    re.compile(r"D[IÍ]A\s+NO\s+LECTIVO\b", re.IGNORECASE),
]

# Skip just this line (no orphan-tail effect)
LABEL_SKIP_RES = [
    re.compile(r"VACACIONES\b", re.IGNORECASE),
    re.compile(r"^\s*[\d\s]+$"),                    # digit-only rows
    re.compile(r"^COCINA\s+\w", re.IGNORECASE),     # theme labels: "COCINA ITALIANA"
    re.compile(r"^\s*\("),                           # safety net: lines starting with (
]

# Keep SKIP_RES as alias used by old debug code
SKIP_RES = EVENT_SKIP_RES + LABEL_SKIP_RES

# Regex helpers for description cleanup
_PAREN_RE      = re.compile(r"\([^)]*\)")   # strip (allergen codes) and (ingredient lists)
_STARTS_CONT   = re.compile(
    r"^(CON|DE|Y|A|AL|EN|SIN|CON EL|CON LA"
    r"|[A-ZÁÉÍÓÚÑÜ]+ADAS?"    # feminine past participles: REHOGADAS, GUISADAS, SALTEADAS…
    r")(\s|$)",                # allow single-word lines (no trailing space required)
    re.IGNORECASE,
)
# Note: masculine -ADOS (ASADO, ESTOFADO…) removed — "PESCADO" ends in -ADO causing
# false-positives. Single-word adjectives are handled by the min-words rule below.
_ENDS_PREP     = re.compile(r"\b(AL|CON|DE|EN|A|SIN|Y)\s*$", re.IGNORECASE)

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

        for page_idx, page in enumerate(pdf.pages[:2]):
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

                # Group flat pdfplumber rows into calendar-week blocks.
                # pdfplumber splits merged cells: each text line → separate row.
                # We must merge lines back into full cell text before date calc.
                week_blocks = _group_rows_into_weeks(data_rows, col_map)

                for week_idx, week_cells in enumerate(week_blocks):
                    for col_idx, weekday in col_map.items():
                        cell_text = _normalize_cell(week_cells.get(col_idx, ""))
                        if not cell_text:
                            continue

                        # ── Date from grid position ──────────────────────────
                        grid_date = first_monday + timedelta(days=week_idx * 7 + weekday)
                        if grid_date.month != month:
                            continue  # outside this month

                        # ── Validate with day number if present ──────────────
                        day_num = _extract_day_number(cell_text)
                        if day_num and day_num != grid_date.day:
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
    for name, num in MONTHS_EN.items():
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


def _group_rows_into_weeks(
    data_rows: list[list],
    col_map: dict[int, int],
) -> list[dict[int, str]]:
    """
    pdfplumber splits each calendar cell across multiple table rows
    (one text line per row).  Group them back into one block per calendar week.

    A new week block starts when any day-column cell is a pure 1-2 digit number
    (i.e. the day-number header row of that week).

    Content text may land in sub-columns within each day's column span
    (pdfplumber models merged cells as multiple columns), so we collect
    all values within the range [col_start, next_col_start).

    Returns a list of dicts: {col_idx: joined_cell_text}
    """
    _PURE_NUM = re.compile(r"^\s*\d{1,2}\s*$")

    # Build column-span ranges: LUNES at col 1, MARTES at col 7 → LUNES = cols 1–6
    sorted_cols = sorted(col_map.keys())
    row_width = len(data_rows[0]) if data_rows else 30
    col_spans: dict[int, range] = {}
    for i, ci in enumerate(sorted_cols):
        next_ci = sorted_cols[i + 1] if i + 1 < len(sorted_cols) else row_width
        col_spans[ci] = range(ci, next_ci)

    def _has_day_numbers(row: list) -> bool:
        """True when the day-header col itself holds a pure 1-2 digit number."""
        return any(
            ci < len(row) and row[ci] and _PURE_NUM.match(str(row[ci]).strip())
            for ci in col_map
        )

    def _collect_span(row: list, ci: int) -> str:
        """Concatenate all non-empty values within a day's column span."""
        parts = []
        for sub in col_spans[ci]:
            val = row[sub] if sub < len(row) else None
            if val and str(val).strip():
                parts.append(str(val).strip())
        return " ".join(parts)

    weeks: list[dict[int, list[str]]] = []
    current: dict[int, list[str]] | None = None

    for row in data_rows:
        if _has_day_numbers(row):
            if current is not None:
                weeks.append(current)
            current = {ci: [] for ci in col_map}

        if current is None:
            continue  # skip pre-week header rows

        for ci in col_map:
            text = _collect_span(row, ci)
            if text:
                current[ci].append(text)

    if current is not None:
        weeks.append(current)

    return [{ci: "\n".join(lines) for ci, lines in week.items()} for week in weeks]


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


def _join_multiline_parens(text: str) -> str:
    """
    Join multi-line parenthetical content onto one line so _PAREN_RE can strip it.
    e.g. "(PICADA, ZANAHORIA,\nCEBOLLA, PIMIENTO)" → "(PICADA, ZANAHORIA, CEBOLLA, PIMIENTO)"
    """
    lines = text.splitlines()
    result: list[str] = []
    depth = 0
    for line in lines:
        if depth > 0 and result:
            result[-1] += " " + line.strip()
        else:
            result.append(line)
        depth += line.count("(") - line.count(")")
        if depth < 0:
            depth = 0
    return "\n".join(result)


def _extract_description(text: str) -> str:
    """
    Extract clean meal description:
    - Join multi-line parens first so _PAREN_RE can strip them completely
    - Strip allergen/ingredient parenthetical groups
    - Skip event headers (DÍA MUNDIAL…) + orphan lines; skip theme labels (COCINA ITALIANA)
    - Stop at dessert/fruit/calorie lines
    - Group lines into max 2 courses; force continuation when course < 2 words
    - Join courses with ' & '; apply sentence case
    """
    # Pre-process: join multi-line parens onto one line
    text = _join_multiline_parens(text)

    lines = text.splitlines()
    cleaned: list[str] = []
    skip_next = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Strip parenthetical content (allergen codes, ingredient lists)
        line = _PAREN_RE.sub("", line).strip()
        line = re.sub(r"\s{2,}", " ", line)
        if not line:
            continue

        # Bare day number — skip silently, no orphan-tail effect
        if re.fullmatch(r"\d{1,2}", line):
            continue

        # Skip orphan lines following event-headers
        if skip_next > 0:
            skip_next -= 1
            continue

        # Event headers: skip this line + eat next orphan line
        if any(p.search(line) for p in EVENT_SKIP_RES):
            skip_next = 1
            continue

        # Label lines: skip just this line (no orphan effect)
        if any(p.search(line) for p in LABEL_SKIP_RES):
            continue

        if len(line) < 3:
            continue

        # Stop collecting at fruit/dessert/calorie line
        if any(p.search(line) for p in STOP_RES):
            break

        cleaned.append(line)

    if not cleaned:
        return ""

    # Remove leading day number from first line
    cleaned[0] = re.sub(r"^\d{1,2}\s+", "", cleaned[0]).strip()
    if not cleaned[0]:
        cleaned = cleaned[1:]
    if not cleaned:
        return ""

    # ── Group lines into courses ───────────────────────────────────────────────
    # A line continues the current course when:
    #   • it starts with a continuation word (CON, DE, Y, AL, REHOGADAS…), OR
    #   • the previous line ended with a dangling preposition, OR
    #   • the current course has < 2 words (too short to be a complete dish)
    courses: list[list[str]] = []
    current_course: list[str] = []

    for line in cleaned:
        if current_course:
            current_words = sum(len(l.split()) for l in current_course)
            prev = current_course[-1]
            if (_STARTS_CONT.match(line)
                    or _ENDS_PREP.search(prev)
                    or (len(line.split()) == 1 and current_words < 4)):  # single-word adjective continuation
                current_course.append(line)
            else:
                courses.append(current_course)
                if len(courses) >= 2:
                    break
                current_course = [line]
        else:
            current_course = [line]

    if current_course and len(courses) < 2:
        courses.append(current_course)

    course_texts = [" ".join(parts) for parts in courses]
    result = " & ".join(course_texts).lower().capitalize()
    return result if len(result) > 3 else ""
