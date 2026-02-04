# app/routers/gallery_router.py

import os
import uuid
import shutil
import subprocess
import json
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
from app.auth import get_current_user

from app.models.event_gallery import EventGallery
from app.models.media import MediaFile
from app.models.timeline_event import TimelineEvent
from app.models.profile import Profile
from app.models.user import User
from fastapi import UploadFile, File
from app.core.profile_visibility import can_view_profile


from app.schemas.gallery_schema import (
    GalleryOut,
    GalleryMediaOut,
    GalleryCreate,
    GalleryUpdate,
    GalleryMediaUpdate,
)

from app.storage import validate_file_size


router = APIRouter(prefix="/gallery", tags=["Galleries"])



# =====================================================================
# GLOBAL FFmpeg PATHS (Windows)
# =====================================================================

FFMPEG_PATH = r"C:\Users\laure\ffmpeg-2025-11-24-git-c732564d2e-full_build\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\Users\laure\ffmpeg-2025-11-24-git-c732564d2e-full_build\bin\ffprobe.exe"


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
    current_user: User = Depends(get_current_user),
):
    if not owns_event(current_user.id, payload.event_id, db):
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
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, g.event_id, db):
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
    current_user: User = Depends(get_current_user),
):
    if not can_view_event(current_user.id, event_id, db):
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
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not can_view_event(current_user.id, g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    return build_gallery(db, g)

# =====================================================================
# DELETE GALLERY
# =====================================================================

@router.delete("/{gallery_id}")
def delete_gallery(
    gallery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    # --------------------------------------------------
    # Clear main media + gallery-level voice note
    # --------------------------------------------------
    g.main_media_id = None
    g.voice_note_path = None
    db.commit()

    # --------------------------------------------------
    # Delete all media inside this gallery
    # --------------------------------------------------
    media_items = db.query(MediaFile).filter(MediaFile.gallery_id == gallery_id).all()

    for m in media_items:
        for p in [m.file_path, m.thumbnail_path, m.voice_note_path]:
            if p:
                fs = p.lstrip("/").replace("/", os.sep)
                if os.path.exists(fs):
                    try:
                        os.remove(fs)
                    except:
                        pass

        db.delete(m)

    db.commit()

    # --------------------------------------------------
    # Delete gallery itself
    # --------------------------------------------------
    db.delete(g)
    db.commit()

    return {"message": "Gallery deleted"}

# ==========================================================
# REORDER GALLERIES
# ==========================================================

@router.put("/event/{event_id}/reorder")
def reorder_galleries(
    event_id: int,
    ids: List[int] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not owns_event(current_user.id, event_id, db):
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
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, g.event_id, db):
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

from app.storage import save_voice_file

@router.post("/{gallery_id}/media/{media_id}/voice")
async def upload_media_voice_note(
    gallery_id: int,
    media_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Verify gallery exists
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    # 2. Verify user owns the event
    if not owns_event(current_user.id, gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    # 3. Verify media exists inside this gallery
    media = db.query(MediaFile).filter(
        MediaFile.id == media_id,
        MediaFile.gallery_id == gallery_id
    ).first()

    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # 4. Save audio with shared helper
    event = gallery.event

    url = save_voice_file(
        user_id=str(current_user.id),
        profile_id=str(event.profile_id),
        event_id=event.id,
        gallery_id=gallery_id,
        media_id=media_id,
        scope="media",     # tells storage.py: media-level voice
        upload=file,
    )

    # 5. Delete old recording
    if media.voice_note_path:
        old = media.voice_note_path.lstrip("/").replace("/", os.sep)
        if os.path.exists(old):
            try: os.remove(old)
            except: pass

    # 6. Update DB
    media.voice_note_path = url
    db.commit()
    db.refresh(media)

    return {"path": url, "success": True}

# ==========================================================
# DELETE MEDIA-LEVEL VOICE NOTE
# ==========================================================

@router.delete("/{gallery_id}/media/{media_id}/voice")
async def delete_media_voice_note(
    gallery_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    media = db.query(MediaFile).filter(
        MediaFile.id == media_id,
        MediaFile.gallery_id == gallery_id
    ).first()

    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # delete file
    if media.voice_note_path:
        fs_path = media.voice_note_path.lstrip("/").replace("/", os.sep)
        if os.path.exists(fs_path):
            try: os.remove(fs_path)
            except: pass

    media.voice_note_path = None
    db.commit()

    return {"message": "Voice note deleted", "success": True}


# =====================================================================
# UPLOAD GALLERY MEDIA
# =====================================================================
@router.post("/{gallery_id}/upload-media", response_model=GalleryMediaOut)
async def upload_gallery_media(
    gallery_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    event = gallery.event
    profile_id = event.profile_id
    user_id = current_user.id

    ext = os.path.splitext(file.filename)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".mkv", ".wmv"}

    if not is_video and ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    base_folder = (
        f"media/users/{user_id}/profiles/{profile_id}/"
        f"events/{event.id}/galleries/{gallery_id}"
    )
    orig_folder = os.path.join(base_folder, "original")
    os.makedirs(orig_folder, exist_ok=True)

    # -------------------------------------------------
    # ALWAYS CREATE A NEW FILE
    # -------------------------------------------------
    file.file.seek(0)
    filename = f"{uuid.uuid4()}{ext}"
    full_path = os.path.join(orig_folder, filename)

    with open(full_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    file_url = "/" + full_path.replace(os.sep, "/")
    file_size = os.path.getsize(full_path)

    thumb_url = None
    duration_seconds = None

    if is_video:
        thumb_folder = os.path.join(base_folder, "thumbnails")
        os.makedirs(thumb_folder, exist_ok=True)

        thumb_path = os.path.join(
            thumb_folder, f"thumb_{uuid.uuid4()}.jpg"
        )
        if generate_video_thumbnail(full_path, thumb_path):
            thumb_url = "/" + thumb_path.replace(os.sep, "/")

        secs = get_video_duration_seconds(full_path)
        duration_seconds = secs if secs and secs > 0 else None

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
        file_size=file_size,
        thumbnail_path=thumb_url,
        order_index=next_index,
        duration_seconds=duration_seconds,
        uploaded_at=datetime.utcnow(),
        original_scope="gallery",
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
    current_user: User = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    media = (
        db.query(MediaFile)
        .filter(
            MediaFile.id == media_id,
            MediaFile.gallery_id == gallery_id,
        )
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # -------------------------------------------------
    # DELETE OLD FILES
    # -------------------------------------------------
    for path in [media.file_path, media.thumbnail_path]:
        if path:
            fs_path = path.lstrip("/").replace("/", os.sep)
            try:
                os.remove(fs_path)
            except Exception:
                pass

    ext = os.path.splitext(file.filename)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".mkv", ".wmv"}

    if not is_video and ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    base_folder = (
        f"media/users/{current_user.id}/profiles/{gallery.event.profile_id}/"
        f"events/{gallery.event_id}/galleries/{gallery_id}"
    )
    orig_folder = os.path.join(base_folder, "original")
    os.makedirs(orig_folder, exist_ok=True)

    # -------------------------------------------------
    # ALWAYS CREATE A NEW FILE
    # -------------------------------------------------
    file.file.seek(0)
    filename = f"{uuid.uuid4()}{ext}"
    full_path = os.path.join(orig_folder, filename)

    with open(full_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    file_url = "/" + full_path.replace(os.sep, "/")
    file_size = os.path.getsize(full_path)

    media.file_path = file_url
    media.file_type = "video" if is_video else "image"
    media.file_size = file_size
    media.thumbnail_path = None
    media.duration_seconds = None
    media.uploaded_at = datetime.utcnow()  # 🔥 REQUIRED

    # -------------------------------------------------
    # VIDEO THUMB + DURATION
    # -------------------------------------------------
    if is_video:
        thumb_folder = os.path.join(base_folder, "thumbnails")
        os.makedirs(thumb_folder, exist_ok=True)

        thumb_path = os.path.join(
            thumb_folder, f"thumb_{uuid.uuid4()}.jpg"
        )
        if generate_video_thumbnail(full_path, thumb_path):
            media.thumbnail_path = "/" + thumb_path.replace(os.sep, "/")

        secs = get_video_duration_seconds(full_path)
        media.duration_seconds = secs if secs and secs > 0 else None

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
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, g.event_id, db):
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
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, g.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    m = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not m or m.gallery_id != gallery_id:
        raise HTTPException(status_code=404, detail="Media not found")

    if g.main_media_id == media_id:
        g.main_media_id = None
    
    db.commit()

    for p in [m.file_path, m.thumbnail_path, m.voice_note_path]:
        if p:
            fs = p.lstrip("/").replace("/", os.sep)
            if os.path.exists(fs):
                try:
                    os.remove(fs)
                except:
                    pass

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
    current_user: User = Depends(get_current_user),
):
    g = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, g.event_id, db):
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

from app.storage import save_voice_file

@router.post("/{gallery_id}/voice-note")
async def upload_gallery_voice_note(
    gallery_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Load gallery
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    # 2. Permission check
    if not owns_event(current_user.id, gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    event = gallery.event

    # 3. Save audio using central method
    url = save_voice_file(
        user_id=str(current_user.id),
        profile_id=str(event.profile_id),
        event_id=event.id,
        gallery_id=gallery_id,
        scope="gallery",
        upload=file,
    )

    # 4. Delete old voice note if present
    if gallery.voice_note_path:
        old = gallery.voice_note_path.lstrip("/").replace("/", os.sep)
        if os.path.exists(old):
            try: os.remove(old)
            except: pass

    # 5. Save new path
    gallery.voice_note_path = url
    db.commit()
    db.refresh(gallery)

    return {"path": url, "success": True}


# =====================================================================
# DELETE GALLERY-LEVEL VOICE NOTE  (UNIFIED)
# =====================================================================

@router.delete("/{gallery_id}/voice-note")
async def delete_gallery_voice_note(
    gallery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gallery = db.query(EventGallery).filter(EventGallery.id == gallery_id).first()
    if not gallery:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not owns_event(current_user.id, gallery.event_id, db):
        raise HTTPException(status_code=403, detail="Not authorised")

    # delete file
    if gallery.voice_note_path:
        fs = gallery.voice_note_path.lstrip("/").replace("/", os.sep)
        if os.path.exists(fs):
            try: os.remove(fs)
            except: pass

    gallery.voice_note_path = None
    db.commit()

    return {"message": "Gallery voice note deleted", "success": True}
