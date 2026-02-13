from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app.models.profile import Profile
from app.models.connection import Connection
from app.models.media import MediaFile
from app.schemas.connection_schema import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionMineOut,
)
from app.core.profile_access import get_current_user_profile
from app.auth.supabase_auth import get_current_user
from app.models.block import Block

from app.core.blocking import is_blocked
from app.schemas.connection_schema import SetRelationshipPayload




router = APIRouter(prefix="/connections", tags=["Connections"])

def profile_image_url(profile, db):
    if profile.profile_picture_media_id is None:
        return None

    media = (
        db.query(MediaFile)
        .filter(MediaFile.id == profile.profile_picture_media_id)
        .first()
    )

    if not media:
        return None

    return media.file_path
# --------------------------------------------------
# CONNECTION SERIALISER (MUST BE ABOVE ROUTES)
# --------------------------------------------------
def build_connection_out(conn: Connection, my_profile_id: str, db: Session):
    if conn.from_profile_id == my_profile_id:
        other = db.query(Profile).filter(
            Profile.id == conn.to_profile_id
        ).first()

        direction = "outgoing"
        relation = conn.from_profile_relation
    else:
        other = db.query(Profile).filter(
            Profile.id == conn.from_profile_id
        ).first()

        direction = "incoming"
        relation = conn.to_profile_relation

    return {
        "id": conn.id,
        "status": conn.status,
        "relation_type": relation,  # ✅ viewer-specific
        "direction": direction,
        "profile": {
            "id": other.id,
            "full_name": other.full_name,
            "profile_image": profile_image_url(other, db),
        },
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }


# --------------------------------------------------
# DB dependency
# --------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# REQUEST CONNECTION (soft Facebook logic)
# --------------------------------------------------
@router.post("/request", response_model=ConnectionOut)
def request_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from_profile = get_current_user_profile(db, current_user["sub"])

    to_profile = (
        db.query(Profile)
        .filter(Profile.id == payload.to_profile_id)
        .first()
    )
    if not to_profile:
        raise HTTPException(404, "Target profile not found")

    existing = (
        db.query(Connection)
        .filter(
            Connection.from_profile_id == from_profile.id,
            Connection.to_profile_id == payload.to_profile_id,
        )
        .first()
    )

    if existing:
        if existing.status == "accepted":
            raise HTTPException(400, "Already connected")

        if existing.status == "pending":
            raise HTTPException(400, "Request already sent")

        if existing.status == "rejected":
            # ✅ allow reconnect
            existing.status = "pending"
            existing.rejected_at = None
            db.commit()
            db.refresh(existing)

            return build_connection_out(existing, from_profile.id, db)

    conn = Connection(
        from_profile_id=from_profile.id,
        to_profile_id=payload.to_profile_id,
        status="pending",
        created_by_user_id=current_user["sub"],
    )

    db.add(conn)
    db.commit()
    db.refresh(conn)

    return build_connection_out(conn, from_profile.id, db)


