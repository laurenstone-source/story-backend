from app.config import settings

def absolute_media_url(path: str | None) -> str | None:
    if not path:
        return None

    # already absolute → leave it
    if path.startswith("http://") or path.startswith("https://"):
        return path

    return f"{settings.BASE_URL}{path}"
