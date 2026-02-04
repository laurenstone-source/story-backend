from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Main profile relationship (uses user_id in Profile)
    profile = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        foreign_keys="Profile.user_id"
    )

    media_files = relationship("MediaFile", back_populates="user")
   
