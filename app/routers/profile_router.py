import os
import uuid
import shutil
from datetime import datetime

from pydantic import BaseModel, EmailStr
from typing import Optional
from app.core.profile_visibility import can_view_profile
from app.schemas.profile_schema import ProfileOut, ProfileOutLimited
from typing import List
from app.schemas.profile_search_schema import ProfileSearchOut
from app.utils.urls import absolute_media_url
from app.core.blocking import is_blocked
from app.models.connection import Connection



from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.supabase_auth import get_current_user

from app.models.profile import Profile
from app.models.media import MediaFile

from app.schemas.profile_schema import (
    ProfileCreate,
    ProfileUpdate,
    ProfileOut
)

from app.storage import save_voice_file,save_file, delete_file,get_file_size


router = APIRouter(prefix="/profile", tags=["Profiles"])

def get_user_id(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["sub"])

def serialize_profile(profile: Profile, db: Session):
    urls = attach_media_urls(db, profile)

    return ProfileOut(
        id=str(profile.id),
        user_id=str(profile.user_id),
        full_name=profile.full_name,
        bio=profile.bio,
        long_biography=profile.long_biography,
        is_public=profile.is_public,
        date_of_birth=profile.date_of_birth,
        is_deceased=profile.is_deceased,
        date_of_death=profile.date_of_death,
        next_of_kin_name=profile.next_of_kin_name,
        next_of_kin_email=profile.next_of_kin_email,
        subscription_status=profile.subscription_status,
        subscription_tier=profile.subscription_tier,
        profile_picture_url=urls["profile_picture_url"],
        profile_video_url=urls["profile_video_url"],
        voice_note_path=profile.voice_note_path,
        voice_note_size=profile.voice_note_size,
    )

# ---------------------------------------------------------------------
# INTERNAL UTIL — Attach profile picture/video URLs
# ---------------------------------------------------------------------
from app.utils.urls import absolute_media_url

def attach_media_urls(db: Session, profile: Profile):
    picture_url = None
    video_url = None

    if profile.profile_picture_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == profile.profile_picture_media_id
        ).first()
        if media and media.file_path:
            if media.uploaded_at:
                ts = int(media.uploaded_at.timestamp())
                picture_url = absolute_media_url(
                    f"{media.file_path}?v={ts}"
                )
            else:
                picture_url = absolute_media_url(media.file_path)

    if profile.profile_video_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == profile.profile_video_media_id
        ).first()
        if media and media.file_path:
            if media.uploaded_at:
                ts = int(media.uploaded_at.timestamp())
                video_url = absolute_media_url(
                    f"{media.file_path}?v={ts}"
                )
            else:
                video_url = absolute_media_url(media.file_path)

    return {
        "profile_picture_url": picture_url,
        "profile_video_url": video_url,
    }

