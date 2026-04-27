import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import engine, Base
from routers import recipes, weekly_plan, shopping, config, pdf_upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    os.makedirs("static/photos", exist_ok=True)
    yield


app = FastAPI(title="Menu Planner API", lifespan=lifespan)

app.include_router(recipes.router,     prefix="/api/recipes",     tags=["recipes"])
app.include_router(weekly_plan.router, prefix="/api/weekly-plan", tags=["weekly-plan"])
app.include_router(shopping.router,    prefix="/api/shopping",    tags=["shopping"])
app.include_router(config.router,      prefix="/api/config",      tags=["config"])
app.include_router(pdf_upload.router,  prefix="/api/pdf",         tags=["pdf"])

# Serve recipe photos
app.mount("/photos", StaticFiles(directory="static/photos"), name="photos")

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
