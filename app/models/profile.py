import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.types import Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

from app.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, index=True)

    # ✅ Supabase user UUID
    user_id = Column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True
    )

    full_name = Column(String, nullable=True)

    bio = Column(String, nullable=True)
    long_biography = Column(Text, nullable=True)

    is_public = Column(Boolean, default=True)
    is_searchable = Column(Boolean, default=True)

    next_of_kin_name = Column(String, nullable=True)
    next_of_kin_email = Column(String, nullable=True, index=True)

    date_of_birth = Column(Date, nullable=True)
    is_deceased = Column(Boolean, default=False)
    date_of_death = Column(Date, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile_picture_media_id = Column(
        Integer,
        nullable=True
    )
    profile_video_media_id = Column(
        Integer,
        nullable=True
    )

    voice_note_path = Column(String, nullable=True)

    # -------------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------------

    events = relationship(
        "TimelineEvent",
        back_populates="profile",
        cascade="all, delete-orphan"
    )

    media_files = relationship(
        "MediaFile",
        back_populates="profile",
        foreign_keys="MediaFile.profile_id"
    )