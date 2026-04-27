from pydantic import BaseModel
from typing import Optional


# ── Ingredients ──────────────────────────────────────────────────────────────

class IngredientBase(BaseModel):
    nombre: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None


class IngredientOut(IngredientBase):
    id: int
    recipe_id: int

    model_config = {"from_attributes": True}


# ── Recipes ───────────────────────────────────────────────────────────────────

class RecipeBase(BaseModel):
    nombre: str
    tipo: str
    subtipo: Optional[str] = None
    foto: Optional[str] = None
    page_number: Optional[int] = None


class RecipeOut(RecipeBase):
    id: int
    ingredientes: list[IngredientOut] = []

    model_config = {"from_attributes": True}


class RecipePatch(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    subtipo: Optional[str] = None


# ── Weekly Plan ───────────────────────────────────────────────────────────────

class MealSlotOut(BaseModel):
    id: int
    meal_type: str
    recipe_id: Optional[int] = None
    is_fixed: bool = False
    recipe: Optional[RecipeOut] = None

    model_config = {"from_attributes": True}


class WeekDayOut(BaseModel):
    id: int
    week_start: str
    day_index: int
    day_type: str
    is_office_day: bool
    meal_slots: list[MealSlotOut] = []

    model_config = {"from_attributes": True}


class WeekDayPatch(BaseModel):
    day_type: Optional[str] = None
    is_office_day: Optional[bool] = None


class MealSlotPatch(BaseModel):
    recipe_id: Optional[int] = None


# ── Shopping ──────────────────────────────────────────────────────────────────

class ShoppingItemOut(BaseModel):
    id: int
    week_start: str
    nombre: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    is_checked: bool
    is_manual: bool

    model_config = {"from_attributes": True}


class ShoppingItemCreate(BaseModel):
    nombre: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None


class ShoppingItemPatch(BaseModel):
    is_checked: Optional[bool] = None
    nombre: Optional[str] = None
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
