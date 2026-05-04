import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Use /data for HF Spaces persistent storage; fall back to local for dev
_default_db = "sqlite:////data/menu_planner.db" if os.path.isdir("/data") else "sqlite:///./menu_planner.db"
DB_PATH = os.environ.get("DATABASE_URL", _default_db)
if DB_PATH.startswith("sqlite"):
    engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DB_PATH)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
