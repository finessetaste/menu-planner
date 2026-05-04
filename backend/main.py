import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import engine, Base
from routers import recipes, weekly_plan, shopping, config, pdf_upload, girls_dinners


PHOTOS_DIR = "/data/photos" if os.path.isdir("/data") else "static/photos"
# Create immediately at import time so StaticFiles mount doesn't crash
os.makedirs(PHOTOS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_cena_to_comida_cena()
    yield


def _migrate_cena_to_comida_cena():
    """One-time migration: rename tipo 'cena' → 'comida_cena' for all recipes."""
    from sqlalchemy.orm import Session
    from models import Recipe
    db: Session = next(__import__("database").get_db())
    try:
        updated = db.query(Recipe).filter(Recipe.tipo == "cena").all()
        for r in updated:
            r.tipo = "comida_cena"
        if updated:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


app = FastAPI(title="Menu Planner API", lifespan=lifespan)

app.include_router(recipes.router,     prefix="/api/recipes",     tags=["recipes"])
app.include_router(weekly_plan.router, prefix="/api/weekly-plan", tags=["weekly-plan"])
app.include_router(shopping.router,    prefix="/api/shopping",    tags=["shopping"])
app.include_router(config.router,      prefix="/api/config",      tags=["config"])
app.include_router(pdf_upload.router,    prefix="/api/pdf",           tags=["pdf"])
app.include_router(girls_dinners.router, prefix="/api/girls-dinners", tags=["girls-dinners"])

# Serve recipe photos
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")

# Serve React SPA
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
