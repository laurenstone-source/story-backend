# app/models/block.py
from sqlalchemy import Column, String, DateTime, ForeignKey
from datetime import datetime
from app.database import Base

class Block(Base):
    __tablename__ = "blocks"

    blocker_profile_id = Column(
        String,
        ForeignKey("profiles.id"),
        primary_key=True,
    )

    blocked_profile_id = Column(
        String,
        ForeignKey("profiles.id"),
        primary_key=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
