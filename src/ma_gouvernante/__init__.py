import os

from nicegui import app, ui

from ma_gouvernante.comptes import demarrer
from ma_gouvernante.garde import AuthMiddleware


def main(reload: bool = False) -> None:
    from ma_gouvernante.pages import enregistrer_routes
    from ma_receptionniste.pages.theme import appliquer_theme

    enregistrer_routes()
    appliquer_theme()
    app.on_startup(demarrer)
    app.add_middleware(AuthMiddleware)
    ui.run(
        title="Ma Gouvernante",
        language="fr",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("GOUVERNANTE_PORT", os.environ.get("PORT", "8081"))),
        storage_secret=os.environ.get("GOUVERNANTE_STORAGE_SECRET", "gouvernante-dev-secret-a-changer"),
        # Cookie distinct de Ma Réceptionniste : les deux applis tournent sur le même hôte.
        session_middleware_kwargs={"session_cookie": "ma_gouvernante"},
        reload=reload,
        show=False,
    )
