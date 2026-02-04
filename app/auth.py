from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import bcrypt

from app.database import get_db
from app.models.user import User


# ============================================================
# JWT CONFIG  (moved constants here - fixes circular import)
# ============================================================

SECRET_KEY = "super-secret-key-change-in-prod"   # <-- update for production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days valid token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ============================================================
# PASSWORD HELPERS
# ============================================================

def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(password_bytes, hashed.encode())


# ============================================================
# REGISTER USER
# ============================================================

def register_user(db: Session, email: str, password: str) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("Email already exists")

    user = User(
        id=str(uuid4()),
        email=email,
        hashed_password=hash_password(password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# LOGIN
# ============================================================

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ============================================================
# TOKEN CREATION
# ============================================================

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ============================================================
# GET CURRENT USER (works even after DB wipe)
# ============================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()

    # IMPORTANT FIX:
    # If DB was wiped, token is invalid → return 401 instead of crashing
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
