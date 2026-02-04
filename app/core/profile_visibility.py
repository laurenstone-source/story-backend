from sqlalchemy.orm import Session
from app.models.profile import Profile
from app.models.connection import Connection
from app.models.family_group_member import FamilyGroupMember

def in_same_family_group(db: Session, profile_a_id: str, profile_b_id: str) -> bool:
    a_groups = db.query(FamilyGroupMember.group_id).filter(
        FamilyGroupMember.profile_id == profile_a_id
    ).subquery()

    shared = db.query(FamilyGroupMember).filter(
        FamilyGroupMember.profile_id == profile_b_id,
        FamilyGroupMember.group_id.in_(a_groups),
    ).first()

    return shared is not None


def can_view_profile(
    db: Session,
    viewer_user_id: str,
    target_profile_id: str,
) -> bool:
    profile = db.query(Profile).filter(Profile.id == target_profile_id).first()
    if not profile:
        return False

    # Owner
    if profile.user_id == viewer_user_id:
        return True

    # Public
    if profile.is_public:
        return True

    viewer_profile = db.query(Profile).filter(
        Profile.user_id == viewer_user_id
    ).first()
    if not viewer_profile:
        return False

    # Same family group
    if in_same_family_group(db, viewer_profile.id, target_profile_id):
        return True

    # Accepted connection
    conn = db.query(Connection).filter(
        Connection.status == "accepted",
        (
            (Connection.from_profile_id == viewer_profile.id)
            & (Connection.to_profile_id == target_profile_id)
        ) | (
            (Connection.to_profile_id == viewer_profile.id)
            & (Connection.from_profile_id == target_profile_id)
        ),
    ).first()

    return conn is not None
