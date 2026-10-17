import os

from nicegui import app, ui

from ma_receptionniste import pages  # noqa: F401
from ma_receptionniste.auth import AuthMiddleware
from ma_receptionniste.db import create_db_and_tables


def main(reload: bool = False) -> None:
    app.on_startup(create_db_and_tables)
    app.add_middleware(AuthMiddleware)
    ui.run(
        title="Ma Réceptionniste",
        language="fr",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
        storage_secret=os.environ.get("STORAGE_SECRET", "dev-secret-a-changer-en-production"),
        reload=reload,
        show=False,
    )
