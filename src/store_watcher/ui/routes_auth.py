from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse, Response

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
    request.session["user"] = {
        "sub": userinfo.get("sub"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }
    return RedirectResponse("/")


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.pop("user", None)
    return RedirectResponse("/")
