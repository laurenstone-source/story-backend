# app/models/family_group_post_comment.py

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class FamilyGroupPostComment(Base):
    __tablename__ = "family_group_post_comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("family_group_posts.id"), nullable=False)
    author_profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)

    content_text = Column(String, nullable=False)
    status = Column(String, default="visible", nullable=False)

    hidden_reason = Column(String, nullable=True)
    hidden_by_profile_id = Column(String, ForeignKey("profiles.id"), nullable=True)
    hidden_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # -------------------------
    # RELATIONSHIPS
    # -------------------------

    author = relationship(
        "Profile",
        foreign_keys=[author_profile_id],
        lazy="joined",
    )

    hidden_by = relationship(
        "Profile",
        foreign_keys=[hidden_by_profile_id],
        lazy="joined",
    )

    post = relationship(
        "FamilyGroupPost",
        back_populates="comments",
    )

    media = relationship(
        "FamilyGroupPostCommentMedia",
        uselist=False,                  # ✅ single media item
        back_populates="comment",
        cascade="all, delete-orphan",
    )
