from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app.auth import get_current_user
from app.models.user import User
from app.models.profile import Profile
from app.models.family_relationship import FamilyRelationship
from app.models.family_relationship_request import FamilyRelationshipRequest
from app.schemas.family_relationship_schema import (
    FamilyRelationshipRequestCreate,
    FamilyRelationshipRequestOut,
    FamilyRelationshipRequestsMine,
)
from app.core.profile_access import get_current_user_profile

router = APIRouter(prefix="/family", tags=["Family Relationships"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# SEND REQUEST
# --------------------------------------------------
@router.post("/request", response_model=FamilyRelationshipRequestOut)
def send_family_request(
    payload: FamilyRelationshipRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user.id)

    if payload.target_profile_id == my_profile.id:
        raise HTTPException(400, "Cannot relate to yourself")

    existing = db.query(FamilyRelationshipRequest).filter(
        FamilyRelationshipRequest.from_profile_id == my_profile.id,
        FamilyRelationshipRequest.to_profile_id == payload.target_profile_id,
        FamilyRelationshipRequest.status == "pending",
    ).first()

    if existing:
        raise HTTPException(400, "Request already pending")

    req = FamilyRelationshipRequest(
        from_profile_id=my_profile.id,
        to_profile_id=payload.target_profile_id,
        relationship_type=payload.relationship_type,
        reciprocal_relationship_type=payload.reciprocal_relationship_type,
    )

    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# --------------------------------------------------
# ACCEPT REQUEST
# --------------------------------------------------
@router.post("/request/{request_id}/accept")
def accept_family_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user.id)

    req = db.query(FamilyRelationshipRequest).filter(
        FamilyRelationshipRequest.id == request_id,
        FamilyRelationshipRequest.status == "pending",
    ).first()

    if not req or req.to_profile_id != my_profile.id:
        raise HTTPException(404, "Request not found")

    req.status = "accepted"
    req.responded_at = datetime.utcnow()

    # Create relationship A → B
    rel_ab = FamilyRelationship(
        profile_a_id=req.from_profile_id,
        profile_b_id=req.to_profile_id,
        relationship_type=req.relationship_type,
    )
    db.add(rel_ab)

    # Optional reciprocal relationship B → A
    if req.reciprocal_relationship_type:
        rel_ba = FamilyRelationship(
            profile_a_id=req.to_profile_id,
            profile_b_id=req.from_profile_id,
            relationship_type=req.reciprocal_relationship_type,
        )
        db.add(rel_ba)

    db.commit()
    return {"status": "accepted"}


# --------------------------------------------------
# REJECT REQUEST
# --------------------------------------------------
@router.post("/request/{request_id}/reject")
def reject_family_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user.id)

    req = db.query(FamilyRelationshipRequest).filter(
        FamilyRelationshipRequest.id == request_id,
        FamilyRelationshipRequest.status == "pending",
    ).first()

    if not req or req.to_profile_id != my_profile.id:
        raise HTTPException(404, "Request not found")

    req.status = "rejected"
    req.responded_at = datetime.utcnow()
    db.commit()

    return {"status": "rejected"}


# --------------------------------------------------
# CANCEL REQUEST (SENDER ONLY)
# --------------------------------------------------
@router.post("/request/{request_id}/cancel")
def cancel_family_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user.id)

    req = db.query(FamilyRelationshipRequest).filter(
        FamilyRelationshipRequest.id == request_id,
        FamilyRelationshipRequest.status == "pending",
    ).first()

    if not req or req.from_profile_id != my_profile.id:
        raise HTTPException(404, "Request not found")

    req.status = "cancelled"
    req.responded_at = datetime.utcnow()
    db.commit()

    return {"status": "cancelled"}


# --------------------------------------------------
# MY REQUESTS (INCOMING / OUTGOING)
# --------------------------------------------------
@router.get("/requests/mine", response_model=FamilyRelationshipRequestsMine)
def my_family_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    my_profile = get_current_user_profile(db, current_user.id)

    incoming = db.query(FamilyRelationshipRequest).filter(
        FamilyRelationshipRequest.to_profile_id == my_profile.id,
        FamilyRelationshipRequest.status == "pending",
    ).all()

    outgoing = db.query(FamilyRelationshipRequest).filter(
        FamilyRelationshipRequest.from_profile_id == my_profile.id,
        FamilyRelationshipRequest.status == "pending",
    ).all()

    return {
        "incoming": incoming,
        "outgoing": outgoing,
    }
