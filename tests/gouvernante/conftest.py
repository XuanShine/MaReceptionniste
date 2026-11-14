import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlmodel import Session, select

# db.py lit GOUVERNANTE_DATABASE_URL à l'import. Le poser avant, sans toucher DATABASE_URL.
_DOSSIER = tempfile.mkdtemp(prefix="ma-gouvernante-tests-")
os.environ["GOUVERNANTE_DATABASE_URL"] = f"sqlite:///{_DOSSIER}/gouvernante.db"
os.environ["GOUVERNANTE_MEDIA"] = str(Path(_DOSSIER) / "media")

from ma_gouvernante import db  # noqa: E402
from ma_gouvernante.auth import assurer_comptes, authenticate  # noqa: E402
from ma_gouvernante.models import GouvernanteModel, Historique  # noqa: E402

atexit.register(shutil.rmtree, _DOSSIER, ignore_errors=True)


@pytest.fixture(autouse=True)
def base_vide():
    GouvernanteModel.metadata.drop_all(db.engine)
    db.create_db_and_tables()
    media = Path(os.environ["GOUVERNANTE_MEDIA"])
    if media.exists():
        shutil.rmtree(media)
    media.mkdir()
    yield


@pytest.fixture
def compte():
    def ouvrir_compte(email: str) -> dict:
        assurer_comptes()
        utilisateur = authenticate(email, "panorama")
        assert utilisateur is not None
        return utilisateur

    return ouvrir_compte


@pytest.fixture
def descriptions():
    def lire() -> list[str]:
        with Session(db.engine) as session:
            rows = session.exec(select(Historique).order_by(Historique.id)).all()
            return [row.description for row in rows]

    return lire
