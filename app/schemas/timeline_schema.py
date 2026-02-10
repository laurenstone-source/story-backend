from pydantic import BaseModel
from typing import Optional, Literal
from datetime import date

from .media_schema import MediaFileOut


# ---------------------------------------------------------
# BASE
# ---------------------------------------------------------
class TimelineEventBase(BaseModel):
    title: str
    description: Optional[str] = None
    item_type: Literal["life_event", "message"] = "life_event"
    # ✅ NEW DATE SYSTEM
    start_date: date
    end_date: Optional[date] = None
    date_precision: Literal["day", "month", "year"]

    order_index: int = 0


# ---------------------------------------------------------
# CREATE
# ---------------------------------------------------------
class TimelineEventCreate(TimelineEventBase):
    profile_id: str


# ---------------------------------------------------------
# UPDATE
# ---------------------------------------------------------
class TimelineEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    item_type: Optional[Literal["life_event", "message"]] = None
    # ✅ NEW DATE SYSTEM
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    date_precision: Optional[Literal["day", "month", "year"]] = None

    order_index: Optional[int] = None


# ---------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------
class TimelineEventOut(BaseModel):
    id: int
    profile_id: str

    title: str
    description: Optional[str] = None
    item_type: Literal["life_event", "message"]
    # ✅ NEW DATE SYSTEM
    start_date: date
    end_date: Optional[date] = None
    date_precision: Literal["day", "month", "year"]

    order_index: int

    main_media: Optional[MediaFileOut] = None

    # EXISTING FIELDS (UNCHANGED)
    audio_url: Optional[str] = None
    story_text: Optional[str] = None

    model_config = {
        "from_attributes": True
    }
