from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.models.user import User
from uuid import uuid4

from app.database import get_db

# Import functions directly — these do NOT import auth_router anymore
from app.auth import (
    register_user,
    authenticate_user,
    create_access_token,
    get_current_user,
)

from app.models.profile import Profile


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------- Pydantic request models ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ChangeEmailRequest(BaseModel):
    email: EmailStr

class ChangePasswordRequest(BaseModel):
    password: str

# ----------------- REGISTER ------------------

@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long",
        )
    try:
        user = register_user(db, email=payload.email, password=payload.password)

        # Auto-create profile
        profile = (
            db.query(Profile)
            .filter(Profile.user_id == user.id)
            .first()
        )

        if profile is None:
            profile = Profile(
                id=str(uuid4()),
                user_id=user.id,
                full_name=None,
                bio=None,
                is_public=True,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)

        return {
            "message": "Registration successful",
            "user_id": user.id,
            "profile_id": profile.id,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------- LOGIN -------------------

@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, email=payload.email, password=payload.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": user.id})

    return {
        "access_token": token,
        "token_type": "bearer",
    }
# --------------------Change email---------------------

@router.post("/change-email")
def change_email(
    payload: ChangeEmailRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )

    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Email already in use",
        )

    current_user.email = payload.email
    db.commit()
    db.refresh(current_user)

    return {"message": "Email updated"}

# --------------------Change Password---------------------
@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 🔒 VALIDATION FIRST
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long"
        )

    from app.auth import hash_password

    current_user.hashed_password = hash_password(payload.password)
    db.commit()

    return {"message": "Password updated"}# -------------------- ME ---------------------

@router.get("/me")
def get_me(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = (
        db.query(Profile)
        .filter(Profile.user_id == current_user.id)
        .first()
    )

    return {
        "id": current_user.id,
        "email": current_user.email,
        "has_profile": profile is not None
    }
