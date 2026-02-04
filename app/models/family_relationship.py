from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from app.database import Base


class FamilyRelationship(Base):
    """
    A confirmed, mutual relationship between two real profiles.
    This is the single source of truth for family semantics.
    """

    __tablename__ = "family_relationships"

    id = Column(Integer, primary_key=True)

    # ------------------------------------
    # The two confirmed profiles
    # ------------------------------------
    profile_a_id = Column(
        String,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    profile_b_id = Column(
        String,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ------------------------------------
    # Relationship semantics
    # ------------------------------------
    # Examples:
    # parent, child, spouse, sibling, partner
    relationship_type = Column(String, nullable=False)

    # Optional extra meaning
    # biological / adoptive / step / unknown
    lineage_type = Column(String, default="unknown", nullable=False)

    # ------------------------------------
    # Metadata
    # ------------------------------------
    created_at = Column(DateTime, default=datetime.utcnow)

    # Who initiated the confirmation (useful for audit/UI)
    confirmed_by_profile_id = Column(
        String,
        ForeignKey("profiles.id"),
        nullable=True,
    )
