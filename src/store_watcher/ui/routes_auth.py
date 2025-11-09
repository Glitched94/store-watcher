import os
from pathlib import Path

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from ..db.users import upsert_user_google

router = APIRouter()


@router.get("/login")
async def login(request: Request) -> Response:
    oauth = request.app.state.oauth
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth", name="auth_callback")
async def auth_callback(request: Request) -> RedirectResponse:
    oauth = request.app.state.oauth
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    user = upsert_user_google(
        dbp,
        sub=str(userinfo.get("sub") or ""),
        email=str(userinfo.get("email") or ""),
        name=str(userinfo.get("name") or userinfo.get("email") or "User"),
        picture=(userinfo.get("picture") or None),
    )

    request.session["user"] = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    }
    return RedirectResponse("/")


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.pop("user", None)
    return RedirectResponse("/")