# ---------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------
@router.get("/search", response_model=List[ProfileSearchOut])
def search_profiles(
    query: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if len(query.strip()) < 2:
        return []

    # ----------------------------------------
    # Get viewer profile once (needed for blocks)
    # ----------------------------------------
    viewer_profile = (
        db.query(Profile)
        .filter(Profile.user_id == get_user_id(current_user))
        .first()
    )

    profiles = (
        db.query(Profile)
        .filter(Profile.full_name.ilike(f"%{query.strip()}%"))
        .limit(20)
        .all()
    )

    results = []

    for profile in profiles:
        # ----------------------------------------
        # Skip self
        # ----------------------------------------
        if viewer_profile and profile.id == viewer_profile.id:
            continue

        # ----------------------------------------
        # 🔒 Block filter
        # ----------------------------------------
        if viewer_profile and is_blocked(db, viewer_profile.id, profile.id):
            continue

        # ----------------------------------------
        # 🔒 Search disabled → do not appear
        # ----------------------------------------
        if not profile.is_searchable:
            continue

        picture_url = None

        if profile.profile_picture_media_id:
            media = (
                db.query(MediaFile)
                .filter(MediaFile.id == profile.profile_picture_media_id)
                .first()
            )
            if media:
                picture_url = absolute_media_url(media.file_path)

        results.append({
            "id": str(profile.id),
            "full_name": profile.full_name,
            "profile_picture_url": picture_url,
            "is_public": profile.is_public,
            "can_view": can_view_profile(
                db=db,
                viewer_user_id=get_user_id(current_user),
                target_profile_id=profile.id,
            ),
        })

    return results

# ---------------------------------------------------------------------
# GET MY PROFILE (Auto-create if missing)
# ---------------------------------------------------------------------
@router.get("/me", response_model=ProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_uuid = get_user_id(current_user)

    profile = db.query(Profile).filter(
        Profile.user_id == user_uuid
    ).first()

    # ✅ Auto-create profile if missing
    if not profile:
        profile = Profile(
            id=str(uuid.uuid4()),
            user_id=user_uuid,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return serialize_profile(profile, db)


# ---------------------------------------------------------------------
# CREATE PROFILE
# ---------------------------------------------------------------------
@router.get("/me", response_model=ProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_uuid = get_user_id(current_user)

    profile = db.query(Profile).filter(
        Profile.user_id == user_uuid
    ).first()

    # ✅ Auto-create profile if missing
    if not profile:
        profile = Profile(
            id=str(uuid.uuid4()),
            user_id=user_uuid,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return serialize_profile(profile, db)


# ---------------------------------------------------------------------
# UPDATE MY PROFILE
# ---------------------------------------------------------------------
@router.put("/me", response_model=ProfileOut)
def update_my_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(
        Profile.user_id == get_user_id(current_user)
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Apply only fields provided
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)

    urls = attach_media_urls(db, profile)
    
    return serialize_profile(profile, db)




# ---------------------------------------------------------------------
# UPDATE LONG BIOGRAPHY
# ---------------------------------------------------------------------
@router.put("/{profile_id}/biography", response_model=ProfileOut)
def update_biography(
    profile_id: str,
    payload: dict,   # expects {"long_biography": "..."}
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403, detail="Not authorised")

    new_bio = payload.get("long_biography")
    if new_bio is None:
        raise HTTPException(status_code=400, detail="Missing long_biography")

    profile.long_biography = new_bio
    db.commit()
    db.refresh(profile)

    urls = attach_media_urls(db, profile)
    return serialize_profile(profile, db)



# ---------------------------------------------------------------------
# UPLOAD pHOTO
# ---------------------------------------------------------------------

@router.post("/{profile_id}/upload-photo")
async def upload_profile_photo(
    profile_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403, detail="Not authorised")

    # Extension check only (no size limits)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Invalid image format")

    file_size = get_file_size(file)

    folder = f"users/{get_user_id(current_user)}/profiles/{profile_id}/profile-photo"
    url = save_file(folder, file)

    if profile.profile_picture_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == profile.profile_picture_media_id
        ).first()

        if media:
            delete_file(media.file_path)
            media.file_path = url
            media.file_size = file_size
            media.uploaded_at = datetime.utcnow()
            db.commit()
    else:
        media = MediaFile(
            user_id=get_user_id(current_user),
            profile_id=profile_id,
            file_path=url,
            file_type="image",
            original_scope="profile",
            file_size=file_size,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        profile.profile_picture_media_id = media.id
        db.commit()

    return {
        "id": media.id,
        "file_path": media.file_path,
        "file_size": media.file_size,
        "scope": "profile",
    }# ---------------------------------------------------------------------
# UPLOAD / UPDATE PROFILE VIDEO (WITH THUMBNAIL)
# ---------------------------------------------------------------------
import subprocess


def generate_video_thumbnail(video_path: str, thumb_path: str):
    """
    Extract a thumbnail image at 1 second into the video.
    Requires FFmpeg installed on the server.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",                  # overwrite if exists
            "-i", video_path,      # input file
            "-ss", "00:00:01",     # take frame at 1 second
            "-vframes", "1",       # only one frame
            thumb_path,            # output image
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@router.post("/{profile_id}/upload-video")
async def upload_profile_video(
    profile_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403, detail="Not authorised")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".mp4", ".mov", ".m4v"}:
        raise HTTPException(status_code=400, detail="Invalid video format")

    file_size = get_file_size(file)

    folder = f"users/{get_user_id(current_user)}/profiles/{profile_id}/profile-video"
    url = save_file(folder, file)

    if profile.profile_video_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == profile.profile_video_media_id
        ).first()

        if media:
            delete_file(media.file_path)
            media.file_path = url
            media.file_size = file_size
            media.uploaded_at = datetime.utcnow()
            db.commit()
    else:
        media = MediaFile(
            user_id=get_user_id(current_user),
            profile_id=profile_id,
            file_path=url,
            file_type="video",
            original_scope="profile",
            file_size=file_size,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        profile.profile_video_media_id = media.id
        db.commit()

    return {
        "id": media.id,
        "file_path": media.file_path,
        "file_size": media.file_size,
        "file_type": "video",
        "scope": "profile",
    }
# -------------------------------------------------
# ---------------------------------------------------------------------
# UPLOAD PROFILE AUDIO (Voice note)
# ---------------------------------------------------------------------
@router.post("/{profile_id}/voice-note")
async def upload_profile_voice_note(
    profile_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403, detail="Not authorised")

    # Extension sanity check only
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".m4a", ".aac", ".mp3", ".wav"}:
        raise HTTPException(status_code=400, detail="Invalid audio format")

    # ✅ Measure file size (for pricing / usage later)
    file_size = get_file_size(file)

    # Upload via shared storage helper
    url = save_voice_file(
        user_id=str(get_user_id(current_user)),
        profile_id=profile_id,
        scope="profile",
        upload=file,
    )

    # Remove old voice note if it exists
    if profile.voice_note_path:
        delete_file(profile.voice_note_path)

    # Persist new reference + size
    profile.voice_note_path = url
    profile.voice_note_size = file_size  # recommended column
    db.commit()

    return {
        "path": url,
        "file_size": file_size,
    }
# ---------------------------------------------------------------------
# DELETE PROFILE Photo
# ---------------------------------------------------------------------

@router.delete("/{profile_id}/photo")
def delete_profile_photo(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404)

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403)

    if not profile.profile_picture_media_id:
        return {"message": "No profile photo set"}

    media = db.query(MediaFile).filter(
        MediaFile.id == profile.profile_picture_media_id
    ).first()

    if media:
        delete_file(media.file_path)
        db.delete(media)

    profile.profile_picture_media_id = None
    db.commit()

    return {"success": True, "message": "Profile photo deleted"}
# ---------------------------------------------------------------------
# DELETE PROFILE Video
# ---------------------------------------------------------------------

@router.delete("/{profile_id}/video")
def delete_profile_video(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404)

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403)

    if not profile.profile_video_media_id:
        return {"message": "No profile video set"}

    media = db.query(MediaFile).filter(
        MediaFile.id == profile.profile_video_media_id
    ).first()

    if media:
        delete_file(media.file_path)
        db.delete(media)

    profile.profile_video_media_id = None
    db.commit()

    return {"success": True, "message": "Profile video deleted"}

# ---------------------------------------------------------------------
# DELETE PROFILE AUDIO
# ---------------------------------------------------------------------
@router.delete("/{profile_id}/voice-note")
async def delete_profile_voice_note(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404)

    if profile.user_id != get_user_id(current_user):
        raise HTTPException(status_code=403)

    if profile.voice_note_path:
     delete_file(profile.voice_note_path)

    profile.voice_note_path = None
    profile.voice_note_size = None  # ← important
    db.commit()

    return {"message": "Voice note deleted"}

# ---------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------
@router.get("/{profile_id}/relationships")
def get_profile_relationships(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    results = []

    connections = (
        db.query(Connection)
        .filter(
            Connection.status == "accepted",
            (Connection.from_profile_id == profile_id)
            | (Connection.to_profile_id == profile_id),
        )
        .all()
    )

    for c in connections:
        if c.from_profile_id == profile_id:
            other_id = c.to_profile_id
            label = c.from_profile_relation
        else:
            other_id = c.from_profile_id
            label = c.to_profile_relation

        if not label:
            continue

        other = db.query(Profile).filter(Profile.id == other_id).first()
        if not other:
            continue

        media_urls = attach_media_urls(db, other)

        results.append({
    "relation_label": label,
    "profile": {
        "id": str(other.id),
        "full_name": other.full_name,
        "profile_image": media_urls.get("profile_picture_url"),
        "is_public": other.is_public,
    },
})

    return results

# ---------------------------------------------------------------------
# Next of Kin
# ---------------------------------------------------------------------
class NextOfKinUpdate(BaseModel):
    next_of_kin_name: Optional[str] = None
    next_of_kin_email: Optional[EmailStr] = None

@router.put("/me/next-of-kin", response_model=ProfileOut)
def update_next_of_kin(
    payload: NextOfKinUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.user_id == get_user_id(current_user)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    data = payload.dict(exclude_unset=True)

    # Optional: normalise email
    if "next_of_kin_email" in data and data["next_of_kin_email"]:
        data["next_of_kin_email"] = data["next_of_kin_email"].lower().strip()

    for key, value in data.items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)

    urls = attach_media_urls(db, profile)
    return serialize_profile(profile, db)
# ---------------------------------------------------------------------
# GET PROFILE BY ID (PUBLIC / LIMITED / CONNECTED)
# ---------------------------------------------------------------------
@router.get("/{profile_id}")
def get_profile_by_id(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # -------------------------------------------------
    # 🔒 BLOCK CHECK — behave as if profile does not exist
    # -------------------------------------------------
    viewer_profile = (
        db.query(Profile)
        .filter(Profile.user_id == get_user_id(current_user))
        .first()
    )

    if viewer_profile and is_blocked(db, viewer_profile.id, profile_id):
        # IMPORTANT: 404, not 403
        raise HTTPException(status_code=404, detail="Profile not found")

    # -------------------------------------------------
    # EXISTING VISIBILITY LOGIC (UNCHANGED)
    # -------------------------------------------------
    allowed = can_view_profile(db, get_user_id(current_user), profile_id)

    # ----------------------------------------
    # NOT ALLOWED → RETURN LIMITED PROFILE
    # ----------------------------------------
    if not allowed:
        return ProfileOutLimited(
            id=str(profile.id),
            user_id=str(profile.user_id),
            full_name=profile.full_name,
            bio=profile.bio,
            long_biography=None,      # hide full biography
            is_public=profile.is_public,
            dob_label="DOB hidden",
            is_deceased=None,
            can_view=False,
        )

    # ----------------------------------------
    # ALLOWED → RETURN FULL PROFILE
    # ----------------------------------------
    return serialize_profile(profile, db)
