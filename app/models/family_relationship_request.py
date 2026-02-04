from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base


class FamilyRelationshipRequest(Base):
    __tablename__ = "family_relationship_requests"

    id = Column(Integer, primary_key=True)

    from_profile_id = Column(String, nullable=False)
    to_profile_id = Column(String, nullable=False)

    # Requested role (e.g. "mother", "spouse")
    relationship_type = Column(String, nullable=False)

    # Optional reciprocal role (e.g. "child", "spouse")
    reciprocal_relationship_type = Column(String, nullable=True)

    # pending / accepted / rejected / cancelled
    status = Column(String, default="pending", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)
