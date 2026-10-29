from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from ma_receptionniste import db
from ma_receptionniste.db import create_db_and_tables
from ma_receptionniste.web.porte import PorteAuth
from ma_receptionniste.web.rendu import DOSSIER, secret
from ma_receptionniste.web.routes_auth import router as routeur_auth
from ma_receptionniste.web.routes_ecrans import router as routeur_ecrans
from ma_receptionniste.web.routes_fiche import router as routeur_fiche


@asynccontextmanager
async def _duree(_app: FastAPI):
    await run_in_threadpool(create_db_and_tables, db.engine)
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Ma Réceptionniste", lifespan=_duree)
    application.add_middleware(PorteAuth)
    application.add_middleware(SessionMiddleware, secret_key=secret())
    application.mount("/static", StaticFiles(directory=DOSSIER / "static"), name="static")
    application.include_router(routeur_auth)
    application.include_router(routeur_ecrans)
    application.include_router(routeur_fiche)
    return application


app = create_app()
