from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.media import MediaFile


def get_user_storage_usage_bytes(
    db: Session,
    user_id,
) -> int:
    """
    Returns total storage used by a user in bytes.
    """
    total = (
        db.query(func.coalesce(func.sum(MediaFile.file_size), 0))
        .filter(MediaFile.user_id == user_id)
        .scalar()
    )

    return int(total or 0)