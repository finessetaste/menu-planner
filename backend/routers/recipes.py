from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Recipe, Ingredient
from schemas import RecipeOut, RecipePatch, IngredientBase

router = APIRouter()


@router.get("/", response_model=list[RecipeOut])
def list_recipes(
    tipo: str | None = None,
    subtipo: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Recipe)
    if tipo:
        q = q.filter(Recipe.tipo == tipo)
    if subtipo:
        q = q.filter(Recipe.subtipo == subtipo)
    return q.order_by(Recipe.tipo, Recipe.nombre).all()


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    r = db.get(Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    return r


@router.patch("/{recipe_id}", response_model=RecipeOut)
def patch_recipe(recipe_id: int, patch: RecipePatch, db: Session = Depends(get_db)):
    r = db.get(Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    for field, val in patch.model_dump(exclude_none=True).items():
        setattr(r, field, val)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{recipe_id}/ingredients/{ing_id}")
def patch_ingredient(
    recipe_id: int,
    ing_id: int,
    data: IngredientBase,
    db: Session = Depends(get_db),
):
    ing = db.get(Ingredient, ing_id)
    if not ing or ing.recipe_id != recipe_id:
        raise HTTPException(404, "Ingredient not found")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(ing, field, val)
    db.commit()
    return {"ok": True}


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    r = db.get(Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    db.delete(r)
    db.commit()
    return {"ok": True}
