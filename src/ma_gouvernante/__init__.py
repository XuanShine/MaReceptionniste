import os

from nicegui import app, ui

from ma_gouvernante.auth import AuthMiddleware, assurer_comptes
from ma_gouvernante.db import create_db_and_tables
from ma_gouvernante.signalements import dossier_media, nettoyer_photos_partielles


def main(reload: bool = False) -> None:
    # Les pages s'enregistrent à l'import. Le faire ici laisse un test les recharger après avoir vidé le routeur.
    from ma_gouvernante import pages  # noqa: F401
    from ma_gouvernante.pages.theme import appliquer_theme

    appliquer_theme()
    media = dossier_media()
    media.mkdir(parents=True, exist_ok=True)
    app.add_static_files("/gouvernante-media", str(media))

    def demarrer() -> None:
        create_db_and_tables()
        nettoyer_photos_partielles()
        assurer_comptes()

    app.on_startup(demarrer)
    app.add_middleware(AuthMiddleware)
    ui.run(
        title="Ma Gouvernante",
        language="fr",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("GOUVERNANTE_PORT", "8081")),
        storage_secret=os.environ.get("GOUVERNANTE_STORAGE_SECRET", "gouvernante-dev-secret-a-changer-en-production"),
        reload=reload,
        show=False,
    )
