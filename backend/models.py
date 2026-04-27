from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    tipo = Column(String, nullable=False)   # desayuno | comida | cena | snack
    subtipo = Column(String, nullable=True)
    foto = Column(String, nullable=True)    # filename in static/photos/
    page_number = Column(Integer, nullable=True)

    ingredientes = relationship(
        "Ingredient", back_populates="receta", cascade="all, delete-orphan"
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    nombre = Column(String, nullable=False)
    cantidad = Column(Float, nullable=True)
    unidad = Column(String, nullable=True)

    receta = relationship("Recipe", back_populates="ingredientes")


class WeekDay(Base):
    __tablename__ = "week_days"

    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(String, nullable=False)  # YYYY-MM-DD (Monday)
    day_index = Column(Integer, nullable=False)   # 0=Mon … 6=Sun
    day_type = Column(String, nullable=False, default="normal_training")
    is_office_day = Column(Boolean, default=False)

    meal_slots = relationship(
        "MealSlot", back_populates="week_day", cascade="all, delete-orphan"
    )


class MealSlot(Base):
    __tablename__ = "meal_slots"

    id = Column(Integer, primary_key=True, index=True)
    week_day_id = Column(Integer, ForeignKey("week_days.id"), nullable=False)
    meal_type = Column(String, nullable=False)  # desayuno | comida | cena | snack
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    is_fixed = Column(Boolean, default=False)

    week_day = relationship("WeekDay", back_populates="meal_slots")
    recipe = relationship("Recipe")


class AppConfig(Base):
    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=False)  # JSON string


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(String, nullable=False)
    nombre = Column(String, nullable=False)
    cantidad = Column(Float, nullable=True)
    unidad = Column(String, nullable=True)
    is_checked = Column(Boolean, default=False)
    is_manual = Column(Boolean, default=False)


# ── Module 2 ──────────────────────────────────────────────────────────────────

class SchoolMeal(Base):
    __tablename__ = "school_meals"

    id = Column(Integer, primary_key=True, index=True)
    girl = Column(String, nullable=False)       # "girl1" | "girl2"
    date = Column(String, nullable=False)       # YYYY-MM-DD
    meal_type = Column(String, nullable=False)  # "lunch" | "dinner"
    description = Column(String, nullable=False)


class GirlDinnerSelection(Base):
    __tablename__ = "girl_dinner_selections"

    id = Column(Integer, primary_key=True, index=True)
    girl = Column(String, nullable=False)
    date = Column(String, nullable=False)
    dinner_description = Column(String, nullable=True)
