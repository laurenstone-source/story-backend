# app/routers/gallery_router.py

import os
import uuid
import subprocess
import json
import tempfile
import requests
from pathlib import Path
from app.supabase_client import supabase
from app.config import settings
from datetime import datetime

from typing import List


from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Body,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.supabase_auth import get_current_user
from app.models.event_gallery import EventGallery
from app.models.media import MediaFile
from app.models.timeline_event import TimelineEvent
from app.models.profile import Profile
from fastapi import UploadFile, File
from app.core.profile_visibility import can_view_profile


from app.schemas.gallery_schema import (
    GalleryOut,
    GalleryMediaOut,
    GalleryCreate,
    GalleryUpdate,
    GalleryMediaUpdate,
)

from app.storage import save_file, delete_file, save_voice_file, get_file_size


router = APIRouter(prefix="/gallery", tags=["Galleries"])



# =====================================================================
# GLOBAL FFmpeg PATHS (Windows)
# =====================================================================

FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"

# =====================================================================
# FFMPEG HELPERS
# =====================================================================

def generate_video_thumbnail(video_path: str, output_path: str) -> bool:
    """Extract 1 frame using FFmpeg."""
    try:
        cmd = [
            FFMPEG_PATH,
            "-ss", "00:00:00.200",
            "-i", video_path,
            "-vframes", "1",
            "-y",
            output_path,
        ]

        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True

    except Exception as e:
        print("FFMPEG ERROR:", e)
        return False


def get_video_duration_seconds(video_path: str) -> int:
    """Return video duration in seconds (0 on failure)."""
    try:
        cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data = json.loads(result.stdout)

        duration = float(data["format"]["duration"])
        return int(duration)

    except Exception as e:
        print("FFPROBE ERROR:", e)
        return 0


# =====================================================================
# OWNERSHIP CHECK
# =====================================================================

def owns_event(user_id: str, event_id: int, db: Session) -> bool:
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        return False

    profile = db.query(Profile).filter(Profile.id == event.profile_id).first()
    return profile and profile.user_id == user_id
# =====================================================================
# Viewing check
# =====================================================================
def can_view_event(user_id: str, event_id: int, db: Session) -> bool:
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        return False

    return can_view_profile(
        db=db,
        viewer_user_id=user_id,
        target_profile_id=event.profile_id,
    )

# =====================================================================
# BUILD GALLERY RESPONSE
# =====================================================================

def build_gallery(db: Session, gallery: EventGallery) -> GalleryOut:
    """Returns gallery with sorted media."""
    thumb_media = None
    if gallery.main_media_id:
        m = db.query(MediaFile).filter(MediaFile.id == gallery.main_media_id).first()
        if m:
            thumb_media = GalleryMediaOut.from_orm(m)

    media_items = (
        db.query(MediaFile)
        .filter(MediaFile.gallery_id == gallery.id)
        .order_by(MediaFile.order_index.asc())
        .all()
    )

    return GalleryOut(
        id=gallery.id,
        event_id=gallery.event_id,
        title=gallery.title,
        description=gallery.description,
        long_description=gallery.long_description,
        position=gallery.position,
        thumbnail_media_id=gallery.main_media_id,
        thumbnail_media=thumb_media,
        voice_note_path=gallery.voice_note_path,
        created_at=gallery.created_at,
        media_items=[GalleryMediaOut.from_orm(m) for m in media_items],
    )


# =====================================================================
# CREATE GALLERY
# =====================================================================

