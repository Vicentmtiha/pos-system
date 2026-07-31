# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Soma URL ya database kutoka kwenye Environment Variables za Render, kama haipo tumia SQLite ya ndani
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pos.db")

# Ikiwa ni PostgreSQL kutoka Render, mara nyingi inaanza na "postgres://", SQLAlchemy inahitaji "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Badilisha connect_args kulingana na aina ya database unayotumia
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
