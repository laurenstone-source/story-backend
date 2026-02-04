from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from datetime import datetime
from app.database import Base


class FamilyTree(Base):
    __tablename__ = "family_trees"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    created_by_profile_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Archive/merge tracking
    is_archived = Column(Boolean, default=False, nullable=False)
    merged_into_tree_id = Column(Integer, ForeignKey("family_trees.id"), nullable=True)
    archived_at = Column(DateTime, nullable=True)
