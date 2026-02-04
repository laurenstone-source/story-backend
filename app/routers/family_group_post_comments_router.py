# app/routers/family_group_post_comments_router.py
from sqlalchemy.orm import joinedload

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.auth import get_current_user
from app.core.profile_access import get_current_user_profile

from app.models.family_group import FamilyGroup
from app.models.family_group_member import FamilyGroupMember
from app.models.family_group_post import FamilyGroupPost
from app.models.family_group_post_comment import FamilyGroupPostComment

from app.schemas.family_group_post_comment_schema import (
    GroupPostCommentCreate,
    GroupPostCommentOut,
)

router = APIRouter(prefix="/family-groups", tags=["Group Post Comments"])


# --------------------------------------------------
# HELPERS (IDENTICAL TO POSTS)
# --------------------------------------------------

def require_member(db, group_id, profile_id):
    member = (
        db.query(FamilyGroupMember)
        .filter(
            FamilyGroupMember.group_id == group_id,
            FamilyGroupMember.profile_id == profile_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(403, "Not a group member")
    return member


def is_admin(member: FamilyGroupMember) -> bool:
    return member.role == "admin"

def _detect_media_type(file: UploadFile) -> str:
    # 1. Try content-type first
    ct = (file.content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"

    # 2. Fallback to extension
    name = (file.filename or "").lower()
    if name.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "image"
    if name.endswith((".mp4", ".mov", ".webm")):
        return "video"

    raise HTTPException(400, "Only image/video supported")

def serialize_comment(
    comment: FamilyGroupPostComment,
    me,
    member: FamilyGroupMember,
):
    return GroupPostCommentOut(
        id=comment.id,
        post_id=comment.post_id,
        author_profile_id=comment.author_profile_id,

        author_name=comment.author.full_name if comment.author else None,
        author_profile_picture=(
            comment.author.profile_picture.file_path
            if comment.author and comment.author.profile_picture
            else None
        ),

        content_text=comment.content_text,
        status=comment.status,

        created_at=comment.created_at,
        updated_at=comment.updated_at,

        # 👇 MEDIA (SAFE)
        media_url=(
            comment.media.media_path
            if comment.media
            else None
        ),
        media_type=(
            comment.media.media_type
            if comment.media
            else None
        ),

        is_hidden=comment.status != "visible",

        can_edit=comment.author_profile_id == me.id,
        can_delete=(
            comment.author_profile_id == me.id
            or member.role == "admin"
        ),
    )

# --------------------------------------------------
# LIST COMMENTS (NESTED UNDER POST)
# --------------------------------------------------

@router.get(
    "/posts/{post_id}/comments",
    response_model=list[GroupPostCommentOut],
)
def list_comments(
    post_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id
    ).first()
    if not post:
        raise HTTPException(404, "Post not found")

    member = require_member(db, post.group_id, me.id)

    query = (
    db.query(FamilyGroupPostComment)
    .options(joinedload(FamilyGroupPostComment.media))  # ✅ IMPORTANT
    .filter(
        FamilyGroupPostComment.post_id == post_id,
        FamilyGroupPostComment.status != "hidden_by_system",
        FamilyGroupPostComment.status != "deleted_by_author",
    )
)



    # Non-admins only see visible comments
    if member.role != "admin":
        query = query.filter(
            FamilyGroupPostComment.status == "visible"
        )

    comments = query.order_by(
        FamilyGroupPostComment.created_at.asc()
    ).all()

    # ✅ SERIALIZE (THIS FIXES THE ERROR)
    return [
        serialize_comment(c, me, member)
        for c in comments
    ]




# --------------------------------------------------
# CREATE COMMENT
# --------------------------------------------------

@router.post(
    "/posts/{post_id}/comments",
    response_model=GroupPostCommentOut,
)
def create_comment(
    post_id: str,
    payload: GroupPostCommentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id,
        FamilyGroupPost.status == "visible",
    ).first()
    if not post:
        raise HTTPException(404, "Post not found")

    group = db.query(FamilyGroup).filter(
        FamilyGroup.id == post.group_id
    ).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot comment in an archived group")

    member = require_member(db, post.group_id, me.id)

    comment = FamilyGroupPostComment(
        post_id=post_id,
        author_profile_id=me.id,
        content_text=payload.content_text,
        status="visible",
    )

    db.add(comment)

    # ✅ bump post activity
    post.last_activity_at = datetime.utcnow()

    db.commit()
    db.refresh(comment)

    return serialize_comment(comment, me, member)



# --------------------------------------------------
# EDIT OWN COMMENT
# --------------------------------------------------

@router.put("/comments/{comment_id}")
def edit_comment(
    comment_id: str,
    payload: GroupPostCommentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    comment = db.query(FamilyGroupPostComment).filter(
        FamilyGroupPostComment.id == comment_id,
        FamilyGroupPostComment.status == "visible",
    ).first()
    if not comment:
        raise HTTPException(404, "Comment not found")

    post = comment.post
    group = db.query(FamilyGroup).filter(
        FamilyGroup.id == post.group_id
    ).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot edit comments in an archived group")

    member = require_member(db, post.group_id, me.id)

    if comment.author_profile_id != me.id:
        raise HTTPException(403, "Cannot edit this comment")

    comment.content_text = payload.content_text
    db.commit()

    return {"status": "updated"}


# --------------------------------------------------
# DELETE COMMENT (AUTHOR OR ADMIN)
# --------------------------------------------------

@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.family_group_post_comment_media import (
        FamilyGroupPostCommentMedia
    )
    from app.storage import delete_file

    me = get_current_user_profile(db, current_user.id)

    comment = db.query(FamilyGroupPostComment).filter(
        FamilyGroupPostComment.id == comment_id
    ).first()

    if not comment:
        raise HTTPException(404, "Comment not found")

    post = comment.post

    group = db.query(FamilyGroup).filter(
        FamilyGroup.id == post.group_id
    ).first()

    if group and group.is_archived:
        raise HTTPException(
            400,
            "Cannot delete comments from an archived group"
        )

    member = require_member(db, post.group_id, me.id)

    # Author OR admin can delete
    if not (is_admin(member) or comment.author_profile_id == me.id):
        raise HTTPException(403, "Cannot delete this comment")

    # -------------------------------------------------
    # ✅ DELETE COMMENT MEDIA FILE + DB RECORD
    # -------------------------------------------------
    media = db.query(FamilyGroupPostCommentMedia).filter(
        FamilyGroupPostCommentMedia.comment_id == comment.id
    ).first()

    if media:
        if media.media_path:
            delete_file(media.media_path)

        db.delete(media)

    # -------------------------------------------------
    # Soft delete comment
    # -------------------------------------------------
    comment.status = "deleted_by_author"
    db.commit()

    return {"status": "deleted"}

# --------------------------------------------------
# HIDE COMMENT (ADMIN)
# --------------------------------------------------

@router.post("/comments/{comment_id}/hide")
def hide_comment(
    comment_id: str,
    reason: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    comment = db.query(FamilyGroupPostComment).filter(
        FamilyGroupPostComment.id == comment_id
    ).first()
    if not comment:
        raise HTTPException(404, "Comment not found")

    post = comment.post
    group = db.query(FamilyGroup).filter(
        FamilyGroup.id == post.group_id
    ).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot moderate comments in an archived group")

    member = require_member(db, post.group_id, me.id)

    if not is_admin(member):
        raise HTTPException(403, "Admin only")

    comment.status = "hidden_by_admin"
    comment.hidden_reason = reason
    comment.hidden_by_profile_id = me.id
    comment.hidden_at = datetime.utcnow()

    db.commit()
    return {"status": "hidden"}



# --------------------------------------------------
# UNHIDE COMMENT (ADMIN)
# --------------------------------------------------

@router.post("/comments/{comment_id}/unhide")
def unhide_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    comment = db.query(FamilyGroupPostComment).filter(
        FamilyGroupPostComment.id == comment_id
    ).first()
    if not comment:
        raise HTTPException(404, "Comment not found")

    post = comment.post
    group = db.query(FamilyGroup).filter(
        FamilyGroup.id == post.group_id
    ).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot moderate comments in an archived group")

    member = require_member(db, post.group_id, me.id)

    if not is_admin(member):
        raise HTTPException(403, "Admin only")

    comment.status = "visible"
    comment.hidden_reason = None
    comment.hidden_by_profile_id = None
    comment.hidden_at = None

    db.commit()
    return {"status": "unhidden"}
