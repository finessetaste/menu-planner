from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import WeekDay, MealSlot, Ingredient, ShoppingItem
from schemas import ShoppingItemOut, ShoppingItemCreate, ShoppingItemPatch

router = APIRouter()


def _monday(d: date) -> str:
    return (d - timedelta(days=d.weekday())).isoformat()


def _aggregate(db: Session, week_start: str) -> list[dict]:
    """Aggregate ingredients from all selected recipes in the week."""
    days = db.query(WeekDay).filter(WeekDay.week_start == week_start).all()
    totals: dict[tuple, dict] = {}

    for day in days:
        for slot in day.meal_slots:
            if not slot.recipe_id:
                continue
            ings = db.query(Ingredient).filter(Ingredient.recipe_id == slot.recipe_id).all()
            for ing in ings:
                key = (ing.nombre.lower(), ing.unidad or "")
                if key in totals:
                    if ing.cantidad:
                        totals[key]["cantidad"] = (totals[key]["cantidad"] or 0) + ing.cantidad
                else:
                    totals[key] = {
                        "nombre": ing.nombre,
                        "cantidad": ing.cantidad,
                        "unidad": ing.unidad,
                    }

    return list(totals.values())


router_prefix = "/shopping"


@router.get("/", response_model=list[ShoppingItemOut])
def get_shopping_list(week_start: str | None = None, db: Session = Depends(get_db)):
    ws = week_start or _monday(date.today())
    return (
        db.query(ShoppingItem)
        .filter(ShoppingItem.week_start == ws)
        .order_by(ShoppingItem.is_manual, ShoppingItem.nombre)
        .all()
    )


@router.post("/generate")
def generate_shopping_list(week_start: str | None = None, db: Session = Depends(get_db)):
    ws = week_start or _monday(date.today())

    # Remove auto-generated items for this week (keep manual)
    db.query(ShoppingItem).filter(
        ShoppingItem.week_start == ws,
        ShoppingItem.is_manual == False,
    ).delete()

    agg = _aggregate(db, ws)
    for item in agg:
        db.add(ShoppingItem(week_start=ws, is_manual=False, **item))
    db.commit()
    return {"generated": len(agg)}


@router.post("/", response_model=ShoppingItemOut)
def add_manual_item(
    item: ShoppingItemCreate,
    week_start: str | None = None,
    db: Session = Depends(get_db),
):
    ws = week_start or _monday(date.today())
    si = ShoppingItem(week_start=ws, is_manual=True, **item.model_dump())
    db.add(si)
    db.commit()
    db.refresh(si)
    return si


@router.patch("/{item_id}", response_model=ShoppingItemOut)
def patch_item(item_id: int, patch: ShoppingItemPatch, db: Session = Depends(get_db)):
    si = db.get(ShoppingItem, item_id)
    if not si:
        raise HTTPException(404, "Item not found")
    for field, val in patch.model_dump(exclude_none=True).items():
        setattr(si, field, val)
    db.commit()
    db.refresh(si)
    return si


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    si = db.get(ShoppingItem, item_id)
    if not si:
        raise HTTPException(404, "Item not found")
    db.delete(si)
    db.commit()
    return {"ok": True}


@router.delete("/")
def clear_checked(week_start: str | None = None, db: Session = Depends(get_db)):
    ws = week_start or _monday(date.today())
    db.query(ShoppingItem).filter(
        ShoppingItem.week_start == ws,
        ShoppingItem.is_checked == True,
    ).delete()
    db.commit()
    return {"ok": True}
