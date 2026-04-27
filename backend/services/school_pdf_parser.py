"""
School PDF parser — monthly table format.

Expected table structures:
  A) Calendar grid: rows=weeks, columns=Mon-Fri, each cell has lunch + dinner
  B) Linear: Date | Lunch | Dinner  (one row per day)

Returns list of:
  {"date": "YYYY-MM-DD", "meal_type": "lunch"|"dinner", "description": str}
"""
import re
import pdfplumber
from datetime import date, timedelta

# Spanish month names → month number
MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

DATE_RE = re.compile(
    r"\b(\d{1,2})[/\-\.](\d{1,2})(?:[/\-\.](\d{2,4}))?\b"
)

DAY_NUMBER_RE = re.compile(r"^\s*(\d{1,2})\s*$")


def parse_school_pdf(pdf_path: str, year: int | None = None) -> list[dict]:
    """Parse school PDF and return structured meal list."""
    results: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        detected_year = year or _detect_year(pdf)

        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    parsed = _parse_table(table, detected_year)
                    results.extend(parsed)
            else:
                # Fall back to text parsing
                text = page.extract_text() or ""
                parsed = _parse_text_fallback(text, detected_year)
                results.extend(parsed)

    # Deduplicate by (date, meal_type)
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for r in results:
        key = (r["date"], r["meal_type"])
        if key not in seen and r["description"].strip():
            seen.add(key)
            deduped.append(r)

    return sorted(deduped, key=lambda x: (x["date"], x["meal_type"]))


# ── Year detection ─────────────────────────────────────────────────────────────

def _detect_year(pdf) -> int:
    for page in pdf.pages:
        text = (page.extract_text() or "").lower()
        m = re.search(r"\b(20\d{2})\b", text)
        if m:
            return int(m.group(1))
    return date.today().year


# ── Table parser ───────────────────────────────────────────────────────────────

def _parse_table(table: list[list], year: int) -> list[dict]:
    """
    Try two layouts:
    1. Linear: first column has dates, remaining columns have lunch / dinner
    2. Calendar grid: header row has day numbers or day names, body rows alternate lunch/dinner
    """
    if not table or len(table) < 2:
        return []

    results = _try_linear(table, year)
    if results:
        return results

    results = _try_calendar_grid(table, year)
    return results


def _clean(cell) -> str:
    if not cell:
        return ""
    return " ".join(str(cell).split()).strip()


def _try_linear(table: list[list], year: int) -> list[dict]:
    """Layout: each row = one day. Columns contain date, lunch, dinner."""
    results: list[dict] = []

    # Find columns that look like dates and meal descriptions
    for row in table:
        if not row:
            continue
        cells = [_clean(c) for c in row]

        # Look for a date in any cell
        row_date = None
        for cell in cells:
            row_date = _extract_date(cell, year)
            if row_date:
                break

        if not row_date:
            continue

        # Remaining non-empty cells: first = lunch, second = dinner
        meal_cells = [c for c in cells if c and not _extract_date(c, year)]
        if len(meal_cells) >= 1:
            results.append({"date": row_date, "meal_type": "lunch", "description": meal_cells[0]})
        if len(meal_cells) >= 2:
            results.append({"date": row_date, "meal_type": "dinner", "description": meal_cells[1]})

    return results


def _try_calendar_grid(table: list[list], year: int) -> list[dict]:
    """
    Layout: calendar grid.
    Header row has day-of-month numbers (1-31) or day names.
    Subsequent rows alternate: week 1 lunch, week 1 dinner, week 2 lunch, ...
    OR each cell contains lunch + dinner separated by newline.
    """
    results: list[dict] = []
    if not table:
        return results

    header = [_clean(c) for c in table[0]]

    # Find month/year context from surrounding text (best effort)
    # Build date mapping: column_index → date
    col_dates: dict[int, str] = {}

    # Try to detect if header has day numbers
    day_numbers: list[int] = []
    for i, h in enumerate(header):
        m = DAY_NUMBER_RE.match(h)
        if m:
            day_numbers.append((i, int(m.group(1))))

    if day_numbers:
        # Need month — scan all cells for month name
        month, yr = _detect_month_year(table, year)
        if month:
            for col_idx, day_num in day_numbers:
                try:
                    d = date(yr, month, day_num)
                    col_dates[col_idx] = d.isoformat()
                except ValueError:
                    pass

    # Now parse body rows
    # Detect if rows alternate lunch/dinner or each cell has both
    body = table[1:]
    meal_row_pattern = _detect_row_pattern(body, header)

    if col_dates and meal_row_pattern == "alternating":
        meal_seq = ["lunch", "dinner"]
        meal_idx = 0
        for row in body:
            cells = [_clean(c) for c in row]
            mt = meal_seq[meal_idx % 2]
            for col_idx, iso_date in col_dates.items():
                if col_idx < len(cells) and cells[col_idx]:
                    results.append({"date": iso_date, "meal_type": mt, "description": cells[col_idx]})
            meal_idx += 1

    elif col_dates and meal_row_pattern == "combined":
        for row in body:
            cells = [_clean(c) for c in row]
            for col_idx, iso_date in col_dates.items():
                if col_idx < len(cells) and cells[col_idx]:
                    text = cells[col_idx]
                    lines = [l.strip() for l in re.split(r"[\n/|]", text) if l.strip()]
                    if len(lines) >= 2:
                        results.append({"date": iso_date, "meal_type": "lunch", "description": lines[0]})
                        results.append({"date": iso_date, "meal_type": "dinner", "description": lines[1]})
                    elif lines:
                        results.append({"date": iso_date, "meal_type": "lunch", "description": lines[0]})

    return results


def _detect_row_pattern(body: list[list], header: list) -> str:
    """Detect if body rows alternate lunch/dinner or each cell has both."""
    lunch_kw = {"comida", "almuerzo", "lunch", "mediodía"}
    dinner_kw = {"cena", "dinner", "noche"}
    for row in body:
        cells = [_clean(c).lower() for c in row if c]
        for c in cells:
            if any(kw in c for kw in lunch_kw) or any(kw in c for kw in dinner_kw):
                return "alternating"
    return "combined"


def _detect_month_year(table: list[list], default_year: int) -> tuple[int | None, int]:
    all_text = " ".join(
        _clean(c).lower()
        for row in table for c in (row or []) if c
    )
    yr_match = re.search(r"\b(20\d{2})\b", all_text)
    yr = int(yr_match.group(1)) if yr_match else default_year
    for name, num in MONTHS_ES.items():
        if name in all_text:
            return num, yr
    return None, yr


# ── Date extraction ────────────────────────────────────────────────────────────

def _extract_date(text: str, year: int) -> str | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    yr = int(m.group(3)) if m.group(3) else year
    if yr < 100:
        yr += 2000
    try:
        return date(yr, mo, d).isoformat()
    except ValueError:
        try:
            return date(yr, d, mo).isoformat()  # swap day/month
        except ValueError:
            return None


# ── Text fallback ──────────────────────────────────────────────────────────────

def _parse_text_fallback(text: str, year: int) -> list[dict]:
    """Last resort: scan text for date + meal description pairs."""
    results: list[dict] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    current_date: str | None = None

    for line in lines:
        d = _extract_date(line, year)
        if d:
            current_date = d
            continue
        if current_date:
            ll = line.lower()
            if any(kw in ll for kw in ("comida", "almuerzo", "lunch")):
                results.append({"date": current_date, "meal_type": "lunch", "description": line})
            elif any(kw in ll for kw in ("cena", "dinner")):
                results.append({"date": current_date, "meal_type": "dinner", "description": line})

    return results
