import uuid
from typing import Literal
import os
import shutil
from fastapi import UploadFile
from pathlib import Path
from app.config import settings




MAX_TOTAL_STORAGE = 1 * 1024 * 1024 * 1024   # 1GB
MAX_IMAGE_SIZE = 5 * 1024 * 1024             # 5MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024            # 50MB


# ---------------------------------------------------------
# Root: /media/{user_id}/
# ---------------------------------------------------------
def user_root(user_id: str) -> Path:
    root = Path(settings.LOCAL_MEDIA_PATH) / user_id
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------
# Nested folder helpers
# ---------------------------------------------------------
def event_main_folder(user_id: str, profile_id: str, event_id: int) -> Path:
    path = (
        Path(settings.LOCAL_MEDIA_PATH)
        / "users" / user_id
        / "profiles" / str(profile_id)
        / "events" / str(event_id)
        / "main"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def gallery_folder(user_id: str, profile_id: str, event_id: int, gallery_id: int) -> Path:
    path = (
        Path(settings.LOCAL_MEDIA_PATH)
        / user_id
        / str(profile_id)
        / "events"
        / str(event_id)
        / "galleries"
        / str(gallery_id)
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------
# Storage usage
# ---------------------------------------------------------
def get_user_storage_used(user_id: str):
    folder = Path(settings.LOCAL_MEDIA_PATH) / user_id
    if not folder.exists():
        return 0
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


# ---------------------------------------------------------
# File size validation
# ---------------------------------------------------------
def validate_file_size(file: UploadFile):
    # FastAPI UploadFile has no size attribute
    # We must read the stream length safely

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)

    if file.content_type and file.content_type.startswith("image/"):
        if size > MAX_IMAGE_SIZE:
            return False, "Image too large (max 5MB)."

    if file.content_type and file.content_type.startswith("video/"):
        if size > MAX_VIDEO_SIZE:
            return False, "Video too large (max 50MB)."

    return True, None


# ---------------------------------------------------------
# Generic save helper
# ---------------------------------------------------------
def save_file_to_folder(folder: Path | str, file: UploadFile, new_filename: str = None) -> str:

    if isinstance(folder, str):
        folder = Path(folder)

    folder.mkdir(parents=True, exist_ok=True)

    filename = new_filename if new_filename else file.filename
    file_path = folder / filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    rel = file_path.relative_to(settings.LOCAL_MEDIA_PATH)
    return f"/media/{rel}".replace("\\", "/")


# ---------------------------------------------------------
# AUDIO SAVE: profile, event, gallery, media
# ---------------------------------------------------------
def save_voice_file(
    *,
    user_id: str,
    profile_id: str,
    scope: Literal["profile", "event", "gallery", "media"],
    upload: UploadFile,
    event_id: int | None = None,
    gallery_id: int | None = None,
    media_id: int | None = None,
) -> str:
    """
    Saves a voice note in the correct folder based on scope.
    Supports:
      - profile-level
      - event-level
      - gallery-level
      - media-level (NEW)
    """

    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in [".m4a", ".aac", ".mp3", ".wav"]:
        ext = ".m4a"

    filename = f"voice_{uuid.uuid4()}{ext}"

    # --------------------------
    # Profile-level
    # --------------------------
    if scope == "profile":
        folder = (
            Path(settings.LOCAL_MEDIA_PATH)
            / "users" / user_id
            / "profiles" / str(profile_id)
            / "voice"
        )

    # --------------------------
    # Event-level
    # --------------------------
    elif scope == "event":
        folder = (
            Path(settings.LOCAL_MEDIA_PATH)
            / "users" / user_id
            / "profiles" / str(profile_id)
            / "events" / str(event_id)
            / "voice"
        )

    # --------------------------
    # Gallery-level
    # --------------------------
    elif scope == "gallery":
        folder = (
            Path(settings.LOCAL_MEDIA_PATH)
            / "users" / user_id
            / "profiles" / str(profile_id)
            / "events" / str(event_id)
            / "galleries" / str(gallery_id)
            / "voice"
        )

    # --------------------------
    # MEDIA-level (NEW)
    # --------------------------
    elif scope == "media":
        folder = (
            Path(settings.LOCAL_MEDIA_PATH)
            / "users" / user_id
            / "profiles" / str(profile_id)
            / "events" / str(event_id)
            / "galleries" / str(gallery_id)
            / "media"
            / str(media_id)
            / "voice"
        )

    else:
        raise ValueError("Invalid scope for save_voice_file")

    # Save and return web URL
    url = save_file_to_folder(folder, upload, filename)
    return url

    # --------------------------
    # Group
    # --------------------------

def group_image_folder(user_id: str, profile_id: str, group_id: str) -> Path:
    path = (
        Path(settings.LOCAL_MEDIA_PATH)
        / "users"
        / user_id
        / "profiles"
        / str(profile_id)
        / "groups"
        / str(group_id)
        / "image"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path
# ---------------------------------------------------------
# DELETE FILE SAFELY (local now, bucket later)
# ---------------------------------------------------------
def delete_file(path: str):
    if not path:
        return

    fs_path = path.lstrip("/").replace("/", os.sep)

    if os.path.exists(fs_path):
        try:
            os.remove(fs_path)
        except:
            pass

