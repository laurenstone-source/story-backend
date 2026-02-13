import os
import uuid
from datetime import datetime
import tempfile
import subprocess
import requests
from pathlib import Path

from app.config import settings
from app.supabase_client import supabase

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException
)
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.auth.supabase_auth import get_current_user
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

from app.storage import save_file, delete_file, save_voice_file, get_file_size


router = APIRouter(prefix="/timeline", tags=["Timeline Events"])



def get_user_uuid(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["sub"])
# =====================================================================
# Helper: Check if user owns the profile
# =====================================================================
def owns_profile(user_id: uuid.UUID, profile_id: str, db: Session) -> bool:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    return bool(profile) and profile.user_id == user_id


# =====================================================================
# CREATE EVENT
# =====================================================================
@router.post("/add", response_model=TimelineEventOut)
def add_event(
    data: TimelineEventCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not owns_profile(current_user["sub"], data.profile_id, db):
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
         item_type=data.item_type,  # ✅ NEW
         start_date=data.start_date,
         end_date=data.end_date,
         date_precision=data.date_precision,
         order_index=data.order_index,
         viewer_id = get_user_uuid(current_user)
     )

    if not owns_profile(viewer_id, data.profile_id, db):
       raise HTTPException(status_code=403, detail="Not your profile")

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
    current_user: dict = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    viewer_id = get_user_uuid(current_user)
if not owns_profile(viewer_id, event.profile_id, db):
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
    current_user: dict = Depends(get_current_user),
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
        viewer_user_id=current_user["sub"],
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
    current_user: dict = Depends(get_current_user),
):
    if not can_view_profile(
        db=db,
        viewer_user_id=current_user["sub"],
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
# UPLOAD / REPLACE MAIN EVENT MEDIA (Image or Video)
# =====================================================================


@router.post("/{event_id}/upload-main", response_model=MediaFileOut)
async def upload_timeline_main_media(
    event_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    viewer_id = get_user_uuid(current_user)
    
    if not owns_profile(viewer_id, event.profile_id, db):
       raise HTTPException(status_code=403, detail="Not authorised")

    ext = os.path.splitext(file.filename)[1].lower()

    allowed_image_types = {".jpg", ".jpeg", ".png", ".webp"}
    allowed_video_types = {".mp4", ".mov", ".webm"}

    if ext not in allowed_image_types and ext not in allowed_video_types:
        raise HTTPException(status_code=400, detail="Unsupported media type")

    file_size = get_file_size(file)

    folder = (
        f"users/{current_user["sub"]}/profiles/{event.profile_id}/events/{event.id}/main"
    )

    # ---------------------------------------------------------
    # 1️⃣ SAVE ORIGINAL FILE TO SUPABASE
    # ---------------------------------------------------------
    url = save_file(folder, file)
    file_type = "image" if ext in allowed_image_types else "video"

    thumbnail_url = None

    # ---------------------------------------------------------
    # 2️⃣ IF VIDEO → GENERATE THUMBNAIL
    # ---------------------------------------------------------
    if file_type == "video":
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)

                # Download video from Supabase public URL
                video_path = tmpdir / "video.mp4"

                r = requests.get(url)
                r.raise_for_status()

                with open(video_path, "wb") as f:
                    f.write(r.content)

                # Generate thumbnail locally
                thumb_path = tmpdir / "thumb.jpg"

                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(video_path),
                        "-ss",
                        "00:00:01.000",
                        "-vframes",
                        "1",
                        str(thumb_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )

                # Upload thumbnail to Supabase
                thumb_filename = f"thumb_{uuid.uuid4()}.jpg"
                thumb_key = f"{folder}/{thumb_filename}"

                with open(thumb_path, "rb") as f:
                    supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
                        thumb_key,
                        f.read(),
                        {"content-type": "image/jpeg"},
                    )

                thumbnail_url = (
                    supabase.storage
                    .from_(settings.SUPABASE_BUCKET)
                    .get_public_url(thumb_key)
                )

        except Exception as e:
            print("Thumbnail generation failed:", e)

    # ---------------------------------------------------------
    # 3️⃣ REPLACE EXISTING MEDIA
    # ---------------------------------------------------------
    if event.main_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == event.main_media_id
        ).first()

        if media:
            delete_file(media.file_path)

            if media.thumbnail_path:
                delete_file(media.thumbnail_path)

            media.file_path = url
            media.file_type = file_type
            media.file_size = file_size
            media.thumbnail_path = thumbnail_url
            media.uploaded_at = datetime.utcnow()

            db.commit()
            db.refresh(media)
            return MediaFileOut.from_orm(media)

    # ---------------------------------------------------------
    # 4️⃣ CREATE NEW MEDIA
    # ---------------------------------------------------------
    media = MediaFile(
        user_id=current_user["sub"],
        profile_id=event.profile_id,
        event_id=event.id,
        file_path=url,
        file_type=file_type,
        thumbnail_path=thumbnail_url,
        original_scope="event",
        file_size=file_size,
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
    current_user: dict = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    viewer_id = get_user_uuid(current_user)
    if not owns_profile(viewer_id, event.profile_id, db):
       raise HTTPException(status_code=403, detail="Not authorised")

    if not event.main_media_id:
        return {"message": "No main image set"}

    media = db.query(MediaFile).filter(
        MediaFile.id == event.main_media_id
    ).first()

    if media:
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
    current_user: dict = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404)

    viewer_id = get_user_uuid(current_user)
    if not owns_profile(viewer_id, event.profile_id, db):
       raise HTTPException(status_code=403, detail="Not authorised")

    if event.main_media_id:
        media = db.query(MediaFile).filter(
            MediaFile.id == event.main_media_id
        ).first()

        if media:
            delete_file(media.file_path)
            db.delete(media)

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
    current_user: dict = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    viewer_id = get_user_uuid(current_user)
    if not owns_profile(viewer_id, event.profile_id, db):
       raise HTTPException(status_code=403, detail="Not authorised")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".m4a", ".aac", ".mp3", ".wav"}:
        raise HTTPException(status_code=400, detail="Invalid audio format")

    file_size = get_file_size(file)

    url = save_voice_file(
        user_id=str(current_user["sub"]),
        profile_id=str(event.profile_id),
        scope="event",
        upload=file,
        event_id=event.id,
    )

    if event.audio_url:
        delete_file(event.audio_url)

    event.audio_url = url
    event.audio_size = file_size  # recommended column
    db.commit()
    db.refresh(event)

    return {"path": url, "file_size": file_size, "success": True}
# =====================================================================
# DELETE EVENT VOICE NOTE
# =====================================================================
@router.delete("/{event_id}/voice-note")
async def delete_event_voice_note(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

     viewer_id = get_user_uuid(current_user)
     if not owns_profile(viewer_id, event.profile_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    if event.audio_url:
        delete_file(event.audio_url)

    event.audio_url = None
    event.audio_size = None
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
    current_user: dict = Depends(get_current_user),
):
    story = payload.get("story_text")
    if story is None:
        raise HTTPException(status_code=400, detail="story_text required")

    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    viewer_id = get_user_uuid(current_user)
    if not owns_profile(viewer_id, event.profile_id, db):
       raise HTTPException(status_code=403, detail="Not authorised")

    event.story_text = story
    db.commit()
    db.refresh(event)

    return event
