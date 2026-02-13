import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ FIX: user_id must match users.id (UUID)
    user_id = Column(
         UUID(as_uuid=True),
         nullable=False,
         index=True,
    )

    # Used by timeline event main image
    event_id = Column(
        Integer,
        ForeignKey("timeline_events.id", ondelete="CASCADE"),
        nullable=True
    )

    # Used by profile picture/video
    profile_id = Column(
        String,
        ForeignKey("profiles.id"),
        nullable=True
    )

    # Used by gallery
    gallery_id = Column(
        Integer,
        ForeignKey("event_galleries.id", ondelete="CASCADE"),
        nullable=True
    )

    # File info
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # image / video / audio
    file_size = Column(Integer, nullable=False)

    caption = Column(String, nullable=True)
    voice_note_path = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)

    duration_seconds = Column(Integer, nullable=True)

    original_scope = Column(String, nullable=False, default="gallery")

    original_media_id = Column(
        Integer,
        ForeignKey("media_files.id"),
        nullable=True
    )

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    order_index = Column(Integer, nullable=False, default=0)

    # -------------------------
    # RELATIONSHIPS
    # -------------------------

    timeline_event = relationship("TimelineEvent", foreign_keys=[event_id])

    profile = relationship(
        "Profile",
        back_populates="media_files",
        foreign_keys=[profile_id],
    )

    gallery = relationship(
        "EventGallery",
        back_populates="media_files",
        foreign_keys=[gallery_id],
        passive_deletes=True,
    )

    original_media = relationship(
        "MediaFile",
        remote_side=[id],
        uselist=False,
    )

    
