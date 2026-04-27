"""
Girls' Dinners — Module 2.
Upload school PDFs, browse parsed meals, get ranked dinner suggestions,
select dinner per girl per day.
"""
import os
import tempfile
from datetime import date, timedelta
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import SchoolMeal, GirlDinnerSelection
from services.school_pdf_parser import parse_school_pdf
from services.dinner_suggester import rank_dinners

router = APIRouter()

# {girl: {meal_type: status}}
_ingest_status: dict[str, dict] = {
    "girl1": {"both": {"state": "idle", "message": "", "count": 0}},
    "girl2": {
        "lunch":  {"state": "idle", "message": "", "count": 0},
        "dinner": {"state": "idle", "message": "", "count": 0},
    },
}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    return _ingest_status


@router.post("/upload")
async def upload_school_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    girl: str = Form(...),           # "girl1" | "girl2"
    meal_type: str = Form("both"),   # "both" | "lunch" | "dinner"
    year: int = Form(None),
    db: Session = Depends(get_db),
):
    if girl not in ("girl1", "girl2"):
        raise HTTPException(400, "girl debe ser 'girl1' o 'girl2'")
    if meal_type not in ("both", "lunch", "dinner"):
        raise HTTPException(400, "meal_type debe ser 'both', 'lunch' o 'dinner'")
    if girl == "girl1" and meal_type != "both":
        raise HTTPException(400, "Girl 1 sube un solo PDF con ambas comidas (meal_type='both')")
    if girl == "girl2" and meal_type == "both":
        raise HTTPException(400, "Girl 2 necesita PDFs separados — usa meal_type='lunch' o 'dinner'")

    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(content)
    tmp.close()

    background_tasks.add_task(_ingest, tmp.name, girl, meal_type, year, db)
    return {"message": f"Ingesta iniciada para {girl} / {meal_type}"}


def _ingest(pdf_path: str, girl: str, meal_type: str, year, db: Session):
    status_key = "both" if meal_type == "both" else meal_type
    _ingest_status[girl][status_key] = {"state": "running", "message": "Procesando…", "count": 0}
    try:
        # Delete existing records for this girl + meal_type
        q = db.query(SchoolMeal).filter(SchoolMeal.girl == girl)
        if meal_type != "both":
            q = q.filter(SchoolMeal.meal_type == meal_type)
        q.delete()
        db.commit()

        meals = parse_school_pdf(pdf_path, year=year)

        # Filter by meal_type if not "both"
        if meal_type != "both":
            meals = [m for m in meals if m["meal_type"] == meal_type]

        for m in meals:
            db.add(SchoolMeal(
                girl=girl,
                date=m["date"],
                meal_type=m["meal_type"],
                description=m["description"],
            ))
        db.commit()

        _ingest_status[girl][status_key] = {
            "state": "done",
            "message": f"{len(meals)} entradas importadas",
            "count": len(meals),
        }
    except Exception as exc:
        db.rollback()
        _ingest_status[girl][status_key] = {"state": "error", "message": str(exc), "count": 0}
    finally:
        os.unlink(pdf_path)


# ── Query meals ───────────────────────────────────────────────────────────────

@router.get("/meals")
def get_meals(
    girl: str | None = None,
    week_start: str | None = None,
    db: Session = Depends(get_db),
):
    ws = week_start or _monday()
    we = _add_days(ws, 6)
    q = db.query(SchoolMeal).filter(
        SchoolMeal.date >= ws,
        SchoolMeal.date <= we,
    )
    if girl:
        q = q.filter(SchoolMeal.girl == girl)
    return q.order_by(SchoolMeal.girl, SchoolMeal.date, SchoolMeal.meal_type).all()


# ── Suggestions ───────────────────────────────────────────────────────────────

@router.get("/suggestions")
def get_suggestions(
    week_start: str | None = None,
    db: Session = Depends(get_db),
):
    """
    For each day in the week and each girl:
    - Return school lunch (for reference)
    - Return school dinner (scheduled)
    - Return ranked dinner alternatives (sorted by no-repeat score)
    """
    ws = week_start or _monday()
    we = _add_days(ws, 6)

    # All meals for the week
    week_meals = (
        db.query(SchoolMeal)
        .filter(SchoolMeal.date >= ws, SchoolMeal.date <= we)
        .all()
    )

    # All dinner options across ALL stored data (for ranking alternatives)
    all_dinners = db.query(SchoolMeal).filter(SchoolMeal.meal_type == "dinner").all()

    result = []
    for day_offset in range(7):
        day = _add_days(ws, day_offset)
        day_entry = {"date": day, "girls": {}}

        for girl in ("girl1", "girl2"):
            lunch = next(
                (m for m in week_meals if m.girl == girl and m.date == day and m.meal_type == "lunch"),
                None,
            )
            dinner = next(
                (m for m in week_meals if m.girl == girl and m.date == day and m.meal_type == "dinner"),
                None,
            )

            # All dinner options for this girl
            girl_dinners = [
                {"date": d.date, "description": d.description}
                for d in all_dinners if d.girl == girl
            ]

            # Rank dinners vs today's lunch
            ranked = []
            if lunch and girl_dinners:
                ranked = rank_dinners(
                    lunch_text=lunch.description,
                    dinner_options=girl_dinners,
                    suggested_date=day,
                )[:5]  # top 5

            # Selected dinner
            selection = (
                db.query(GirlDinnerSelection)
                .filter(GirlDinnerSelection.girl == girl, GirlDinnerSelection.date == day)
                .first()
            )

            day_entry["girls"][girl] = {
                "lunch": lunch.description if lunch else None,
                "scheduled_dinner": dinner.description if dinner else None,
                "ranked_options": ranked,
                "selected": selection.dinner_description if selection else (
                    dinner.description if dinner else None
                ),
            }

        result.append(day_entry)

    return result


# ── Selection ─────────────────────────────────────────────────────────────────

@router.put("/select")
def select_dinner(
    girl: str,
    day: str,
    dinner_description: str,
    db: Session = Depends(get_db),
):
    sel = (
        db.query(GirlDinnerSelection)
        .filter(GirlDinnerSelection.girl == girl, GirlDinnerSelection.date == day)
        .first()
    )
    if sel:
        sel.dinner_description = dinner_description
    else:
        db.add(GirlDinnerSelection(girl=girl, date=day, dinner_description=dinner_description))
    db.commit()
    return {"ok": True}


# ── Config (girl names) ───────────────────────────────────────────────────────

@router.get("/config")
def get_girl_config(db: Session = Depends(get_db)):
    from models import AppConfig
    import json
    row = db.query(AppConfig).filter(AppConfig.key == "girl_names").first()
    if row:
        return json.loads(row.value)
    return {"girl1": "Niña 1", "girl2": "Niña 2"}


@router.put("/config")
def set_girl_config(body: dict, db: Session = Depends(get_db)):
    from models import AppConfig
    import json
    row = db.query(AppConfig).filter(AppConfig.key == "girl_names").first()
    if row:
        row.value = json.dumps(body)
    else:
        db.add(AppConfig(key="girl_names", value=json.dumps(body)))
    db.commit()
    return {"ok": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _monday() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def _add_days(iso: str, n: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=n)).isoformat()
