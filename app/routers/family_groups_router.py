from app.database import get_db


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
from fastapi import UploadFile, File
import os
from app.routers.profile_router import attach_media_urls
from app.utils.urls import absolute_media_url
from app.database import SessionLocal
from app.auth.supabase_auth import get_current_user
from app.models.profile import Profile

from app.models.family_group import FamilyGroup
from app.models.family_group_member import FamilyGroupMember
from app.models.family_group_join_request import FamilyGroupJoinRequest
from app.models.family_invite import FamilyInvite
from app.models.family_person import FamilyPerson
from app.models.family_relationship import FamilyRelationship
from app.models.family_group_merge_request import FamilyGroupMergeRequest

from app.schemas.family_group_schema import (
    FamilyGroupCreate,
    FamilyGroupOut,
    FamilyGroupSearchOut,
    FamilyGroupDetailOut,
    FamilyGroupRename,  # 👈 THIS WAS MISSING
)

from app.schemas.family_group_merge_schema import (
    FamilyGroupMergeRequestCreate,
    GroupMergeRequestOut,
)

from app.core.profile_access import get_current_user_profile

router = APIRouter(prefix="/family-groups", tags=["Family Groups"])




# --------------------------------------------------
# DB
# --------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def require_member(db: Session, group_id: str, profile_id: str) -> FamilyGroupMember:
    member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group_id,
        FamilyGroupMember.profile_id == profile_id,
    ).first()

    if not member:
        raise HTTPException(403, "Not a member of this family group")

    return member


def require_admin(db: Session, group_id: str, profile_id: str) -> FamilyGroupMember:
    member = require_member(db, group_id, profile_id)
    if member.role != "admin":
        raise HTTPException(403, "Admin only")
    return member


def resolve_group(db: Session, group_id: str) -> FamilyGroup:
    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Family group not found")

    # For reads, redirect merged groups
    if group.is_archived and group.merged_into_group_id:
        target = db.query(FamilyGroup).filter(FamilyGroup.id == group.merged_into_group_id).first()
        if target:
            return target

    return group# ---------------------------------------------------------
# GROUP IMAGE
# ---------------------------------------------------------
@router.put("/{group_id}/image")
def upload_group_image(
    group_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.storage import save_file, delete_file

    me = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)

    if group.is_archived:
        raise HTTPException(400, "Cannot modify an archived group")

    require_admin(db, group.id, me.id)

    # -------------------------------------------------
    # Validate extension only
    # -------------------------------------------------
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    # -------------------------------------------------
    # Delete old image
    # -------------------------------------------------
    if group.group_image_url:
        delete_file(group.group_image_url)

    # -------------------------------------------------
    # Upload new image
    # -------------------------------------------------
    folder = f"users/{current_user['sub']}/profiles/{me.id}/groups/{group.id}"
    filename = f"group_{uuid.uuid4()}{ext}"

    url = save_file(folder, file, filename)

    group.group_image_url = url
    db.commit()
    db.refresh(group)

    return {"image_url": url, "success": True}


