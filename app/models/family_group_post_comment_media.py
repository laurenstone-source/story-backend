# app/models/family_group_post_comment_media.py

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class FamilyGroupPostCommentMedia(Base):
    __tablename__ = "family_group_post_comment_media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    comment_id = Column(
        String,
        ForeignKey("family_group_post_comments.id"),
        nullable=False,
    )

    media_path = Column(String, nullable=False)
    media_type = Column(String, nullable=False)

    comment = relationship(
        "FamilyGroupPostComment",
        back_populates="media",
    )

