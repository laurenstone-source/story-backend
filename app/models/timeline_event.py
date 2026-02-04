from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)

    title = Column(String, nullable=True)
    description = Column(String, nullable=True)

    # ----------------------------------------------------------
    # NEW FIELD: Long-form event story text
    # ----------------------------------------------------------
    story_text = Column(String, nullable=True)

    # ----------------------------------------------------------
    # NEW FIELD: Event-level audio URL
    # ----------------------------------------------------------
    audio_url = Column(String, nullable=True)

    # ----------------------------------------------------------
    # OLD SINGLE DATE (KEEP FOR NOW)
    # ----------------------------------------------------------
    event_date = Column(Date, nullable=True)

    # ----------------------------------------------------------
    # NEW DATE SYSTEM (FIXED INDENTATION)
    # ----------------------------------------------------------
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    date_precision = Column(String, nullable=False, default="day")

    order_index = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # ----------------------------------------------------------
    # ONE-TO-ONE MAIN IMAGE for EVENT
    # ----------------------------------------------------------
    main_media_id = Column(
        Integer,
        ForeignKey("media_files.id", ondelete="SET NULL"),
        nullable=True
    )

    main_media = relationship(
        "MediaFile",
        foreign_keys=[main_media_id],
        uselist=False,
        passive_deletes=True
    )

    # ----------------------------------------------------------
    # RELATIONSHIPS
    # ----------------------------------------------------------
    profile = relationship(
        "Profile",
        back_populates="events"
    )

    galleries = relationship(
        "EventGallery",
        back_populates="event",
        cascade="all, delete-orphan"
    )