# --------------------------------------------------
# CREATE FAMILY GROUP
# --------------------------------------------------
@router.post("", response_model=FamilyGroupOut)
def create_family_group(
    payload: FamilyGroupCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = get_current_user_profile(db, current_user["sub"])

    group = FamilyGroup(
        id=str(uuid.uuid4()),
        name=payload.name,
        created_by_profile_id=profile.id,
        created_at=datetime.utcnow(),
    )
    db.add(group)
    db.add(
        FamilyGroupMember(
            group_id=group.id,
            profile_id=profile.id,
            role="admin",
        )
    )
    db.commit()
    db.refresh(group)
    return group

# --------------------------------------------------
# SEARCH GROUPS (for discovery + merge)
# --------------------------------------------------
@router.get("/search", response_model=list[FamilyGroupSearchOut])
def search_groups(
    query: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = (query or "").strip()
    if len(q) < 2:
        return []

    groups = (
        db.query(FamilyGroup)
        .filter(FamilyGroup.is_archived == False)
        .filter(FamilyGroup.name.ilike(f"%{q}%"))
        .order_by(FamilyGroup.name.asc())
        .limit(25)
        .all()
    )

    return [
        {"id": g.id, "name": g.name, "group_image_url": g.group_image_url}
        for g in groups
    ]
# --------------------------------------------------
# RENAME GROUP (ADMIN ONLY)
# --------------------------------------------------
@router.put("/{group_id}/rename")
def rename_family_group(
    group_id: str,
    payload: FamilyGroupRename,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])
    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Family group not found")

    if group.is_archived:
        raise HTTPException(400, "Cannot rename an archived group")

    require_admin(db, group.id, me.id)

    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(400, "Group name cannot be empty")

    group.name = new_name
    db.commit()

    return {"status": "renamed", "name": group.name}
# --------------------------------------------------
# DELETE / ARCHIVE GROUP (ADMIN ONLY)
# --------------------------------------------------
@router.delete("/{group_id}")
def delete_family_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)

    require_admin(db, group.id, me.id)

    if group.is_archived:
        return {"status": "already_archived"}

    group.is_archived = True
    group.archived_at = datetime.utcnow()
    db.commit()

    return {"status": "archived"}

# --------------------------------------------------
# LIST MY FAMILY GROUPS
# --------------------------------------------------
@router.get("/mine")
def my_family_groups(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    rows = (
        db.query(FamilyGroup, FamilyGroupMember)
        .join(FamilyGroupMember)
        .filter(FamilyGroupMember.profile_id == me.id)
        .filter(FamilyGroup.is_archived == False)
        .all()
    )

    out = []

    for group, member in rows:
        out.append(
            {
                "id": group.id,
                "name": group.name,
                "group_image_url": group.group_image_url,
                "my_role": member.role,  # ✅ THIS FIXES EVERYTHING
            }
        )

    return out

# --------------------------------------------------
# GET FAMILY GROUP DETAIL (MEMBERS)
# --------------------------------------------------
@router.get("/{group_id}", response_model=FamilyGroupDetailOut)
def get_family_group_detail(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)
    require_member(db, group.id, me.id)

    rows = (
        db.query(FamilyGroupMember, Profile)
        .join(Profile, Profile.id == FamilyGroupMember.profile_id)
        .filter(FamilyGroupMember.group_id == group.id)
        .all()
    )

    members_out = []
    my_role: str | None = None

    for member, profile in rows:
        urls = attach_media_urls(db, profile)
        image_url = urls.get("profile_picture_url")
        if image_url:
            image_url = absolute_media_url(image_url)

        members_out.append(
            {
                "profile_id": profile.id,
                "display_name": profile.full_name,
                "profile_image_url": image_url,
                "joined_at": member.joined_at,
                "role": member.role,
            }
        )

        if profile.id == me.id:
            my_role = member.role

    if my_role is None:
        raise HTTPException(status_code=500, detail="Membership state invalid")

    return {
        "id": group.id,
        "name": group.name,
        "created_by_profile_id": group.created_by_profile_id,
        "created_at": group.created_at,
        "is_archived": group.is_archived,
        "merged_into_group_id": group.merged_into_group_id,
        "group_image_url": group.group_image_url,
        "members": members_out,
        "my_role": my_role,
        "my_profile_id": me.id,
    }

# --------------------------------------------------
# REMOVE MEMBER FROM GROUP
# --------------------------------------------------
@router.post("/{group_id}/members/{profile_id}/remove")
def remove_group_member(
    group_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.models.family_group_post import FamilyGroupPost
    from app.models.family_group_post_comment import FamilyGroupPostComment

    admin = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)
    require_admin(db, group.id, admin.id)

    member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == profile_id,
    ).first()

    if not member:
        return {"status": "ok"}

    if member.role == "admin":
        admin_count = db.query(FamilyGroupMember).filter(
            FamilyGroupMember.group_id == group.id,
            FamilyGroupMember.role == "admin",
        ).count()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot remove the last admin")

    # 🔒 SYSTEM HIDE POSTS
    db.query(FamilyGroupPost).filter(
        FamilyGroupPost.group_id == group.id,
        FamilyGroupPost.author_profile_id == profile_id,
        FamilyGroupPost.status == "visible",
    ).update(
        {"status": "hidden_by_system"},
        synchronize_session=False,
    )
    db.query(FamilyGroupPostComment).filter(
    FamilyGroupPostComment.author_profile_id == profile_id,
    FamilyGroupPostComment.status == "visible",
).update(
    {
        "status": "hidden_by_system",
        
    },
    synchronize_session=False,
)
    db.delete(member)
    db.commit()

    return {"status": "ok"}
