import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import AppConfig

router = APIRouter()

DEFAULT_CONFIG = {
    "calorie_targets": {
        "intense_training": 2500,
        "normal_training": 2250,
        "rest": 2000,
    },
    "calorie_breakdown": {
        "desayuno": 0.25,
        "comida": 0.35,
        "cena": 0.30,
        "snack": 0.10,
    },
    "office_fixed": {
        "desayuno": None,
        "snack": None,
    },
}


def _get_or_default(db: Session, key: str):
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row:
        return json.loads(row.value)
    return DEFAULT_CONFIG.get(key, {})


def _set(db: Session, key: str, value):
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row:
        row.value = json.dumps(value)
    else:
        db.add(AppConfig(key=key, value=json.dumps(value)))
    db.commit()


@router.get("/")
def get_config(db: Session = Depends(get_db)):
    return {k: _get_or_default(db, k) for k in DEFAULT_CONFIG}


@router.put("/")
def update_config(body: dict, db: Session = Depends(get_db)):
    for key, val in body.items():
        if key in DEFAULT_CONFIG:
            _set(db, key, val)
    return {"ok": True}
