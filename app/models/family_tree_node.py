from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class FamilyTreeNode(Base):
    __tablename__ = "family_tree_nodes"

    id = Column(Integer, primary_key=True)

    tree_id = Column(
        Integer,
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Nullable until claimed
    profile_id = Column(
        String,
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ✅ Relationship (AFTER profile_id exists)
    profile = relationship(
        "Profile",
        foreign_keys=[profile_id],
        lazy="joined",
    )

    display_name = Column(String, nullable=False)

    gender = Column(String, nullable=True)
    date_of_birth = Column(String, nullable=True)
    date_of_death = Column(String, nullable=True)

    # Claim/confirmation
    is_confirmed = Column(Boolean, default=False, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