# --------------------------------------------------
# LEAVE GROUP
# --------------------------------------------------
@router.post("/{group_id}/leave")
def leave_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.models.family_group_post import FamilyGroupPost
    from app.models.family_group_post_comment import FamilyGroupPostComment

    me = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)

    member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == me.id,
    ).first()

    if not member:
        return {"status": "ok"}

    if member.role == "admin":
        admin_count = db.query(FamilyGroupMember).filter(
            FamilyGroupMember.group_id == group.id,
            FamilyGroupMember.role == "admin",
        ).count()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot leave as the last admin")

    # 🔒 SYSTEM HIDE POSTS
    db.query(FamilyGroupPost).filter(
        FamilyGroupPost.group_id == group.id,
        FamilyGroupPost.author_profile_id == me.id,
        FamilyGroupPost.status == "visible",
    ).update(
        {"status": "hidden_by_system"},
        synchronize_session=False,
    )
    db.query(FamilyGroupPostComment).filter(
    FamilyGroupPostComment.author_profile_id == me.id,
    FamilyGroupPostComment.status == "visible",
).update(
    {
        "status": "hidden_by_system",
        
    },
    synchronize_session=False,
)
    db.delete(member)
    db.commit()

    return {"status": "ok"}
# --------------------------------------------------
# GROUP MEMBER GOVERNANCE
# --------------------------------------------------

@router.post("/{group_id}/members/{profile_id}/make-admin")
def make_group_admin(
    group_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)
    require_admin(db, group.id, me.id)

    member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == profile_id,
    ).first()

    if not member:
        raise HTTPException(404, "Member not found")

    member.role = "admin"
    db.commit()
    return {"status": "ok"}


@router.post("/{group_id}/members/{profile_id}/make-member")
def make_group_member(
    group_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])
    group = resolve_group(db, group_id)
    require_admin(db, group.id, me.id)

    admins = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.role == "admin",
    ).all()

    if len(admins) <= 1 and any(a.profile_id == profile_id for a in admins):
        raise HTTPException(400, "Cannot demote last admin")

    member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == profile_id,
    ).first()

    if not member:
        raise HTTPException(404, "Member not found")

    member.role = "member"
    db.commit()
    return {"status": "ok"}
