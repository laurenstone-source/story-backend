from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy.orm import joinedload
from app.models.family_group import FamilyGroup


from app.database import get_db
from app.auth.supabase_auth import get_current_user
from app.core.profile_access import get_current_user_profile
from app.models.family_group_member import FamilyGroupMember
from app.models.family_group_post import FamilyGroupPost
from app.models.media import MediaFile
from app.schemas.family_group_post_schema import (
    GroupPostCreate,
    GroupPostOut,
)

router = APIRouter(prefix="/family-groups", tags=["Group Posts"])


# --------------------------------------------------
# HELPERS
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


def serialize_post(
    post: FamilyGroupPost,
    me,
    member: FamilyGroupMember,
    db: Session,
):
    # --------------------------------------------------
    # Resolve author profile picture properly
    # --------------------------------------------------
    profile_image_url = None

    if post.author and post.author.profile_picture_media_id:
        media = (
            db.query(MediaFile)
            .filter(MediaFile.id == post.author.profile_picture_media_id)
            .first()
        )
        if media:
            profile_image_url = media.file_path

    # --------------------------------------------------
    # Count visible comments safely
    # --------------------------------------------------
    visible_comment_count = len([
        c for c in post.comments
        if c.status == "visible"
    ])

    return GroupPostOut(
        id=post.id,
        group_id=post.group_id,
        author_profile_id=post.author_profile_id,

        author_name=post.author.full_name if post.author else None,
        author_profile_picture=profile_image_url,

        content_text=post.content_text,
        status=post.status,

        created_at=post.created_at,
        updated_at=post.updated_at,
        last_activity_at=post.last_activity_at,

        comment_count=visible_comment_count,

        media_url=(post.media.file_path if post.media else None),
        media_type=(post.media.media_type if post.media else None),

        is_hidden=post.status != "visible",

        can_edit=post.author_profile_id == me.id,
        can_delete=(
            post.author_profile_id == me.id
            or member.role == "admin"
        ),
    )

# --------------------------------------------------
# LIST POSTS
# --------------------------------------------------

@router.get("/{group_id}/posts", response_model=list[GroupPostOut])
def list_group_posts(
    group_id: str,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])
    member = require_member(db, group_id, me.id)

    posts = (
        db.query(FamilyGroupPost)
        .options(
            joinedload(FamilyGroupPost.media),
            joinedload(FamilyGroupPost.comments),
            joinedload(FamilyGroupPost.author),  # ✅ ADD THIS
        )
        .filter(
            FamilyGroupPost.group_id == group_id,
            FamilyGroupPost.status != "hidden_by_system",
            FamilyGroupPost.status != "deleted_by_author",
        )
        # ✅ ORDER BY ACTIVITY, NOT CREATION
        .order_by(FamilyGroupPost.last_activity_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [serialize_post(p, me, member, db) for p in posts]

# --------------------------------------------------
# CREATE POST
# --------------------------------------------------

@router.post("/{group_id}/posts", response_model=GroupPostOut)
def create_post(
    group_id: str,
    payload: GroupPostCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Family group not found")

    if group.is_archived:
        raise HTTPException(400, "Cannot post in an archived group")

    member = require_member(db, group_id, me.id)

    post = FamilyGroupPost(
        group_id=group_id,
        author_profile_id=me.id,
        content_text=payload.content_text,
        status="visible",
        last_activity_at=datetime.utcnow(),
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    return serialize_post(post, me, member)


# --------------------------------------------------
# EDIT OWN POST
# --------------------------------------------------
@router.put("/posts/{post_id}")
def edit_post(
    post_id: str,
    payload: GroupPostCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id,
        FamilyGroupPost.status == "visible",
    ).first()

    if not post:
        raise HTTPException(404, "Post not found")

    group = db.query(FamilyGroup).filter(FamilyGroup.id == post.group_id).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot edit posts in an archived group")

    if post.author_profile_id != me.id:
        raise HTTPException(403, "Cannot edit this post")

    post.content_text = payload.content_text
    db.commit()

    return {"status": "updated"}

# --------------------------------------------------
# DELETE POST
# --------------------------------------------------

@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.family_group_post_media import FamilyGroupPostMedia
    from app.storage import delete_file

    me = get_current_user_profile(db, current_user["sub"])

    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id
    ).first()

    if not post:
        raise HTTPException(404, "Post not found")

    group = db.query(FamilyGroup).filter(
        FamilyGroup.id == post.group_id
    ).first()

    if group and group.is_archived:
        raise HTTPException(400, "Cannot delete posts from an archived group")

    member = require_member(db, post.group_id, me.id)

    if not (is_admin(member) or post.author_profile_id == me.id):
        raise HTTPException(403, "Cannot delete this post")

    # -------------------------------------------------
    # ✅ DELETE MEDIA FILE + MEDIA RECORD
    # -------------------------------------------------
    media = db.query(FamilyGroupPostMedia).filter(
        FamilyGroupPostMedia.post_id == post.id
    ).first()

    if media:
        if media.media_path:
            delete_file(media.media_path)

        db.delete(media)

    # -------------------------------------------------
    # Soft-delete the post
    # -------------------------------------------------
    post.status = "deleted_by_author"
    db.commit()

    return {"status": "deleted"}

# --------------------------------------------------
# HIDE POST (ADMIN)
# --------------------------------------------------

@router.post("/posts/{post_id}/hide")
def hide_post(
    post_id: str,
    reason: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id
    ).first()

    if not post:
        raise HTTPException(404, "Post not found")

    group = db.query(FamilyGroup).filter(FamilyGroup.id == post.group_id).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot moderate posts in an archived group")

    member = require_member(db, post.group_id, me.id)
    if not is_admin(member):
        raise HTTPException(403, "Admin only")

    post.status = "hidden_by_admin"
    post.hidden_reason = reason
    post.hidden_by_profile_id = me.id
    post.hidden_at = datetime.utcnow()

    db.commit()
    return {"status": "hidden"}
# --------------------------------------------------
# UNHIDE POST (ADMIN)
# --------------------------------------------------

@router.post("/posts/{post_id}/unhide")
def unhide_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    post = db.query(FamilyGroupPost).filter(
        FamilyGroupPost.id == post_id
    ).first()

    if not post:
        raise HTTPException(404, "Post not found")

    group = db.query(FamilyGroup).filter(FamilyGroup.id == post.group_id).first()
    if group and group.is_archived:
        raise HTTPException(400, "Cannot moderate posts in an archived group")

    member = require_member(db, post.group_id, me.id)
    if not is_admin(member):
        raise HTTPException(403, "Admin only")

    post.status = "visible"
    post.hidden_reason = None
    post.hidden_by_profile_id = None
    post.hidden_at = None

    db.commit()
    return {"status": "unhidden"}
