from database import engine, SessionLocal
from models import Base, User, UserRole
from passlib.context import CryptContext

# Unda meza zote kwenye hifadhidata mpya
Base.metadata.create_all(bind=engine)

# Tunatumia passlib kama mfumo wako wa asili unavyotaka
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = SessionLocal()

existing_admin = db.query(User).filter(User.username == "admin").first()
hashed_pwd = pwd_context.hash("admin123")

if existing_admin:
    existing_admin.hashed_password = hashed_pwd
    db.commit()
    print("Password ya admin imebadilishwa kuwa admin123!")
else:
    new_admin = User(
        username="admin",
        full_name="System Administrator",
        hashed_password=hashed_pwd,
        role=UserRole.ADMIN,
        is_active=True
    )
    db.add(new_admin)
    db.commit()
    print("Akaunti ya Admin imetengenezwa kwa mafanikio!")

db.close()
