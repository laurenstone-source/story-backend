import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.config import settings

# Import models so SQLAlchemy registers tables
from app.models import (
    user,
    profile,
    timeline_event,
    media,
    event_gallery,
    connection,
    block,
    family_group,
    family_group_member,
    family_group_join_request,
    family_group_merge_request,
    family_group_post,
    family_group_post_comment,
    family_group_post_media,
    family_group_post_comment_media,
)

# Routers
from app.routers import (
    auth_router,
    profile_router,
    timeline_router,
    gallery_router,
    connection_router,
    blocks_router,
    family_groups_router,
    family_group_post_router,
    family_group_post_comments_router,
    family_group_post_media_router,
    family_group_post_comment_media_router,
    media_library_router,
    media_library_zip,

)

# -----------------------
# AUTO-CREATE MEDIA FOLDERS
# -----------------------
def ensure_media_folders():
    """
    Automatically create required base media directories on startup.
    """
    base = "media"

    folders = [
        base,
        os.path.join(base, "timeline"),
        os.path.join(base, "profile"),
        os.path.join(base, "gallery"),
    ]

    for folder in folders:
        os.makedirs(folder, exist_ok=True)

# -----------------------
# CREATE APP
# -----------------------
app = FastAPI(
    title="Story App API",
    description="Backend API for the Story family memories application.",
    version="1.0.0",
)
print("DATABASE URL:", settings.DATABASE_URL)
print("RESOLVED PATH:", os.path.abspath("story.db"))
# -----------------------
# CORS (ONLY ONCE)
# -----------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow all during development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------
# DATABASE TABLES
# -----------------------
Base.metadata.create_all(bind=engine)

# -----------------------
# STATIC MEDIA FILES
# -----------------------
app.mount("/media", StaticFiles(directory="media"), name="media")

# -----------------------
# ROUTES
# -----------------------
app.include_router(auth_router.router)
app.include_router(profile_router.router)
app.include_router(timeline_router.router)
app.include_router(blocks_router.router)
app.include_router(family_groups_router.router)
app.include_router(family_group_post_router.router)
app.include_router(family_group_post_comments_router.router)
app.include_router(family_group_post_media_router.router)
app.include_router(family_group_post_comment_media_router.router)
app.include_router(media_library_router.router)
app.include_router(media_library_zip.router)
app.include_router(connection_router.router)

app.include_router(gallery_router.router)

# -----------------------
# HEALTH CHECK
# -----------------------
@app.get("/")
def root():
    return {"message": "Story API is running!"}
