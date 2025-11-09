from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth


def build_oauth() -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth
