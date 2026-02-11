from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class EventGallery(Base):
    __tablename__ = "event_galleries"

    id = Column(Integer, primary_key=True, index=True)

    # Which event this gallery belongs to
    event_id = Column(Integer, ForeignKey("timeline_events.id"), nullable=False)

    # Basic info
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    long_description = Column(Text, nullable=True)

    # MAIN COVER MEDIA
    main_media_id = Column(Integer, ForeignKey("media_files.id"), nullable=True)

    # NEW SYSTEM: gallery-level voice note stored directly as a file path
    voice_note_path = Column(String, nullable=True)

    # Sort order
    position = Column(Integer, default=0)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)

    # --------------------------------------------------
    # Relationships
    # --------------------------------------------------

    event = relationship(
        "TimelineEvent",
        back_populates="galleries",
        foreign_keys=[event_id],
    )

    media_files = relationship(
        "MediaFile",
        back_populates="gallery",
        foreign_keys="MediaFile.gallery_id",
        cascade="all, delete-orphan",
    )

    # Single cover image
    main_media = relationship(
        "MediaFile",
        foreign_keys=[main_media_id],
        uselist=False,
        lazy="joined",
        post_update=True,
    )

    # --------------------------------------------------
    # API Helpers
    # --------------------------------------------------

    @property
    def thumbnail_media(self):
        return self.main_media
