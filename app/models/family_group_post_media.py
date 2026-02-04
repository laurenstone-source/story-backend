# app/models/family_group_post_media.py



from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class FamilyGroupPostMedia(Base):
    __tablename__ = "family_group_post_media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("family_group_posts.id"), nullable=False)

    media_path = Column(String, nullable=False)
    media_type = Column(String, nullable=False)  # image / video

    post = relationship(
        "FamilyGroupPost",
        back_populates="media",
    )
