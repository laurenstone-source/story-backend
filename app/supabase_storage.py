import os
from supabase import create_client

# Supabase client (created once)
supabase = create_client(
    os.environ["https://blqddscofxulsffddowu.supabase.co"],
    os.environ["sb_publishable_oUq-zVmPeGFTY8L9x0by1w_QN0RcaxM"],
)

BUCKET = "media"


def upload_file(contents: bytes, path: str, content_type: str) -> str:
    """
    Uploads bytes to Supabase Storage and returns the public URL.
    """

    supabase.storage.from_(BUCKET).upload(
        path,
        contents,
        {"content-type": content_type},
    )

    return supabase.storage.from_(BUCKET).get_public_url(path)
