import os
import shutil
import tempfile
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import Recipe, Ingredient
from services.pdf_parser import parse_pdf

router = APIRouter()

PHOTOS_DIR = "/data/photos" if os.path.isdir("/data") else os.path.join(os.path.dirname(__file__), "..", "static", "photos")
_ingest_status: dict = {"state": "idle", "message": "", "count": 0}


@router.get("/status")
def ingest_status():
    return _ingest_status


@router.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos PDF")

    if _ingest_status["state"] == "running":
        raise HTTPException(409, "Ingesta ya en curso")

    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(content)
    tmp.close()

    background_tasks.add_task(_ingest, tmp.name, db)
    return {"message": "Ingesta iniciada"}


def _ingest(pdf_path: str, db: Session):
    global _ingest_status
    _ingest_status = {"state": "running", "message": "Procesando PDF…", "count": 0}
    try:
        # Clear existing recipes
        db.query(Ingredient).delete()
        db.query(Recipe).delete()
        db.commit()

        # Clear old photos
        if os.path.exists(PHOTOS_DIR):
            shutil.rmtree(PHOTOS_DIR)
        os.makedirs(PHOTOS_DIR, exist_ok=True)

        recipes_data = parse_pdf(pdf_path, PHOTOS_DIR)

        for rd in recipes_data:
            r = Recipe(
                nombre=rd["nombre"],
                tipo=rd["tipo"],
                subtipo=rd.get("subtipo"),
                foto=rd.get("foto"),
                page_number=rd.get("page_number"),
            )
            db.add(r)
            db.flush()
            for ing in rd.get("ingredientes", []):
                db.add(
                    Ingredient(
                        recipe_id=r.id,
                        nombre=ing["nombre"],
                        cantidad=ing.get("cantidad"),
                        unidad=ing.get("unidad"),
                    )
                )

        db.commit()

        # Normalise tipos: cena → comida_cena, comida → desayuno
        TIPO_MAP = {"cena": "comida_cena", "comida": "desayuno"}
        for old, new in TIPO_MAP.items():
            for r in db.query(Recipe).filter(Recipe.tipo == old).all():
                r.tipo = new
        db.commit()

        _ingest_status = {
            "state": "done",
            "message": f"{len(recipes_data)} recetas importadas",
            "count": len(recipes_data),
        }
    except Exception as exc:
        db.rollback()
        _ingest_status = {"state": "error", "message": str(exc), "count": 0}
    finally:
        os.unlink(pdf_path)
