"""Le planning compte les nuits, pas les matins de départ, et ignore les réservations annulées."""

from datetime import date

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from ma_receptionniste.consultations import nuits_entre, planning, segments
from ma_receptionniste.models import Chambre, Client, Reservation, Sejour, StatutReservation

NUIT_10 = date(2026, 10, 10)
NUIT_11 = date(2026, 10, 11)
DEPART_12 = date(2026, 10, 12)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_planning_compte_les_nuits_et_ignore_les_annulees(session: Session) -> None:
    # Du 10 au 12 : nuits du 10 et du 11. Le 12 est le matin du départ.
    client = Client(nom="Alice Dupont")
    chambre = Chambre(nom="101", position=1)
    autre = Chambre(nom="102", position=2)
    session.add(client)
    session.add(chambre)
    session.add(autre)
    session.commit()

    confirmee = Reservation(client_id=client.id)
    annulee = Reservation(client_id=client.id, statut=StatutReservation.annulee)
    session.add(confirmee)
    session.add(annulee)
    session.commit()
    session.add(Sejour(reservation_id=confirmee.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12))
    session.add(
        Sejour(
            reservation_id=annulee.id,
            chambre_id=autre.id,
            date_debut=NUIT_10,
            date_fin=DEPART_12,
            nom_client="Ne pas afficher",
        )
    )
    session.commit()

    data = planning(session, NUIT_10, date(2026, 10, 13))

    assert [chambre["nom"] for chambre in data["chambres"]] == ["101", "102"]
    assert len(data["sejours"]) == 1
    sejour = data["sejours"][0]
    assert sejour["nom"] == "Alice Dupont"
    assert sejour["nuits"] == [NUIT_10, NUIT_11]
    assert DEPART_12 not in sejour["nuits"]
    assert nuits_entre(NUIT_10, DEPART_12, NUIT_10, date(2026, 10, 13)) == [NUIT_10, NUIT_11]

    jours = [NUIT_10, NUIT_11, DEPART_12]
    blocs = segments(jours, [sejour])
    assert [bloc["longueur"] for bloc in blocs] == [2, 1]
    assert blocs[0]["sejour"]["reservation_id"] == confirmee.id
    assert blocs[1]["sejour"] is None
