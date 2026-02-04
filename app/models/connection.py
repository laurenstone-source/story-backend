from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
)
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

    # ------------------------------------
    # Relationship labels (DIRECTIONAL)
    # ------------------------------------
    # How *from_profile* sees *to_profile*
    from_profile_relation = Column(String, nullable=True)

    # How *to_profile* sees *from_profile*
    to_profile_relation = Column(String, nullable=True)

    # ------------------------------------
    # Connection state
    # ------------------------------------
    # pending | accepted | rejected
    status = Column(
        String,
        nullable=False,
        default="pending",
        index=True,
    )

    # Who initiated the request
    created_by_user_id = Column(
        String,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # ------------------------------------
    # Timestamps
    # ------------------------------------
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

    # Soft rejection timestamp (Facebook-style behaviour)
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
