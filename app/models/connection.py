import uuid

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)

    # Profiles involved
    from_profile_id = Column(
        String,
        ForeignKey("profiles.id"),
        nullable=False,
        index=True,
    )

    to_profile_id = Column(
        String,
        ForeignKey("profiles.id"),
        nullable=False,
        index=True,
    )

    # Relationship labels (directional)
    from_profile_relation = Column(String, nullable=True)
    to_profile_relation = Column(String, nullable=True)

    # Connection state
    status = Column(
        String,
        nullable=False,
        default="pending",
        index=True,
    )

    # ✅ FIX: Who initiated the request (UUID not String)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    rejected_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "from_profile_id != to_profile_id",
            name="ck_connections_not_self",
        ),
        Index(
            "ix_connections_from_status",
            "from_profile_id",
            "status",
        ),
        Index(
            "ix_connections_to_status",
            "to_profile_id",
            "status",
        ),
    )
