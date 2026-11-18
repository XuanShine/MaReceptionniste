from datetime import date, timedelta

import pytest
from nicegui import ui
from nicegui.testing import User
from sqlmodel import Session

from ma_receptionniste.auth import register_user
from ma_receptionniste.models import Chambre, Client, Reservation, Sejour, TypeChambre


@pytest.fixture
def catalogue_disponibilites(base) -> tuple[int, int]:
    with Session(base) as session:
        double = TypeChambre(libelle="Double")
        suite = TypeChambre(libelle="Suite")
        client = Client(nom="Occupant")
        session.add_all([double, suite, client])
        session.flush()
        chambre = Chambre(nom="101", position=1, type_chambre_id=double.id)
        session.add_all(
            [
                chambre,
                Chambre(nom="102", position=2, type_chambre_id=double.id),
                Chambre(nom="301", position=3),
            ]
        )
        reservation = Reservation(client_id=client.id)
        session.add(reservation)
        session.flush()
        session.add(
            Sejour(
                reservation_id=reservation.id,
                chambre_id=chambre.id,
                date_debut=date.today(),
                date_fin=date.today() + timedelta(days=1),
            )
        )
        session.commit()
        return double.id, suite.id


async def _ouvrir(user: User, base) -> None:
    with Session(base) as session:
        register_user(session, "disponibilites@hotel-panorama.fr", "Réception", "panorama-disponibilites")
    await user.open("/login")
    user.find("Email").type("disponibilites@hotel-panorama.fr")
    user.find("Mot de passe").type("panorama-disponibilites")
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)
    assert any(lien.props.get("href") == "/disponibilites" for lien in user.find(ui.link).elements)
    await user.open("/disponibilites")
    await user.should_see("365 nuits", retries=30)


async def test_periode_par_defaut_et_types_en_colonnes(user: User, base, catalogue_disponibilites) -> None:
    double_id, suite_id = catalogue_disponibilites
    await _ouvrir(user, base)
    debut = next(iter(user.find(marker="disponibilites-debut").elements))
    fin = next(iter(user.find(marker="disponibilites-fin").elements))
    assert debut.value == date.today().isoformat()
    assert fin.value == (date.today() + timedelta(days=365)).isoformat()
    tableau = next(iter(user.find(marker="tableau-disponibilites").elements))
    assert [colonne["label"] for colonne in tableau.columns] == ["Date", "Double", "Suite"]
    assert len(tableau.rows) == 365
    assert tableau.rows[0] == {
        "id": date.today().isoformat(),
        "date": date.today().strftime("%d/%m/%Y"),
        f"type_{double_id}": 1,
        f"type_{suite_id}": 0,
    }
    assert tableau.rows[1][f"type_{double_id}"] == 2
    assert tableau.rows[-1]["id"] == (date.today() + timedelta(days=364)).isoformat()


async def test_changer_la_periode(user: User, base, catalogue_disponibilites) -> None:
    await _ouvrir(user, base)
    debut = date.today() + timedelta(days=1)
    fin = debut + timedelta(days=2)
    user.find(marker="disponibilites-debut").clear().type(debut.isoformat())
    user.find(marker="disponibilites-fin").clear().type(fin.isoformat())
    user.find("Afficher").click()
    await user.should_see("2 nuits")
    tableau = next(iter(user.find(marker="tableau-disponibilites").elements))
    assert [ligne["id"] for ligne in tableau.rows] == [
        debut.isoformat(),
        (debut + timedelta(days=1)).isoformat(),
    ]


@pytest.mark.parametrize("decalage", [0, -1])
async def test_periode_invalide_conserve_le_tableau(user: User, base, catalogue_disponibilites, decalage) -> None:
    await _ouvrir(user, base)
    tableau = next(iter(user.find(marker="tableau-disponibilites").elements))
    avant = list(tableau.rows)
    user.find(marker="disponibilites-fin").clear().type((date.today() + timedelta(days=decalage)).isoformat())
    user.find("Afficher").click()
    await user.should_see("La date de fin doit être après la date de début")
    assert tableau.rows == avant


async def test_date_manquante(user: User, base) -> None:
    await _ouvrir(user, base)
    user.find(marker="disponibilites-debut").clear()
    user.find("Afficher").click()
    await user.should_see("Renseignez deux dates valides")


async def test_aucun_type(user: User, base) -> None:
    await _ouvrir(user, base)
    await user.should_see("Aucun type de chambre configuré.")
    await user.should_not_see(marker="tableau-disponibilites")
