from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.profile import Profile
from app.auth.supabase_auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


# -------------------- ME ---------------------

@router.get("/me")
def get_me(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["sub"]
    email = current_user["email"]

    profile = (
        db.query(Profile)
        .filter(Profile.user_id == user_id)
        .first()
    )

    # Auto-create profile if missing
    if not profile:
        profile = Profile(
            user_id=user_id,
            full_name=None,
            bio=None,
            is_public=True,
            subscription_status="free",
            subscription_tier="free",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return {
        "id": user_id,
        "email": email,
        "has_profile": True
    }