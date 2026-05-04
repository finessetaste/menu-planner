from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import WeekDay, MealSlot, AppConfig, Recipe
from schemas import WeekDayOut, WeekDayPatch, MealSlotPatch
import json

router = APIRouter()

MEAL_TYPES = ["desayuno", "comida", "cena", "snack"]

# Which recipe tipos are valid for each slot type
SLOT_COMPATIBLE_TYPES: dict[str, set[str]] = {
    "desayuno": {"desayuno"},
    "comida":   {"comida_cena"},
    "cena":     {"comida_cena"},
    "snack":    {"snack"},
}


def _monday(d: date) -> str:
    return (d - timedelta(days=d.weekday())).isoformat()


def _get_or_create_week(db: Session, week_start: str) -> list[WeekDay]:
    days = db.query(WeekDay).filter(WeekDay.week_start == week_start).all()
    if len(days) == 7:
        return days

    # Create missing days
    existing_indices = {d.day_index for d in days}
    for i in range(7):
        if i not in existing_indices:
            wd = WeekDay(week_start=week_start, day_index=i)
            db.add(wd)
            db.flush()
            for mt in MEAL_TYPES:
                db.add(MealSlot(week_day_id=wd.id, meal_type=mt))
    db.commit()
    return db.query(WeekDay).filter(WeekDay.week_start == week_start).order_by(WeekDay.day_index).all()


def _apply_office_fixed(db: Session, day: WeekDay):
    """Set fixed meal slots from config for office days."""
    cfg_row = db.query(AppConfig).filter(AppConfig.key == "office_fixed").first()
    if not cfg_row:
        return
    cfg = json.loads(cfg_row.value)
    for mt in ["desayuno", "snack"]:
        rid = cfg.get(mt)
        slot = next((s for s in day.meal_slots if s.meal_type == mt), None)
        if slot:
            slot.recipe_id = rid
            slot.is_fixed = True
    db.commit()


def _clear_office_fixed(db: Session, day: WeekDay):
    for slot in day.meal_slots:
        if slot.is_fixed:
            slot.is_fixed = False
    db.commit()


@router.get("/", response_model=list[WeekDayOut])
def get_week(week_start: str | None = None, db: Session = Depends(get_db)):
    ws = week_start or _monday(date.today())
    days = _get_or_create_week(db, ws)
    return sorted(days, key=lambda d: d.day_index)


@router.patch("/{day_id}", response_model=WeekDayOut)
def patch_day(day_id: int, patch: WeekDayPatch, db: Session = Depends(get_db)):
    day = db.get(WeekDay, day_id)
    if not day:
        raise HTTPException(404, "Day not found")

    if patch.day_type is not None:
        day.day_type = patch.day_type
    if patch.is_office_day is not None:
        day.is_office_day = patch.is_office_day
        if patch.is_office_day:
            _apply_office_fixed(db, day)
        else:
            _clear_office_fixed(db, day)

    db.commit()
    db.refresh(day)
    return day


@router.post("/copy-from-previous", response_model=dict)
def copy_from_previous_week(week_start: str | None = None, db: Session = Depends(get_db)):
    """Copy all non-fixed meal slot selections from the previous week into the given week."""
    ws = week_start or _monday(date.today())
    prev_ws = (date.fromisoformat(ws) - timedelta(weeks=1)).isoformat()

    prev_days = db.query(WeekDay).filter(WeekDay.week_start == prev_ws).all()
    if not prev_days:
        raise HTTPException(404, "No hay datos de la semana anterior para copiar")

    current_days = _get_or_create_week(db, ws)
    prev_map = {d.day_index: d for d in prev_days}

    copied = 0
    for day in current_days:
        prev_day = prev_map.get(day.day_index)
        if not prev_day:
            continue
        for slot in day.meal_slots:
            if slot.is_fixed:
                continue
            prev_slot = next(
                (s for s in prev_day.meal_slots if s.meal_type == slot.meal_type), None
            )
            if prev_slot and prev_slot.recipe_id:
                slot.recipe_id = prev_slot.recipe_id
                copied += 1

    db.commit()
    return {"ok": True, "copied": copied}


@router.patch("/slot/{slot_id}", response_model=dict)
def patch_slot(slot_id: int, patch: MealSlotPatch, db: Session = Depends(get_db)):
    slot = db.get(MealSlot, slot_id)
    if not slot:
        raise HTTPException(404, "Slot not found")
    if slot.is_fixed:
        raise HTTPException(400, "Slot fijo — cambia en Ajustes")
    if patch.recipe_id is not None and patch.recipe_id != 0:
        r = db.get(Recipe, patch.recipe_id)
        if not r:
            raise HTTPException(404, "Recipe not found")
        compatible = SLOT_COMPATIBLE_TYPES.get(slot.meal_type, {slot.meal_type})
        if r.tipo not in compatible:
            raise HTTPException(400, f"Receta de tipo '{r.tipo}' no encaja en slot '{slot.meal_type}'")
    slot.recipe_id = patch.recipe_id if patch.recipe_id != 0 else None
    db.commit()
    return {"ok": True}
