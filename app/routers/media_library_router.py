# app/routers/media_library_router.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.auth.supabase_auth import get_current_user

from app.models.media import MediaFile
from app.models.profile import Profile
from app.models.timeline_event import TimelineEvent
from app.models.event_gallery import EventGallery

from app.schemas.media_library_schema import MediaLibraryItemOut
from app.utils.urls import absolute_media_url

router = APIRouter(prefix="/media-library", tags=["Media Library"])


# ==========================================================
# Helpers
# ==========================================================

def _abs(path: str | None) -> str | None:
    """
    Convert stored Supabase/local path into full absolute URL.
    """
    if not path:
        return None
    return absolute_media_url(path)


def _safe_name(value: str | None, fallback: str) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned else fallback


# ==========================================================
# GET FULL MEDIA LIBRARY
# ==========================================================
@router.get("/library", response_model=list[MediaLibraryItemOut])
def get_media_library(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    results: list[dict] = []

    # ======================================================
    # 1) MediaFile items (images/videos + voice notes)
    # ======================================================
    media_items = (
        db.query(MediaFile)
        .filter(MediaFile.user_id == current_user["sub"])
        .options(
            joinedload(MediaFile.profile),
            joinedload(MediaFile.timeline_event),
            joinedload(MediaFile.gallery),
        )
        .order_by(MediaFile.uploaded_at.desc())
        .all()
    )

    for m in media_items:
        profile_name = m.profile.full_name if m.profile else None
        event_title = m.timeline_event.title if m.timeline_event else None
        gallery_title = m.gallery.title if m.gallery else None

        # --------------------------------------------------
        # Origin label for UI
        # --------------------------------------------------
        if gallery_title:
            origin = f"Gallery: {_safe_name(gallery_title, 'Gallery')}"
            label = _safe_name(gallery_title, "Gallery media")

        elif event_title:
            origin = f"Event: {_safe_name(event_title, 'Event')}"
            label = _safe_name(event_title, "Event media")

        elif profile_name:
            origin = f"Profile: {_safe_name(profile_name, 'Profile')}"
            label = _safe_name(profile_name, "Profile media")

        else:
            origin = "Personal media"
            label = "Media"

        # --------------------------------------------------
        # Main media entry
        # --------------------------------------------------
        results.append({
            "id": f"media-{m.id}",
            "media_id": m.id,

            "file_path": _abs(m.file_path),
            "file_type": m.file_type,

            "label": label,
            "origin": origin,

            "caption": m.caption,
            "uploaded_at": m.uploaded_at,

            "thumbnail_path": _abs(m.thumbnail_path),
            "voice_note_path": _abs(m.voice_note_path),

            "profile_id": m.profile_id,
            "event_id": m.event_id,
            "gallery_id": m.gallery_id,
        })

        # --------------------------------------------------
        # Separate AUDIO entry for media voice note
        # --------------------------------------------------
        if m.voice_note_path:
            results.append({
                "id": f"media-voice-{m.id}",
                "media_id": m.id,

                "file_path": _abs(m.voice_note_path),
                "file_type": "audio",

                "label": "Voice note",
                "origin": origin,

                "caption": None,
                "uploaded_at": m.uploaded_at,

                "thumbnail_path": None,
                "voice_note_path": None,

                "profile_id": m.profile_id,
                "event_id": m.event_id,
                "gallery_id": m.gallery_id,
            })

    # ======================================================
    # 2) Profile Voice Note
    # ======================================================
    my_profile = (
        db.query(Profile)
        .filter(Profile.user_id == current_user["sub"])
        .first()
    )

    if my_profile and my_profile.voice_note_path:
        pname = _safe_name(my_profile.full_name, "My profile")

        results.append({
            "id": f"profile-audio-{my_profile.id}",
            "profile_id": my_profile.id,

            "file_path": _abs(my_profile.voice_note_path),
            "file_type": "audio",

            "label": "Profile voice note",
            "origin": f"Profile: {pname}",

            "caption": None,
            "uploaded_at": my_profile.updated_at,

            "thumbnail_path": None,
            "voice_note_path": None,

            "media_id": None,
            "event_id": None,
            "gallery_id": None,
        })

    # ======================================================
    # 3) Event Voice Notes
    # ======================================================
    if my_profile:
        events = (
            db.query(TimelineEvent)
            .filter(TimelineEvent.profile_id == my_profile.id)
            .order_by(TimelineEvent.created_at.desc())
            .all()
        )

        for e in events:
            if not e.audio_url:
                continue

            title = _safe_name(e.title, f"Event {e.id}")

            results.append({
                "id": f"event-audio-{e.id}",
                "event_id": e.id,
                "profile_id": my_profile.id,

                "file_path": _abs(e.audio_url),
                "file_type": "audio",

                "label": "Event voice note",
                "origin": f"Event: {title}",

                "caption": None,
                "uploaded_at": e.created_at,

                "thumbnail_path": None,
                "voice_note_path": None,

                "media_id": None,
                "gallery_id": None,
            })

    # ======================================================
    # 4) Gallery Voice Notes
    # ======================================================
    if my_profile:
        galleries = (
            db.query(EventGallery)
            .join(TimelineEvent, TimelineEvent.id == EventGallery.event_id)
            .filter(TimelineEvent.profile_id == my_profile.id)
            .order_by(EventGallery.created_at.desc())
            .all()
        )

        for g in galleries:
            if not g.voice_note_path:
                continue

            gtitle = _safe_name(g.title, f"Gallery {g.id}")
            etitle = _safe_name(
                g.event.title if g.event else None,
                f"Event {g.event_id}"
            )

            results.append({
                "id": f"gallery-audio-{g.id}",
                "gallery_id": g.id,
                "event_id": g.event_id,
                "profile_id": my_profile.id,

                "file_path": _abs(g.voice_note_path),
                "file_type": "audio",

                "label": "Gallery voice note",
                "origin": f"Gallery: {gtitle} (Event: {etitle})",

                "caption": None,
                "uploaded_at": g.created_at,

                "thumbnail_path": None,
                "voice_note_path": None,

                "media_id": None,
            })

    return results
