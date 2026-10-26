import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from ma_receptionniste2.db import creer_tables, moteur_par_defaut
from ma_receptionniste2.routes.auth import router as auth_router
from ma_receptionniste2.routes.chambres import router as chambres_router
from ma_receptionniste2.routes.clients import router as clients_router
from ma_receptionniste2.routes.planning import router as planning_router
from ma_receptionniste2.routes.reservations import router as reservations_router
from ma_receptionniste2.web import RACINE, JetonInvalide, VersPage, page_simple


@asynccontextmanager
async def duree_de_vie(app: FastAPI):
    if app.state.engine is None:
        app.state.engine = moteur_par_defaut()
    creer_tables(app.state.engine)
    yield


def create_app(engine=None, aujourd_hui=None, secret: str | None = None) -> FastAPI:
    app = FastAPI(
        title="Ma réceptionniste",
        lifespan=duree_de_vie,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.engine = engine
    app.state.aujourd_hui = aujourd_hui or date.today
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret or os.environ.get("STORAGE_SECRET", "dev-secret-a-changer-en-production"),
        session_cookie="reception_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=False,
    )
    app.mount("/static", StaticFiles(directory=str(RACINE / "static")), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    app.include_router(auth_router)
    app.include_router(planning_router)
    app.include_router(chambres_router)
    app.include_router(clients_router)
    app.include_router(reservations_router)

    @app.exception_handler(VersPage)
    async def _rediriger(request, exc: VersPage):
        if request.headers.get("hx-request"):
            return Response(status_code=204, headers={"HX-Redirect": exc.url})
        return RedirectResponse(exc.url, status_code=303)

    @app.exception_handler(JetonInvalide)
    async def _jeton(request, _exc: JetonInvalide):
        return page_simple(
            request,
            titre="Action expirée",
            message="Cette action a expiré. Rechargez la page.",
            href="/",
            lien="Retour à l'accueil",
            statut=403,
        )

    @app.exception_handler(HTTPException)
    async def _http(request, exc: HTTPException):
        if exc.status_code == 404:
            return page_simple(
                request,
                titre="Page introuvable",
                message="Cette page n'existe pas.",
                href="/",
                lien="Retour à l'accueil",
                statut=404,
            )
        return page_simple(
            request,
            titre="Requête refusée",
            message="La requête n'a pas abouti.",
            href="/",
            lien="Retour à l'accueil",
            statut=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request, _exc: RequestValidationError):
        return page_simple(
            request,
            titre="Page introuvable",
            message="Cette page n'existe pas.",
            href="/",
            lien="Retour à l'accueil",
            statut=404,
        )

    return app


app = create_app()
