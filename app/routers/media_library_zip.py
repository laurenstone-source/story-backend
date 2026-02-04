# app/routers/media_library_zip_router.py

import os
import zipfile
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.media import MediaFile

from app.models.profile import Profile
from app.models.event_gallery import EventGallery
from app.models.timeline_event import TimelineEvent


router = APIRouter(prefix="/media-library", tags=["Media Library ZIP"])


# ==========================================================
# SAFE NAME
# ==========================================================
def safe_name(text: str) -> str:
    return (
        (text or "")
        .replace(":", "")
        .replace("–", "-")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
        .strip()
    )


# ==========================================================
# NICE LABEL
# ==========================================================
def get_folder_label(db: Session, media: MediaFile) -> str:

    if media.profile_id:
        profile = db.query(Profile).filter(Profile.id == media.profile_id).first()
        return f"Profile_{profile.full_name}" if profile else "Profile_Unknown"

    if media.gallery_id:
        gallery = db.query(EventGallery).filter(EventGallery.id == media.gallery_id).first()
        return f"Gallery_{gallery.title}" if gallery else "Gallery_Unknown"

    if media.event_id:
        event = db.query(TimelineEvent).filter(TimelineEvent.id == media.event_id).first()
        return f"Event_{event.title}" if event else "Event_Unknown"

    return "Other"


# ==========================================================
# DOWNLOAD ONE FILE FROM SUPABASE
# ==========================================================
def download_supabase_file(storage_path: str) -> str | None:
    """
    Downloads a file from Supabase Storage into a temp file.
    Returns the temp file path.
    """

    try:
        bucket = supabase_client.storage.from_("media")

        response = bucket.download(storage_path)

        if not response:
            return None

        # Save into temp file
        tmp_fd, tmp_path = tempfile.mkstemp()
        os.write(tmp_fd, response)
        os.close(tmp_fd)

        return tmp_path

    except Exception as e:
        print("SUPABASE DOWNLOAD ERROR:", e)
        return None


# ==========================================================
# DOWNLOAD ALL MEDIA ZIP
# ==========================================================
@router.get("/download-all")
def download_all_media_zip(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media_files = (
        db.query(MediaFile)
        .filter(MediaFile.user_id == current_user.id)
        .all()
    )

    if not media_files:
        raise HTTPException(status_code=404, detail="No media found")

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "all_media.zip")

    with zipfile.ZipFile(zip_path, "w") as zipf:

        for media in media_files:

            if not media.file_path:
                continue

            storage_key = media.file_path.lstrip("/")

            tmp_file = download_supabase_file(storage_key)
            if not tmp_file:
                continue

            folder = safe_name(get_folder_label(db, media))
            filename = os.path.basename(storage_key)

            zipf.write(
                tmp_file,
                arcname=f"{folder}/{filename}",
            )

            os.remove(tmp_file)

    return FileResponse(
        zip_path,
        filename="all_media.zip",
        media_type="application/zip",
    )


# ==========================================================
# DOWNLOAD ONE FOLDER ZIP
# ==========================================================
@router.get("/download-folder")
def download_folder_zip(
    scope: str = Query(...),   # profile / gallery / timeline
    id: str = Query(...),
    name: str = Query("folder"),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(MediaFile).filter(
        MediaFile.user_id == current_user.id
    )

    if scope == "profile":
        query = query.filter(MediaFile.profile_id == id)

    elif scope == "gallery":
        query = query.filter(MediaFile.gallery_id == int(id))

    elif scope == "timeline":
        query = query.filter(MediaFile.event_id == int(id))

    else:
        raise HTTPException(status_code=400, detail="Invalid scope")

    matched = query.all()

    if not matched:
        raise HTTPException(status_code=404, detail="No media found in folder")

    folder_name = safe_name(name)

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"{folder_name}.zip")

    with zipfile.ZipFile(zip_path, "w") as zipf:

        for media in matched:

            if not media.file_path:
                continue

            storage_key = media.file_path.lstrip("/")

            tmp_file = download_supabase_file(storage_key)
            if not tmp_file:
                continue

            filename = os.path.basename(storage_key)

            zipf.write(
                tmp_file,
                arcname=f"{folder_name}/{filename}",
            )

            os.remove(tmp_file)

    return FileResponse(
        zip_path,
        filename=f"{folder_name}.zip",
        media_type="application/zip",
    )
