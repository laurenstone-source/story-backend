# app/routers/family_group_post_media_router.py

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.core.profile_access import get_current_user_profile

from app.models.user import User
from app.models.family_group_post import FamilyGroupPost
from app.models.family_group_member import FamilyGroupMember
from app.models.family_group_post_media import FamilyGroupPostMedia

from app.storage import validate_file_size, delete_file, save_file
media_url = save_file(folder, file, filename)

router = APIRouter(prefix="/family-groups", tags=["Group Post Media"])


def require_member(db: Session, group_id: str, profile_id: str) -> FamilyGroupMember:
    m = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group_id,
        FamilyGroupMember.profile_id == profile_id,
    ).first()
    if not m:
        raise HTTPException(403, "Not a group member")
    return m


def _detect_media_type(file: UploadFile) -> str:
    ct = (file.content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"

    name = (file.filename or "").lower()
    if name.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "image"
    if name.endswith((".mp4", ".mov", ".webm")):
        return "video"

    raise HTTPException(400, "Only image/video supported")


def _post_media_folder(user_id: str, profile_id: str, group_id: str, post_id: str) -> str:
    return (
        f"media/users/{user_id}/profiles/{profile_id}"
        f"/family-groups/{group_id}/posts/{post_id}/media"
    )


@router.post("/posts/{post_id}/media")
def upload_post_media(
    post_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.storage import save_file, delete_file

    me = get_current_user_profile(db, current_user.id)

    # -------------------------------------------------
    # Load post
    # -------------------------------------------------
    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id
    ).first()
    if not post:
        raise HTTPException(404, "Post not found")

    require_member(db, post.group_id, me.id)

    # Only author can upload media
    if post.author_profile_id != me.id:
        raise HTTPException(403, "Only the author can add media")

    if post.status != "visible":
        raise HTTPException(400, "Cannot add media to hidden/deleted post")
     # -------------------------------------------------
     # Validate file size
     # -------------------------------------------------
     ok, err = validate_file_size(file, max_mb=5)
     if not ok:
     raise HTTPException(status_code=413, detail=err)

    # -------------------------------------------------
    # Detect media type
    # -------------------------------------------------
    media_type = _detect_media_type(file)

    # -------------------------------------------------
    # Folder path
    # -------------------------------------------------
    folder = (
        f"users/{current_user.id}/profiles/{me.id}"
        f"/family-groups/{post.group_id}/posts/{post.id}/media"
    )

    # -------------------------------------------------
    # Filename
    # -------------------------------------------------
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext:
        ext = ".jpg" if media_type == "image" else ".mp4"

    filename = f"post_{uuid.uuid4()}{ext}"

    # -------------------------------------------------
    # Replace existing media if present
    # -------------------------------------------------
    existing = db.query(FamilyGroupPostMedia).filter(
        FamilyGroupPostMedia.post_id == post.id
    ).first()

    if existing and existing.media_path:
        delete_file(existing.media_path)

    # -------------------------------------------------
    # Upload new file
    # -------------------------------------------------
    media_url = save_file(folder, file, filename)

    # -------------------------------------------------
    # Persist DB
    # -------------------------------------------------
    if existing:
        existing.media_path = media_url
        existing.media_type = media_type
    else:
        db.add(
            FamilyGroupPostMedia(
                post_id=post.id,
                media_path=media_url,
                media_type=media_type,
            )
        )

    db.commit()

    return {
        "status": "ok",
        "media_path": media_url,
        "media_type": media_type,
        "success": True,
    }