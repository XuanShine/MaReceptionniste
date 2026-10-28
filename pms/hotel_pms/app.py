"""Application FastAPI."""

import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from hotel_pms.auth import AuthRequise
from hotel_pms.db import DB_PATH, creer_engine, initialiser, preparer_url
from hotel_pms.routes.auth import router as auth_router
from hotel_pms.routes.pages import router as pages_router
from hotel_pms.routes.sejours import router as sejours_router
from hotel_pms.templating import STATIC


def create_app(database_url: str | None = None, secret: str | None = None) -> FastAPI:
    url = preparer_url(database_url or os.environ.get("PMS_DATABASE_URL") or f"sqlite:///{DB_PATH}")
    cle = secret or os.environ.get("PMS_SECRET") or "dev-secret-panorama-change-me"
    engine = creer_engine(url)
    initialiser(engine)

    app = FastAPI(title="Panorama Réception", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.database_url = url
    app.state.db_path = url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else url

    @app.middleware("http")
    async def proteger(request: Request, call_next):
        chemin = request.url.path
        if chemin == "/login" or chemin.startswith("/static/") or chemin == "/favicon.ico":
            return await call_next(request)
        if not request.session.get("user_id"):
            if request.headers.get("HX-Request") == "true":
                return Response(status_code=401, headers={"HX-Redirect": "/login"})
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    @app.exception_handler(AuthRequise)
    async def _auth_requise(request: Request, _exc: AuthRequise):
        if request.headers.get("HX-Request") == "true":
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    app.include_router(auth_router)
    app.include_router(pages_router)
    app.include_router(sejours_router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_middleware(
        SessionMiddleware,
        secret_key=cle,
        session_cookie="pms_session",
        max_age=60 * 60 * 12,
        same_site="lax",
        https_only=False,
    )
    return app
