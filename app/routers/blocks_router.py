# routers/blocks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app.models.block import Block
from app.models.profile import Profile
from app.models.connection import Connection
from app.models.media import MediaFile
from app.auth.supabase_auth import get_current_user
from app.core.profile_access import get_current_user_profile


router = APIRouter(prefix="/blocks", tags=["Blocks"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# BLOCK PROFILE
# --------------------------------------------------
@router.post("/{profile_id}")
def block_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]

    my_profile = get_current_user_profile(db, user_id)

    # Cannot block yourself
    if profile_id == my_profile.id:
        raise HTTPException(400, "Cannot block yourself")

    # Target must exist
    target = db.query(Profile).filter(Profile.id == profile_id).first()
    if not target:
        raise HTTPException(404, "Profile not found")

    # Already blocked → no-op
    exists = (
        db.query(Block)
        .filter_by(
            blocker_profile_id=my_profile.id,
            blocked_profile_id=profile_id,
        )
        .first()
    )

    if exists:
        return {"status": "already_blocked"}

    # Create block
    db.add(
        Block(
            blocker_profile_id=my_profile.id,
            blocked_profile_id=profile_id,
        )
    )

    # Sever any existing connections
    existing_connections = (
        db.query(Connection)
        .filter(
            (
                (Connection.from_profile_id == my_profile.id)
                & (Connection.to_profile_id == profile_id)
            )
            | (
                (Connection.from_profile_id == profile_id)
                & (Connection.to_profile_id == my_profile.id)
            )
        )
        .all()
    )

    for conn in existing_connections:
        conn.status = "rejected"
        conn.rejected_at = datetime.utcnow()

    db.commit()

    return {"status": "blocked"}


# --------------------------------------------------
# UNBLOCK PROFILE
# --------------------------------------------------
@router.delete("/{profile_id}")
def unblock_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]

    my_profile = get_current_user_profile(db, user_id)

    block = db.query(Block).filter_by(
        blocker_profile_id=my_profile.id,
        blocked_profile_id=profile_id,
    ).first()

    if not block:
        return {"status": "not_blocked"}

    db.delete(block)
    db.commit()

    return {"status": "unblocked"}


# --------------------------------------------------
# MY BLOCKED PROFILES
# --------------------------------------------------
@router.get("/mine")
def get_my_blocked_profiles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    blocks = (
        db.query(Block)
        .filter(Block.blocker_profile_id == my_profile.id)
        .all()
    )

    results = []

    for b in blocks:
        profile = (
            db.query(Profile)
            .filter(Profile.id == b.blocked_profile_id)
            .first()
        )

        if not profile:
            continue

        media = None
        if profile.profile_picture_media_id:
            media = (
                db.query(MediaFile)
                .filter(MediaFile.id == profile.profile_picture_media_id)
                .first()
            )

        results.append({
            "id": profile.id,
            "full_name": profile.full_name,
            "profile_picture": media.file_path if media else None,
        })

    return results