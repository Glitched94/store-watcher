from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from ..auth import build_oauth
from . import routes_admin, routes_auth, routes_main


def create_app(dotenv_path: str | None = None) -> FastAPI:
    load_dotenv(dotenv_path=dotenv_path)

    app = FastAPI(title="Store Watcher UI")

    # --- middleware ---
    secret_key = os.getenv("SECRET_KEY", "dev-please-change-me")
    app.add_middleware(SessionMiddleware, secret_key=secret_key, same_site="lax", https_only=False)

    # --- oauth ---
    app.state.oauth = build_oauth()

    # --- include routes ---
    app.include_router(routes_main.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_admin.router)

    return app