# --------------------------------------------------
# MY INCOMING GROUP INVITES
# --------------------------------------------------
@router.get("/invites/mine")
def my_group_invites(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    invites = (
        db.query(FamilyInvite, FamilyGroup)
        .join(FamilyGroup, FamilyGroup.id == FamilyInvite.group_id)
        .filter(
            FamilyInvite.invited_profile_id == me.id,
            FamilyInvite.status == "pending",
        )
        .order_by(FamilyInvite.created_at.desc())
        .all()
    )

    return [
        {
            "invite_id": invite.id,
            "group_id": group.id,
            "group_name": group.name,
            "group_image_url": group.group_image_url,
            "invited_by_profile_id": invite.invited_by_profile_id,
            "created_at": invite.created_at,
        }
        for invite, group in invites
    ]
# --------------------------------------------------
# LIST JOIN REQUESTS FOR A GROUP (ADMIN ONLY)
# --------------------------------------------------
@router.get("/{group_id}/join-requests")
def list_group_join_requests(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    group = resolve_group(db, group_id)

    # 🔐 Admin only
    require_admin(db, group.id, me.id)

    rows = (
        db.query(FamilyGroupJoinRequest, Profile)
        .join(Profile, Profile.id == FamilyGroupJoinRequest.profile_id)
        .filter(
            FamilyGroupJoinRequest.group_id == group.id,
            FamilyGroupJoinRequest.status == "pending",
        )
        .order_by(FamilyGroupJoinRequest.created_at.asc())
        .all()
    )

    out = []

    for req, profile in rows:
        urls = attach_media_urls(db, profile)

        image_url = urls.get("profile_picture_url")
        if image_url:
            image_url = absolute_media_url(image_url)

        out.append(
    {
        "request_id": req.id,
        "profile_id": profile.id,
        "profile_name": profile.full_name,
        "profile_image_url": image_url,
        "is_public": profile.is_public,
        "can_view": profile.is_public,  # admins can only view public here
        "created_at": req.created_at,
    }
)


    return out

# --------------------------------------------------
# REQUEST TO JOIN GROUP
# --------------------------------------------------
@router.post("/{group_id}/join-request")
def request_to_join_family_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Family group not found")

    if group.is_archived:
        raise HTTPException(400, "This group has been archived")

    profile = get_current_user_profile(db, current_user["sub"])

    exists = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == profile.id,
    ).first()
    if exists:
        return {"status": "already_member"}

    pending = db.query(FamilyGroupJoinRequest).filter(
        FamilyGroupJoinRequest.group_id == group.id,
        FamilyGroupJoinRequest.profile_id == profile.id,
        FamilyGroupJoinRequest.status == "pending",
    ).first()
    if pending:
        return {"status": "already_requested"}

    req = FamilyGroupJoinRequest(
        id=str(uuid.uuid4()),
        group_id=group.id,
        profile_id=profile.id,
        status="pending",
        created_at=datetime.utcnow(),
    )

    db.add(req)
    db.commit()

    return {"status": "requested"}


# --------------------------------------------------
# ACCEPT JOIN REQUEST
# --------------------------------------------------
@router.post("/join-requests/{request_id}/accept")
def accept_join_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.models.family_group_post import FamilyGroupPost
    from app.models.family_group_post_comment import FamilyGroupPostComment

    admin = get_current_user_profile(db, current_user["sub"])

    req = db.query(FamilyGroupJoinRequest).filter(
        FamilyGroupJoinRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(404, "Request not found")

    group = db.query(FamilyGroup).filter(FamilyGroup.id == req.group_id).first()
    if not group:
        raise HTTPException(404, "Family group not found")

    if group.is_archived:
        raise HTTPException(400, "Cannot accept join requests for archived groups")

    require_admin(db, group.id, admin.id)

    if req.status != "pending":
        return {"status": req.status}

    req.status = "accepted"

    existing_member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == req.profile_id,
    ).first()

    if not existing_member:
        db.add(
            FamilyGroupMember(
                group_id=group.id,
                profile_id=req.profile_id,
                role="member",
            )
        )

    # Restore posts/comments
    db.query(FamilyGroupPost).filter(
        FamilyGroupPost.group_id == group.id,
        FamilyGroupPost.author_profile_id == req.profile_id,
        FamilyGroupPost.status == "hidden_by_system",
    ).update({"status": "visible"}, synchronize_session=False)

    db.query(FamilyGroupPostComment).filter(
        FamilyGroupPostComment.author_profile_id == req.profile_id,
        FamilyGroupPostComment.status == "hidden_by_system",
    ).update({"status": "visible"}, synchronize_session=False)

    db.commit()
    return {"status": "accepted"}
# --------------------------------------------------
# DECLINE JOIN REQUEST
# --------------------------------------------------
@router.post("/join-requests/{request_id}/decline")
def decline_join_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = get_current_user_profile(db, current_user["sub"])

    req = db.query(FamilyGroupJoinRequest).filter(
        FamilyGroupJoinRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(404, "Request not found")

    group = resolve_group(db, req.group_id)
    require_admin(db, group.id, profile.id)

    req.status = "declined"
    db.commit()

    return {"status": "declined"}
# --------------------------------------------------
# CANCEL JOIN REQUEST
# --------------------------------------------------
@router.post("/join-requests/{request_id}/cancel")
def cancel_join_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    req = db.query(FamilyGroupJoinRequest).filter(
        FamilyGroupJoinRequest.id == request_id,
        FamilyGroupJoinRequest.profile_id == me.id,
        FamilyGroupJoinRequest.status == "pending",
    ).first()

    if not req:
        raise HTTPException(404, "Join request not found")

    req.status = "cancelled"
    db.commit()

    return {"status": "cancelled"}



# --------------------------------------------------
# INVITE PROFILE TO GROUP (ANY MEMBER)
# --------------------------------------------------
@router.post("/{group_id}/invite/{profile_id}", status_code=201)
def invite_to_group(
    group_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Family group not found")

    if group.is_archived:
        raise HTTPException(400, "Cannot invite users to an archived group")

    require_member(db, group.id, me.id)

    if profile_id == me.id:
        raise HTTPException(400, "You cannot invite yourself")

    target_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not target_profile:
        raise HTTPException(404, "Profile not found")

    existing_member = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.group_id == group.id,
        FamilyGroupMember.profile_id == profile_id,
    ).first()
    if existing_member:
        raise HTTPException(400, "Profile is already a member")

    existing_invite = db.query(FamilyInvite).filter(
        FamilyInvite.group_id == group.id,
        FamilyInvite.invited_profile_id == profile_id,
        FamilyInvite.status == "pending",
    ).first()
    if existing_invite:
        raise HTTPException(400, "Invite already sent")

    invite = FamilyInvite(
        id=str(uuid.uuid4()),
        group_id=group.id,
        invited_by_profile_id=me.id,
        invited_profile_id=profile_id,
        status="pending",
        created_at=datetime.utcnow(),
    )

    db.add(invite)
    db.commit()
    db.refresh(invite)

    return {"id": invite.id, "status": invite.status}
# --------------------------------------------------
# LIST PENDING INVITES (ANY MEMBER)
# --------------------------------------------------

@router.get("/{group_id}/invites")
def list_group_invites(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # --------------------------------------------------
    # WHO AM I
    # --------------------------------------------------
    me = get_current_user_profile(db, current_user["sub"])

    # --------------------------------------------------
    # LOAD GROUP + SECURITY CHECK
    # --------------------------------------------------
    group = resolve_group(db, group_id)

    # Any member can view
    require_member(db, group.id, me.id)

    # --------------------------------------------------
    # LOAD INVITES + PROFILE DATA
    # --------------------------------------------------
    rows = (
        db.query(FamilyInvite, Profile)
        .join(Profile, Profile.id == FamilyInvite.invited_profile_id)
        .filter(
            FamilyInvite.group_id == group.id,
            FamilyInvite.status == "pending",
        )
        .order_by(FamilyInvite.created_at.desc())
        .all()
    )

    invites_out = []

    for invite, profile in rows:
        urls = attach_media_urls(db, profile)

        image_url = urls.get("profile_picture_url")
        if image_url:
            image_url = absolute_media_url(image_url)

        invites_out.append(
    {
        "id": invite.id,
        "profile_id": profile.id,
        "profile_name": profile.full_name,
        "profile_image_url": image_url,
        "is_public": profile.is_public,
        "can_view": profile.is_public,
        "created_at": invite.created_at,
    }
)


    return invites_out

# --------------------------------------------------
# CANCEL GROUP INVITE (ANY MEMBER)
# --------------------------------------------------
@router.post("/invites/{invite_id}/cancel")
def cancel_group_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    invite = (
        db.query(FamilyInvite)
        .filter(
            FamilyInvite.id == invite_id,
            FamilyInvite.status == "pending",
        )
        .first()
    )
    if not invite:
        raise HTTPException(404, "Invite not found")

    group = resolve_group(db, invite.group_id)

    # Any group member can cancel
    require_member(db, group.id, me.id)

    invite.status = "cancelled"
    db.commit()

    return {"status": "cancelled"}

# --------------------------------------------------
# ACCEPT GROUP INVITE (INVITED USER)
# --------------------------------------------------
@router.post("/invites/{invite_id}/accept")
def accept_group_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.models.family_group_post import FamilyGroupPost
    from app.models.family_group_post_comment import FamilyGroupPostComment

    me = get_current_user_profile(db, current_user["sub"])

    invite = (
        db.query(FamilyInvite)
        .filter(
            FamilyInvite.id == invite_id,
            FamilyInvite.invited_profile_id == me.id,
            FamilyInvite.status == "pending",
        )
        .first()
    )
    if not invite:
        raise HTTPException(404, "Invite not found")

    existing = (
        db.query(FamilyGroupMember)
        .filter(
            FamilyGroupMember.group_id == invite.group_id,
            FamilyGroupMember.profile_id == me.id,
        )
        .first()
    )

    if not existing:
        db.add(
            FamilyGroupMember(
                group_id=invite.group_id,
                profile_id=me.id,
                role="member",
            )
        )

    invite.status = "accepted"

    # ✅ RESTORE POSTS
    db.query(FamilyGroupPost).filter(
        FamilyGroupPost.group_id == invite.group_id,
        FamilyGroupPost.author_profile_id == me.id,
        FamilyGroupPost.status == "hidden_by_system",
    ).update(
        {"status": "visible"},
        synchronize_session=False,
    )

    # ✅ RESTORE COMMENTS
    db.query(FamilyGroupPostComment).filter(
        FamilyGroupPostComment.author_profile_id == me.id,
        FamilyGroupPostComment.status == "hidden_by_system",
    ).update(
        {"status": "visible"},
        synchronize_session=False,
    )

    db.commit()
    return {"status": "accepted"}
# --------------------------------------------------
# DECLINE GROUP INVITE (INVITED USER)
# --------------------------------------------------
@router.post("/invites/{invite_id}/decline")
def decline_group_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    invite = (
        db.query(FamilyInvite)
        .filter(
            FamilyInvite.id == invite_id,
            FamilyInvite.invited_profile_id == me.id,
            FamilyInvite.status == "pending",
        )
        .first()
    )
    if not invite:
        raise HTTPException(404, "Invite not found")

    invite.status = "declined"
    db.commit()

    return {"status": "declined"}
# --------------------------------------------------
# MY OUTGOING GROUP REQUESTS
# --------------------------------------------------
@router.get("/join-requests/mine")
def my_join_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    rows = (
        db.query(FamilyGroupJoinRequest, FamilyGroup)
        .join(FamilyGroup, FamilyGroup.id == FamilyGroupJoinRequest.group_id)
        .filter(
            FamilyGroupJoinRequest.profile_id == me.id,
            FamilyGroupJoinRequest.status == "pending",
        )
        .order_by(FamilyGroupJoinRequest.created_at.desc())
        .all()
    )

    return [
        {
            "request_id": req.id,
            "group_id": group.id,
            "group_name": group.name,
            "group_image_url": group.group_image_url,
            "created_at": req.created_at,
        }
        for req, group in rows
    ]
# ==================================================
# GROUP MERGE REQUESTS
# ==================================================

@router.post("/{to_group_id}/merge-request", response_model=GroupMergeRequestOut)
def request_group_merge(
    to_group_id: str,
    payload: FamilyGroupMergeRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    to_group = resolve_group(db, to_group_id)
    from_group = resolve_group(db, payload.from_group_id)

    # --------------------------------------------------
    # VALIDATION
    # --------------------------------------------------
    if from_group.id == to_group.id:
        raise HTTPException(400, "Cannot merge a group into itself")

    # must be admin of FROM group
    require_admin(db, from_group.id, me.id)

    # must NOT be archived
    if from_group.is_archived or to_group.is_archived:
        raise HTTPException(400, "Cannot merge archived groups")

    # --------------------------------------------------
    # PREVENT DUPLICATE PENDING REQUEST
    # --------------------------------------------------
    existing = (
        db.query(FamilyGroupMergeRequest)
        .filter(
            FamilyGroupMergeRequest.from_group_id == from_group.id,
            FamilyGroupMergeRequest.to_group_id == to_group.id,
            FamilyGroupMergeRequest.status == "pending",
        )
        .first()
    )

    if existing:
        return GroupMergeRequestOut(
            id=existing.id,

            from_group_id=existing.from_group_id,
            from_group_name=existing.from_group.name,
            from_group_image_url=existing.from_group.group_image_url,

            to_group_id=existing.to_group_id,
            to_group_name=existing.to_group.name,
            to_group_image_url=existing.to_group.group_image_url,

            message=existing.message,
            status=existing.status,
            created_at=existing.created_at,
        )

    # --------------------------------------------------
    # CREATE NEW MERGE REQUEST
    # --------------------------------------------------
    req = FamilyGroupMergeRequest(
        id=str(uuid.uuid4()),
        from_group_id=from_group.id,
        to_group_id=to_group.id,
        requested_by_profile_id=me.id,
        message=payload.message or "",
        status="pending",
        created_at=datetime.utcnow(),
    )

    db.add(req)
    db.commit()
    db.refresh(req)

    return GroupMergeRequestOut(
        id=req.id,

        from_group_id=req.from_group_id,
        from_group_name=from_group.name,
        from_group_image_url=from_group.group_image_url,

        to_group_id=req.to_group_id,
        to_group_name=to_group.name,
        to_group_image_url=to_group.group_image_url,

        message=req.message,
        status=req.status,
        created_at=req.created_at,
    )

# ==================================================
# INCOMING MERGE REQUESTS
# ==================================================
@router.get(
    "/merge-requests/incoming",
    response_model=list[GroupMergeRequestOut],
)
def incoming_merge_requests(
    group_id: str | None = None,  # 👈 ADD THIS
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    query = (
        db.query(FamilyGroupMergeRequest)
        .join(FamilyGroup, FamilyGroup.id == FamilyGroupMergeRequest.from_group_id)
        .filter(FamilyGroupMergeRequest.status == "pending")
    )

    if group_id:
        # 🔐 Group-scoped (CORRECT for group screen)
        group = resolve_group(db, group_id)
        require_admin(db, group.id, me.id)

        query = query.filter(
            FamilyGroupMergeRequest.to_group_id == group.id
        )
    else:
        # 🧠 Profile-wide fallback (keeps old behaviour if needed)
        admin_group_ids = (
            db.query(FamilyGroupMember.group_id)
            .filter(
                FamilyGroupMember.profile_id == me.id,
                FamilyGroupMember.role == "admin",
            )
            .subquery()
        )

        query = query.filter(
            FamilyGroupMergeRequest.to_group_id.in_(admin_group_ids)
        )

    requests = (
        query.order_by(FamilyGroupMergeRequest.created_at.desc()).all()
    )

    return [
        GroupMergeRequestOut(
            id=r.id,

            from_group_id=r.from_group_id,
            from_group_name=r.from_group.name,
            from_group_image_url=r.from_group.group_image_url,

            to_group_id=r.to_group_id,
            to_group_name=r.to_group.name,
            to_group_image_url=r.to_group.group_image_url,

            message=r.message or "",
            status=r.status,
            created_at=r.created_at,
        )
        for r in requests
    ]
# ==================================================
# OUTGOING MERGE REQUESTS
# ==================================================
@router.get(
    "/merge-requests/outgoing",
    response_model=list[GroupMergeRequestOut],
)
def my_outgoing_group_merge_requests(
    group_id: str | None = None,  # 👈 ADD THIS
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    query = (
        db.query(FamilyGroupMergeRequest)
        .join(FamilyGroup, FamilyGroup.id == FamilyGroupMergeRequest.to_group_id)
        .filter(
            FamilyGroupMergeRequest.requested_by_profile_id == me.id,
            FamilyGroupMergeRequest.status == "pending",
        )
    )

    if group_id:
        # 🔐 Group-scoped (CORRECT for group screen)
        group = resolve_group(db, group_id)
        require_admin(db, group.id, me.id)

        query = query.filter(
            FamilyGroupMergeRequest.from_group_id == group.id
        )

    reqs = query.order_by(
        FamilyGroupMergeRequest.created_at.desc()
    ).all()

    return [
        GroupMergeRequestOut(
            id=r.id,

            from_group_id=r.from_group_id,
            from_group_name=r.from_group.name if r.from_group else None,
            from_group_image_url=r.from_group.group_image_url if r.from_group else None,

            to_group_id=r.to_group_id,
            to_group_name=r.to_group.name if r.to_group else None,
            to_group_image_url=r.to_group.group_image_url if r.to_group else None,

            message=r.message or "",
            status=r.status,
            created_at=r.created_at,
        )
        for r in reqs
    ]

def _execute_group_merge(db: Session, from_group_id: str, to_group_id: str):
    from app.models.family_group_post import FamilyGroupPost

    # 1️⃣ Move MEMBERS
    from_members = (
        db.query(FamilyGroupMember)
        .filter(FamilyGroupMember.group_id == from_group_id)
        .all()
    )

    for m in from_members:
        exists = db.query(FamilyGroupMember).filter(
            FamilyGroupMember.group_id == to_group_id,
            FamilyGroupMember.profile_id == m.profile_id,
        ).first()

        if not exists:
            db.add(
                FamilyGroupMember(
                    group_id=to_group_id,
                    profile_id=m.profile_id,
                    role=m.role,
                    joined_at=m.joined_at,
                )
            )

    # 2️⃣ Move POSTS
    db.query(FamilyGroupPost).filter(
        FamilyGroupPost.group_id == from_group_id
    ).update(
        {"group_id": to_group_id},
        synchronize_session=False,
    )

    # 3️⃣ Move PEOPLE
    db.query(FamilyPerson).filter(
        FamilyPerson.group_id == from_group_id
    ).update(
        {"group_id": to_group_id},
        synchronize_session=False,
    )

    # 4️⃣ Move invites & join requests
    db.query(FamilyInvite).filter(
        FamilyInvite.group_id == from_group_id
    ).update(
        {"group_id": to_group_id},
        synchronize_session=False,
    )

    db.query(FamilyGroupJoinRequest).filter(
        FamilyGroupJoinRequest.group_id == from_group_id
    ).update(
        {"group_id": to_group_id},
        synchronize_session=False,
    )

    # 5️⃣ Archive source group
    from_group = db.query(FamilyGroup).filter(
        FamilyGroup.id == from_group_id
    ).first()

    if from_group:
        from_group.is_archived = True
        from_group.merged_into_group_id = to_group_id
        from_group.archived_at = datetime.utcnow()

# ==================================================
# ACCEPT MERGE REQUESTS
# ==================================================
@router.post("/merge-requests/{request_id}/accept")
def accept_group_merge_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    req = db.query(FamilyGroupMergeRequest).filter(
        FamilyGroupMergeRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(404, "Merge request not found")

    if req.status != "pending":
        return {"status": req.status}

    to_group = resolve_group(db, req.to_group_id)
    from_group = resolve_group(db, req.from_group_id)

    require_admin(db, to_group.id, me.id)

    _execute_group_merge(db, from_group.id, to_group.id)

    req.status = "accepted"
    req.responded_at = datetime.utcnow()
    db.commit()

    return {"status": "accepted"}


# ==================================================
# DECLINE MERGE REQUESTS
# ==================================================
@router.post("/merge-requests/{request_id}/decline")
def decline_group_merge_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    req = db.query(FamilyGroupMergeRequest).filter(
        FamilyGroupMergeRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(404, "Merge request not found")

    to_group = resolve_group(db, req.to_group_id)
    require_admin(db, to_group.id, me.id)

    if req.status != "pending":
        return {"status": req.status}

    req.status = "declined"
    req.responded_at = datetime.utcnow()
    db.commit()

    return {"status": "declined"}

# ==================================================
#CANCEL MERGE REQUESTS
# ==================================================

@router.post("/merge-requests/{request_id}/cancel")
def cancel_group_merge_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user["sub"])

    req = db.query(FamilyGroupMergeRequest).filter(
        FamilyGroupMergeRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(404, "Merge request not found")

    if req.requested_by_profile_id != me.id:
        raise HTTPException(403, "Not authorised")

    if req.status != "pending":
        return {"status": req.status}

    req.status = "cancelled"
    req.responded_at = datetime.utcnow()
    db.commit()

    return {"status": "cancelled"}

