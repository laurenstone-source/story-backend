from sqlalchemy.orm import Session
from app.models.block import Block

def is_blocked(
    db: Session,
    profile_a_id: str,
    profile_b_id: str,
) -> bool:
    """
    Returns True if either profile has blocked the other.
    """
    return (
        db.query(Block)
        .filter(
            (
                (Block.blocker_profile_id == profile_a_id)
                & (Block.blocked_profile_id == profile_b_id)
            )
            | (
                (Block.blocker_profile_id == profile_b_id)
                & (Block.blocked_profile_id == profile_a_id)
            )
        )
        .first()
        is not None
    )
