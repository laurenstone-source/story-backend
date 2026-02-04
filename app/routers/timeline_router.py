import os
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException
)
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.auth import get_current_user
from app.core.profile_visibility import can_view_profile

from app.schemas.timeline_schema import (
    TimelineEventCreate,
    TimelineEventUpdate,
    TimelineEventOut,
)
from app.schemas.media_schema import MediaFileOut

from app.models.timeline_event import TimelineEvent
from app.models.media import MediaFile
from app.models.profile import Profile
from app.models.user import User

from app.storage import save_file, delete_file, save_voice_file, validate_file_size

from app.storage import save_voice_file

router = APIRouter(prefix="/timeline", tags=["Timeline Events"])


# =====================================================================
# Helper: Check if user owns the profile
# =====================================================================
def owns_profile(user_id: str, profile_id: str, db: Session):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    return profile and profile.user_id == user_id


# =====================================================================
# CREATE EVENT
# =====================================================================
@router.post("/add", response_model=TimelineEventOut)
def add_event(
    data: TimelineEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not owns_profile(current_user.id, data.profile_id, db):
        raise HTTPException(status_code=403, detail="Not your profile")

    # ✅ VALIDATE DATE RANGE FIRST
    if data.end_date and data.end_date < data.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date"
        )

    event = TimelineEvent(
        profile_id=data.profile_id,
        title=data.title,
        description=data.description,
        start_date=data.start_date,
        end_date=data.end_date,
        date_precision=data.date_precision,
        order_index=data.order_index,
    )

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# =====================================================================
# UPDATE EVENT
# =====================================================================
@router.put("/{event_id}", response_model=TimelineEventOut)
def update_event(
    event_id: int,
    update_data: TimelineEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    data = update_data.dict(exclude_unset=True)

    # ✅ DATE RANGE SAFETY
    start = data.get("start_date", event.start_date)
    end = data.get("end_date", event.end_date)
    if end and start and end < start:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date"
        )

    for key, value in data.items():
        setattr(event, key, value)

    db.commit()
    db.refresh(event)
    return event


# =====================================================================
# GET SINGLE EVENT
# =====================================================================
@router.get("/event/{event_id}", response_model=TimelineEventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = (
        db.query(TimelineEvent)
        .filter(TimelineEvent.id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    if not can_view_profile(
        db=db,
        viewer_user_id=current_user.id,
        target_profile_id=event.profile_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Not authorised",
        )

    return event
#=====================================================================
# GET ALL EVENTS FOR PROFILE
# =====================================================================
@router.get("/profile/{profile_id}", response_model=list[TimelineEventOut])
def get_profile_events(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_view_profile(
        db=db,
        viewer_user_id=current_user.id,
        target_profile_id=profile_id,
    ):
        raise HTTPException(status_code=403, detail="Not authorised")

    events = (
        db.query(TimelineEvent)
        .options(joinedload(TimelineEvent.main_media))
        .filter(TimelineEvent.profile_id == profile_id)
        .order_by(
            TimelineEvent.start_date.desc(),
            TimelineEvent.order_index.asc(),
        )
        .all()
    )

    return events
# =====================================================================
# UPLOAD / REPLACE MAIN EVENT IMAGE
# =====================================================================
@router.post("/{event_id}/upload-main", response_model=MediaFileOut)
async def upload_timeline_main_media(
    event_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    ok, msg = validate_file_size(file)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    # ✅ Supabase folder path (string)
    folder = f"users/{current_user.id}/profiles/{event.profile_id}/events/{event.id}/main"

    # ✅ Upload new image
    url = save_file(folder, file)

    # -------------------------------------------------
    # REPLACE EXISTING IMAGE
    # -------------------------------------------------
    if event.main_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == event.main_media_id
        ).first()

        if media:
            # ✅ Delete old Supabase file
            delete_file(media.file_path)

            # Update record
            media.file_path = url
            media.uploaded_at = datetime.utcnow()
            db.commit()
            db.refresh(media)

            return MediaFileOut.from_orm(media)

    # -------------------------------------------------
    # FIRST UPLOAD
    # -------------------------------------------------
    media = MediaFile(
        user_id=current_user.id,
        profile_id=event.profile_id,
        event_id=event.id,
        file_path=url,
        file_type="image",
        original_scope="event",
    )

    db.add(media)
    db.commit()
    db.refresh(media)

    event.main_media_id = media.id
    db.commit()

    return MediaFileOut.from_orm(media)

# =====================================================================
# DELETE Photo
# =====================================================================
@router.delete("/{event_id}/main-media")
def delete_event_main_media(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    if not event.main_media_id:
        return {"message": "No main image set"}

    media = db.query(MediaFile).filter(
        MediaFile.id == event.main_media_id
    ).first()

    if media:
        # ✅ Delete from Supabase
        delete_file(media.file_path)

        db.delete(media)

    event.main_media_id = None
    db.commit()

    return {"success": True, "message": "Event main image deleted"}
# =====================================================================
# DELETE EVENT
# =====================================================================
@router.delete("/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404)

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403)

    # ✅ Delete main media
    if event.main_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == event.main_media_id
        ).first()

        if media:
            delete_file(media.file_path)
            db.delete(media)

    # ✅ Delete voice note
    if event.audio_url:
        delete_file(event.audio_url)

    db.delete(event)
    db.commit()

    return {"status": "success"}


# =====================================================================
# UPLOAD EVENT VOICE NOTE (Unified)
# =====================================================================
@router.post("/{event_id}/voice-note")
async def upload_event_voice_note(
    event_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    folder = f"users/{current_user.id}/profiles/{event.profile_id}/events/{event.id}/voice"

    # ✅ Upload new audio
    url = save_file(folder, file)

    # ✅ Delete old audio if exists
    if event.audio_url:
        delete_file(event.audio_url)

    event.audio_url = url
    db.commit()
    db.refresh(event)

    return {"path": url, "success": True}

# =====================================================================
# DELETE EVENT VOICE NOTE
# =====================================================================
@router.delete("/{event_id}/voice-note")
async def delete_event_voice_note(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    if event.audio_url:
        delete_file(event.audio_url)

    event.audio_url = None
    db.commit()

    return {"message": "Event audio deleted"}

# =====================================================================
# UPDATE EVENT STORY
# =====================================================================
@router.put("/{event_id}/story", response_model=TimelineEventOut)
async def update_event_story(
    event_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story = payload.get("story_text")
    if story is None:
        raise HTTPException(status_code=400, detail="story_text required")

    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not owns_profile(current_user.id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    event.story_text = story
    db.commit()
    db.refresh(event)

    return event
