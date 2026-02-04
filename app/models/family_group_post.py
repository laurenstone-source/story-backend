# app/models/family_group_post.py

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class FamilyGroupPost(Base):
    __tablename__ = "family_group_posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)
    author_profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)
    last_activity_at = Column(
    DateTime,
    default=datetime.utcnow,
    nullable=False,
)
    content_text = Column(String, nullable=True)
    status = Column(String, default="visible")

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

    comments = relationship(
        "FamilyGroupPostComment",
        back_populates="post",
        cascade="all, delete-orphan",
    )

    media = relationship(
        "FamilyGroupPostMedia",
        uselist=False,                  # ✅ single media item
        back_populates="post",
        cascade="all, delete-orphan",
    )