@router.post("/", response_model=GalleryOut)
def create_gallery(
    payload: GalleryCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not owns_event(current_user["sub"], payload.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    g = EventGallery(
        event_id=payload.event_id,
        title=payload.title,
        description=payload.description,
        long_description=payload.long_description,
    )

    db.add(g)
    db.commit()
    db.refresh(g)

    return build_gallery(db, g)


# =====================================================================
# UPDATE GALLERY
# =====================================================================

@router.put("/{gallery_id}", response_model=GalleryOut)
def update_gallery(
    gallery_id: int,
    payload: GalleryUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    if payload.title is not None:
        g.title = payload.title
    if payload.description is not None:
        g.description = payload.description
    if payload.long_description is not None:
        g.long_description = payload.long_description

    db.commit()
    db.refresh(g)

    return build_gallery(db, g)


# =====================================================================
# GET GALLERIES FOR EVENT
# =====================================================================

@router.get("/event/{event_id}", response_model=List[GalleryOut])
def get_galleries_for_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not can_view_event(current_user["sub"], event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    galleries = (
        db.query(EventGallery)
        .filter(EventGallery.event_id == event_id)
        .order_by(EventGallery.position.asc())
        .all()
    )

    return [build_gallery(db, g) for g in galleries]

# =====================================================================
# GET SINGLE GALLERY
# =====================================================================

@router.get("/{gallery_id}", response_model=GalleryOut)
def get_single_gallery(
    gallery_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not can_view_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    return build_gallery(db, g)

# =====================================================================
# DELETE GALLERY
# =====================================================================

@router.delete("/{gallery_id}")
def delete_gallery(
    gallery_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    try:
        # 🔥 BREAK circular reference FIRST
        g.main_media_id = None
        

        # --------------------------------------------------
        # DELETE ALL MEDIA IN GALLERY
        # --------------------------------------------------
        media_items = db.query(MediaFile).filter(
            MediaFile.gallery_id == gallery_id
        ).all()

        for m in media_items:
            for path in [m.file_path, m.thumbnail_path, m.voice_note_path]:
                if path:
                    delete_file(path)

            db.delete(m)

        # --------------------------------------------------
        # DELETE GALLERY VOICE NOTE
        # --------------------------------------------------
        if g.voice_note_path:
            delete_file(g.voice_note_path)

        # --------------------------------------------------
        # DELETE GALLERY
        # --------------------------------------------------
        db.delete(g)
        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"DB delete failed: {e}"
        )

    return {"message": "Gallery deleted"}
# ==========================================================
# REORDER GALLERIES
# ==========================================================

@router.put("/event/{event_id}/reorder")
def reorder_galleries(
    event_id: int,
    ids: List[int] = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not owns_event(current_user["sub"], event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    galleries = (
        db.query(EventGallery)
        .filter(EventGallery.event_id == event_id)
        .order_by(EventGallery.position)
        .all()
    )

    id_to_gallery = {g.id: g for g in galleries}

    for index, gallery_id in enumerate(ids):
        g = id_to_gallery.get(gallery_id)
        if g:
            g.position = index

    db.commit()
    return {"message": "Order saved"}

# =====================================================================
# REORDER MEDIA
# =====================================================================

@router.put("/{gallery_id}/media/reorder")
def reorder_media(
    gallery_id: int,
    ids: List[int] = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    for index, media_id in enumerate(ids):
        m = (
            db.query(MediaFile)
            .filter(MediaFile.id == media_id, MediaFile.gallery_id == gallery_id)
            .first()
        )
        if m:
            m.order_index = index

    db.commit()
    return {"message": "Order saved"}

# ==========================================================
# UPLOAD MEDIA-LEVEL VOICE NOTE (UNIFIED)
# ==========================================================

@router.post("/{gallery_id}/media/{media_id}/voice")
async def upload_media_voice_note(
    gallery_id: int,
    media_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404)

    if not owns_event(current_user["sub"], gallery.event_id, db):
        raise HTTPException(status_code=403)

    media = db.query(MediaFile).filter(
        MediaFile.id == media_id,
        MediaFile.gallery_id == gallery_id
    ).first()
    if not media:
        raise HTTPException(status_code=404)

    event = gallery.event

    # ✅ Measure size
    file_size = get_file_size(file)

    url = save_voice_file(
        user_id=str(current_user["sub"]),
        profile_id=str(event.profile_id),
        event_id=event.id,
        gallery_id=gallery_id,
        media_id=media_id,
        scope="media",
        upload=file,
    )

    if media.voice_note_path:
        delete_file(media.voice_note_path)

    media.voice_note_path = url
    media.voice_note_size = file_size  # ✅ IMPORTANT
    db.commit()

    return {"path": url, "success": True}
# ==========================================================
# DELETE MEDIA-LEVEL VOICE NOTE
# ==========================================================

@router.delete("/{gallery_id}/media/{media_id}/voice")
async def delete_media_voice_note(
    gallery_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404)

    if not owns_event(current_user["sub"], gallery.event_id, db):
        raise HTTPException(status_code=403)

    media = db.query(MediaFile).filter(
        MediaFile.id == media_id,
        MediaFile.gallery_id == gallery_id
    ).first()
    if not media:
        raise HTTPException(status_code=404)

    if media.voice_note_path:
        delete_file(media.voice_note_path)

    media.voice_note_path = None
    media.voice_note_size = None  # ✅ IMPORTANT
    db.commit()

    return {"message": "Media voice note deleted", "success": True}

# =====================================================================
# UPLOAD GALLERY MEDIA
# =====================================================================
@router.post("/{gallery_id}/upload-media", response_model=GalleryMediaOut)
async def upload_gallery_media(
    gallery_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user["sub"], gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    event = gallery.event
    profile_id = event.profile_id
    user_id = current_user["sub"]

    ext = os.path.splitext(file.filename)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".mkv", ".wmv"}

    if not is_video and ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_size = get_file_size(file)

    folder = f"users/{user_id}/profiles/{profile_id}/events/{event.id}/galleries/{gallery_id}/original"

    # 1️⃣ Upload original
    file_url = save_file(folder, file)

    thumbnail_url = None
    duration_seconds = None

    # 2️⃣ If video → generate thumbnail
    if is_video:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)

                video_path = tmpdir / "video.mp4"
                thumb_path = tmpdir / "thumb.jpg"

                # Download uploaded video
                r = requests.get(file_url)
                r.raise_for_status()

                with open(video_path, "wb") as f:
                    f.write(r.content)

                # Generate thumbnail
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(video_path),
                        "-ss",
                        "00:00:00.500",
                        "-vframes",
                        "1",
                        str(thumb_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )

                # Upload thumbnail
                thumb_filename = f"thumb_{uuid.uuid4()}.jpg"
                thumb_key = f"{folder}/{thumb_filename}"

                with open(thumb_path, "rb") as f:
                    supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
                        thumb_key,
                        f.read(),
                        {"content-type": "image/jpeg"},
                    )

                thumbnail_url = supabase.storage.from_(
                    settings.SUPABASE_BUCKET
                ).get_public_url(thumb_key)

        except Exception as e:
            print("Gallery thumbnail generation failed:", e)

    # Get next order index
    last = (
        db.query(MediaFile)
        .filter(MediaFile.gallery_id == gallery_id)
        .order_by(MediaFile.order_index.desc())
        .first()
    )
    next_index = (last.order_index + 1) if last else 0

    media = MediaFile(
        user_id=user_id,
        profile_id=profile_id,
        event_id=event.id,
        gallery_id=gallery_id,
        file_path=file_url,
        file_type="video" if is_video else "image",
        caption=caption,
        order_index=next_index,
        uploaded_at=datetime.utcnow(),
        original_scope="gallery",
        file_size=file_size,
        thumbnail_path=thumbnail_url,
        duration_seconds=duration_seconds,
    )

    db.add(media)
    db.commit()
    db.refresh(media)

    return GalleryMediaOut.from_orm(media)
# =====================================================================
# REPLACE GALLERY MEDIA FILE (EDIT)
# =====================================================================
@router.post("/{gallery_id}/media/{media_id}/replace", response_model=GalleryMediaOut)
async def replace_gallery_media(
    gallery_id: int,
    media_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404)

    if not owns_event(current_user["sub"], gallery.event_id, db):
        raise HTTPException(status_code=403)

    media = db.query(MediaFile).filter(
        MediaFile.id == media_id,
        MediaFile.gallery_id == gallery_id
    ).first()
    if not media:
        raise HTTPException(status_code=404)

    # ✅ Delete old files
    delete_file(media.file_path)
    if media.thumbnail_path:
        delete_file(media.thumbnail_path)

    ext = os.path.splitext(file.filename)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".mkv", ".wmv"}

    # ✅ Measure size
    file_size = get_file_size(file)

    folder = f"users/{current_user["sub"]}/profiles/{gallery.event.profile_id}/events/{gallery.event_id}/galleries/{gallery_id}/original"

    new_url = save_file(folder, file)

    media.file_path = new_url
    media.file_type = "video" if is_video else "image"
    media.thumbnail_path = None
    media.duration_seconds = None
    media.file_size = file_size  # ✅ IMPORTANT
    media.uploaded_at = datetime.utcnow()

    db.commit()
    db.refresh(media)

    return GalleryMediaOut.from_orm(media)
# =====================================================================
# UPDATE MEDIA CAPTION
# =====================================================================

@router.put("/{gallery_id}/media/{media_id}", response_model=GalleryMediaOut)
def update_media(
    gallery_id: int,
    media_id: int,
    payload: GalleryMediaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    m = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not m or m.gallery_id != gallery_id:
        raise HTTPException(status_code=404, detail="Media not found")

    if payload.caption is not None:
        cleaned = payload.caption.strip()
        m.caption = cleaned or None

    db.commit()
    db.refresh(m)

    return GalleryMediaOut.from_orm(m)


# =====================================================================
# DELETE MEDIA
# =====================================================================

@router.delete("/{gallery_id}/media/{media_id}")
def delete_gallery_media(
    gallery_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404)

    if not owns_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403)

    m = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not m:
        raise HTTPException(status_code=404)

    if g.main_media_id == media_id:
        g.main_media_id = None

    for p in [m.file_path, m.thumbnail_path, m.voice_note_path]:
        if p:
            delete_file(p)

    db.delete(m)
    db.commit()

    return {"message": "Media deleted"}


# =====================================================================
# SET GALLERY THUMBNAIL
# =====================================================================

@router.put("/{gallery_id}/set-thumbnail/{media_id}", response_model=GalleryOut)
def set_gallery_thumbnail(
    gallery_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user["sub"], g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    m = (
        db.query(MediaFile)
        .filter(MediaFile.id == media_id, MediaFile.gallery_id == gallery_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Media not found in gallery")

    g.main_media_id = media_id
    db.commit()
    db.refresh(g)

    return build_gallery(db, g)


# =====================================================================
# UPLOAD GALLERY-LEVEL VOICE NOTE  (UNIFIED)
# =====================================================================

@router.post("/{gallery_id}/voice-note")
async def upload_gallery_voice_note(
    gallery_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404)

    if not owns_event(current_user["sub"], gallery.event_id, db):
        raise HTTPException(status_code=403)

    event = gallery.event

    # ✅ Measure size
    file_size = get_file_size(file)

    url = save_voice_file(
        user_id=str(current_user["sub"]),
        profile_id=str(event.profile_id),
        event_id=event.id,
        gallery_id=gallery_id,
        scope="gallery",
        upload=file,
    )

    if gallery.voice_note_path:
        delete_file(gallery.voice_note_path)

    gallery.voice_note_path = url
    gallery.voice_note_size = file_size  # ✅ IMPORTANT
    db.commit()

    return {"path": url, "success": True}

# =====================================================================
# DELETE GALLERY-LEVEL VOICE NOTE  (UNIFIED)
# =====================================================================

@router.delete("/{gallery_id}/voice-note")
async def delete_gallery_voice_note(
    gallery_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404)

    if not owns_event(current_user["sub"], gallery.event_id, db):
        raise HTTPException(status_code=403)

    if gallery.voice_note_path:
        delete_file(gallery.voice_note_path)

    gallery.voice_note_path = None
    gallery.voice_note_size = None  # ✅ IMPORTANT
    db.commit()

    return {"message": "Gallery voice note deleted", "success": True}
