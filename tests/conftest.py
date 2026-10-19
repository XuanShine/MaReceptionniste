import atexit
import os
import shutil
import tempfile

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

# db.py lit DATABASE_URL à l'import : les tests ne doivent jamais ouvrir ma_receptionniste.db.
_DOSSIER = tempfile.mkdtemp(prefix="ma-receptionniste-tests-")
atexit.register(shutil.rmtree, _DOSSIER, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_DOSSIER}/app.db"

from ma_receptionniste import db  # noqa: E402


@pytest.fixture
def base(monkeypatch: pytest.MonkeyPatch):
    """Base en mémoire derrière get_session(), pour appeler saisie et consultations comme le font les pages."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    db.create_db_and_tables(engine)
    monkeypatch.setattr(db, "engine", engine)
    return engine
