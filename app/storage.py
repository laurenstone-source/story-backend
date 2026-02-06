import uuid
import os
import shutil
from pathlib import Path
from typing import Literal

from fastapi import UploadFile
from app.config import settings

# ==========================================================
# SUPABASE CLIENT
# ==========================================================
if settings.STORAGE_BACKEND == "supabase":
    from app.supabase_client import supabase


# ==========================================================
# LIMITS
# ==========================================================
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024


# ==========================================================
# VALIDATE FILE SIZE
# ==========================================================
def validate_file_size(file: UploadFile):
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


# ==========================================================
# EXTRACT SUPABASE STORAGE KEY
# ==========================================================
def extract_storage_key(url_or_path: str) -> str:
    """
    Converts Supabase public URL → storage key.
    """

    if not url_or_path:
        return ""

    if url_or_path.startswith("http"):
        marker = f"/storage/v1/object/public/{settings.SUPABASE_BUCKET}/"
        if marker in url_or_path:
            return url_or_path.split(marker)[1]

    return url_or_path.strip("/")


def save_file(folder: str, file: UploadFile, filename: str | None = None) -> str:
    folder = folder.strip("/")

    if not filename:
        filename = f"{uuid.uuid4()}_{file.filename}"

    # -----------------------------
    # LOCAL STORAGE
    # -----------------------------
    if settings.STORAGE_BACKEND == "local":
        folder_path = Path(settings.LOCAL_MEDIA_PATH) / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        file_path = folder_path / filename

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        rel = file_path.relative_to(settings.LOCAL_MEDIA_PATH)
        return f"/media/{rel}".replace("\\", "/")

    # -----------------------------
    # SUPABASE STORAGE
    # -----------------------------
    elif settings.STORAGE_BACKEND == "supabase":
        storage_key = f"{folder}/{filename}"

        file.file.seek(0)
        contents = file.file.read()

        if not contents:
            raise RuntimeError("File is empty – nothing to upload")

        res = supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
            storage_key,
            contents,
            {
                "content-type": file.content_type or "application/octet-stream",
                "upsert": True,
            },
        )

        if not res:
            raise RuntimeError("Supabase upload failed (no response)")

        print("Supabase upload OK:", storage_key)

        return supabase.storage.from_(settings.SUPABASE_BUCKET).get_public_url(
            storage_key
        )

    else:
        raise ValueError("Invalid STORAGE_BACKEND")

# ==========================================================
# DELETE FILE (LOCAL or SUPABASE)
# ==========================================================
def delete_file(path: str):
    if not path:
        return

    # -----------------------------
    # LOCAL DELETE
    # -----------------------------
    if settings.STORAGE_BACKEND == "local":
        fs_path = path.lstrip("/").replace("/", os.sep)
        if os.path.exists(fs_path):
            try:
                os.remove(fs_path)
            except Exception:
                pass

    # -----------------------------
    # SUPABASE DELETE
    # -----------------------------
    elif settings.STORAGE_BACKEND == "supabase":
        key = extract_storage_key(path)
        try:
            supabase.storage.from_(settings.SUPABASE_BUCKET).remove([key])
            print("Supabase delete OK:", key)
        except Exception as e:
            print("Supabase delete failed:", e)
# ==========================================================
# VOICE NOTE SAVE
# ==========================================================
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

    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in [".m4a", ".aac", ".mp3", ".wav"]:
        ext = ".m4a"

    filename = f"voice_{uuid.uuid4()}{ext}"

    # Folder by scope
    if scope == "profile":
        folder = f"users/{user_id}/profiles/{profile_id}/voice"

    elif scope == "event":
        folder = f"users/{user_id}/profiles/{profile_id}/events/{event_id}/voice"

    elif scope == "gallery":
        folder = f"users/{user_id}/profiles/{profile_id}/events/{event_id}/galleries/{gallery_id}/voice"

    elif scope == "media":
        folder = f"users/{user_id}/profiles/{profile_id}/events/{event_id}/galleries/{gallery_id}/media/{media_id}/voice"

    else:
        raise ValueError("Invalid scope")

    return save_file(folder, upload, filename)


# ==========================================================
# GROUP IMAGE SAVE
# ==========================================================
def save_group_image(user_id: str, profile_id: str, group_id: str, upload: UploadFile):

    filename = f"group_{uuid.uuid4()}.jpg"
    folder = f"users/{user_id}/profiles/{profile_id}/groups/{group_id}/image"

    return save_file(folder, upload, filename)