# --------------------------------------------------
# MY CONNECTIONS
# --------------------------------------------------
@router.get("/mine")
def get_my_connections(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    # ----------------------------------------------
    # INCOMING (pending → to me)
    # ----------------------------------------------
    incoming = []
    for c in (
        db.query(Connection)
        .filter(
            Connection.to_profile_id == my_profile.id,
            Connection.status == "pending",
        )
        .all()
    ):
        other_profile_id = c.from_profile_id

        if is_blocked(db, my_profile.id, other_profile_id):
            continue

        incoming.append(
            build_connection_out(c, my_profile.id, db)
        )

    # ----------------------------------------------
    # OUTGOING (pending → from me)
    # ----------------------------------------------
    outgoing = []
    for c in (
        db.query(Connection)
        .filter(
            Connection.from_profile_id == my_profile.id,
            Connection.status == "pending",
        )
        .all()
    ):
        other_profile_id = c.to_profile_id

        if is_blocked(db, my_profile.id, other_profile_id):
            continue

        outgoing.append(
            build_connection_out(c, my_profile.id, db)
        )

    # ----------------------------------------------
    # ACCEPTED (either direction)
    # ----------------------------------------------
    accepted = []
    for c in (
        db.query(Connection)
        .filter(
            Connection.status == "accepted",
            (Connection.from_profile_id == my_profile.id)
            | (Connection.to_profile_id == my_profile.id),
        )
        .all()
    ):
        other_profile_id = (
            c.to_profile_id
            if c.from_profile_id == my_profile.id
            else c.from_profile_id
        )

        if is_blocked(db, my_profile.id, other_profile_id):
            continue

        accepted.append(
            build_connection_out(c, my_profile.id, db)
        )

    return {
        "incoming_pending": incoming,
        "outgoing_pending": outgoing,
        "accepted": accepted,
    }

# --------------------------------------------------
# ACCEPT CONNECTION
# --------------------------------------------------
@router.post("/{connection_id}/accept", response_model=ConnectionOut)
def accept_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(404, "Connection not found")

    if conn.to_profile_id != my_profile.id:
        raise HTTPException(403, "Not authorised")

    if conn.status != "pending":
        raise HTTPException(400, "Invalid state")

    conn.status = "accepted"
    conn.rejected_at = None
    db.commit()
    db.refresh(conn)

    return build_connection_out(conn, my_profile.id, db)


# --------------------------------------------------
# REJECT CONNECTION
# --------------------------------------------------
@router.post("/{connection_id}/reject", response_model=ConnectionOut)
def reject_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(404, "Connection not found")

    if conn.to_profile_id != my_profile.id:
        raise HTTPException(403, "Not authorised")

    conn.status = "rejected"
    conn.rejected_at = datetime.utcnow()
    db.commit()
    db.refresh(conn)

    return build_connection_out(conn, my_profile.id, db)

# --------------------------------------------------
# REMOVE / DISCONNECT (soft delete)
# --------------------------------------------------
@router.post("/{connection_id}/remove")
def remove_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(404, "Connection not found")

    # -----------------------------------------
    # If it's still pending → only sender can cancel
    # -----------------------------------------
    if conn.status == "pending":
        if conn.from_profile_id != my_profile.id:
            raise HTTPException(403, "Only the sender can cancel this request")

        conn.status = "rejected"
        conn.rejected_at = datetime.utcnow()
        db.commit()

        return {"message": "Connection request cancelled"}

    # -----------------------------------------
    # If it's accepted → either side can remove
    # -----------------------------------------
    if conn.status == "accepted":
        if my_profile.id not in {
            conn.from_profile_id,
            conn.to_profile_id,
        }:
            raise HTTPException(403, "Not authorised")

        conn.status = "rejected"
        conn.rejected_at = datetime.utcnow()
        db.commit()

        return {"message": "Connection removed"}

    return {"message": "Nothing to remove"}# --------------------------------------------------
# CONNECTION STATUS (read-only helper)
# --------------------------------------------------
@router.get("/status/{profile_id}")
def get_connection_status(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    # ----------------------------------------------
    # SELF
    # ----------------------------------------------
    if profile_id == my_profile.id:
        return {"status": "self"}

    # ----------------------------------------------
    # 🔒 BLOCK OVERRIDE (MUST COME BEFORE CONNECTIONS)
    # ----------------------------------------------
    blocked = db.query(Block).filter(
        (
            (Block.blocker_profile_id == my_profile.id)
            & (Block.blocked_profile_id == profile_id)
        )
        | (
            (Block.blocker_profile_id == profile_id)
            & (Block.blocked_profile_id == my_profile.id)
        )
    ).first()

    if blocked:
        return {"status": "blocked"}

    # ----------------------------------------------
    # CONNECTION STATUS (UNCHANGED)
    # ----------------------------------------------
    conn = (
        db.query(Connection)
        .filter(
            (
                (Connection.from_profile_id == my_profile.id)
                & (Connection.to_profile_id == profile_id)
            )
            | (
                (Connection.from_profile_id == profile_id)
                & (Connection.to_profile_id == my_profile.id)
            )
        )
        .order_by(Connection.created_at.desc())
        .first()
    )

    if not conn:
        return {"status": "none"}

    if conn.status == "accepted":
        return {"status": "accepted"}

    if conn.status == "pending":
        if conn.to_profile_id == my_profile.id:
            return {"status": "incoming_pending"}
        return {"status": "outgoing_pending"}

    return {"status": "none"}
    # ----------------------------------------------
# Set Relation (directional)
# ----------------------------------------------
@router.post("/{connection_id}/set-relationship")
def set_relationship(
    connection_id: int,
    payload: SetRelationshipPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user["sub"])

    conn = (
        db.query(Connection)
        .filter(
            Connection.id == connection_id,
            Connection.status == "accepted",
        )
        .first()
    )

    if not conn:
        raise HTTPException(404, "Connection not found")

    # Must be one of the two profiles
    if my_profile.id not in {
        conn.from_profile_id,
        conn.to_profile_id,
    }:
        raise HTTPException(403, "Not authorised")

    # Directional write (THIS is the key)
    if my_profile.id == conn.from_profile_id:
        conn.from_profile_relation = payload.relationship
    else:
        conn.to_profile_relation = payload.relationship

    db.commit()

    return {"status": "ok"}

