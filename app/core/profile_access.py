from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.profile import Profile


def get_current_user_profile(db: Session, user_id: str) -> Profile:
    """
    Simple helper for now: assumes 1 profile per user.
    Later we'll replace with 'active profile'.
    """
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="User has no profile")
    return profile