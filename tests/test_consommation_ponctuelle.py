"""Note YAML des consommations ponctuelles : lecture, cases, totaux, incohérences, journal."""

import copy
from datetime import date
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from ma_receptionniste.consommation_ponctuelle import (
    NoteIllisible,
    basculer,
    ecrire,
    incoherences,
    jours_du_sejour,
    lire,
    totaux,
    tout_cocher,
    tout_retirer,
)
from ma_receptionniste.consultations import fiche_sejour
from ma_receptionniste.db import get_session
from ma_receptionniste.models import Reservation, User
from ma_receptionniste.saisie import (
    OperationPonctuelle,
    creer_client,
    creer_reservation,
    modifier_consommation_ponctuelle,
)

EXEMPLE = """\
Consommation:
  Chambre_12:
    Petit-déjeuner:
      2026-11-11: 2
      2026-11-12: 2
"""

JOUR = date(2026, 11, 11)
LENDEMAIN = date(2026, 11, 12)
SURPLUS = date(2026, 11, 13)


def test_le_yaml_relu_apres_ecriture_est_identique() -> None:
    donnees = {
        "Consommation": {
            "Chambre_2": {"Taxe de séjour": {LENDEMAIN: 1}},
            "Chambre_12": {"Petit-déjeuner": {LENDEMAIN: 2, JOUR: 2}},
        }
    }

    texte = ecrire(donnees)
    assert lire(texte) == {
        "Consommation": {
            "Chambre_12": {"Petit-déjeuner": {JOUR: 2, LENDEMAIN: 2}},
            "Chambre_2": {"Taxe de séjour": {LENDEMAIN: 1}},
        }
    }
    assert ecrire(lire(texte)) == texte
    assert ecrire(lire(EXEMPLE)) == EXEMPLE
    assert lire(None) == {}
    assert lire("  \n") == {}
    assert ecrire({}) == ""

    with pytest.raises(NoteIllisible):
        lire("[")
    with pytest.raises(NoteIllisible):
        lire("Consommation: [1]\n")
    with pytest.raises(NoteIllisible):
        lire("Consommation:\n  Chambre_12:\n    Petit-déjeuner:\n      2026-11-11: oui\n")


def test_cocher_decocher_et_vider_les_branches() -> None:
    vide: dict = {}
    un = basculer(vide, "12", "Petit-déjeuner", JOUR, 2)
    deux = basculer(un, "12", "Ancien buffet", JOUR, 1)
    retire = basculer(deux, "12", "Petit-déjeuner", JOUR, None)

    assert vide == {}
    assert un == {"Consommation": {"Chambre_12": {"Petit-déjeuner": {JOUR: 2}}}}
    assert retire == {"Consommation": {"Chambre_12": {"Ancien buffet": {JOUR: 1}}}}
    assert basculer(retire, "12", "Ancien buffet", JOUR, None) == {}
    assert jours_du_sejour({"date_debut": JOUR, "date_fin": LENDEMAIN}) == [JOUR, LENDEMAIN]


def test_tout_cocher_et_tout_retirer() -> None:
    origine = basculer({}, "12", "Ancien buffet", JOUR, 1)
    avant = copy.deepcopy(origine)

    coche = tout_cocher(origine, "12", "Petit-déjeuner", [LENDEMAIN, JOUR], 2)
    assert coche["Consommation"]["Chambre_12"]["Petit-déjeuner"] == {JOUR: 2, LENDEMAIN: 2}
    assert coche["Consommation"]["Chambre_12"]["Ancien buffet"] == {JOUR: 1}
    assert origine == avant

    assert tout_retirer(coche, "12", "Petit-déjeuner") == origine
    assert tout_retirer(origine, "12", "Ancien buffet") == {}


def test_les_totaux_additionnent_les_jours() -> None:
    donnees = lire(EXEMPLE)
    donnees = basculer(donnees, "12", "Taxe de séjour", JOUR, 1)

    assert totaux(donnees) == {("Chambre_12", "Petit-déjeuner"): 4, ("Chambre_12", "Taxe de séjour"): 1}
    assert totaux({}) == {}


def test_incoherences_sur_un_changement_de_chambre_et_de_dates() -> None:
    sejour = SimpleNamespace(date_debut=JOUR, date_fin=LENDEMAIN, chambre=SimpleNamespace(nom="12"))
    donnees = tout_cocher({}, "12", "Petit-déjeuner", [JOUR, SURPLUS], 2)
    donnees = basculer(donnees, "12", "Bar", SURPLUS, 1)

    assert incoherences(donnees, [sejour]) == [
        "Bar · Chambre 12 · 13/11/2026 : hors du séjour",
        "Petit-déjeuner · Chambre 12 · 13/11/2026 : hors du séjour",
    ]
    assert incoherences(donnees, [{"chambre_nom": "12", "date_debut": JOUR, "date_fin": SURPLUS}]) == []

    autre_chambre = SimpleNamespace(date_debut=JOUR, date_fin=SURPLUS, chambre=SimpleNamespace(nom="8"))
    assert incoherences(donnees, [autre_chambre]) == [
        "Bar · Chambre 12 : chambre absente des séjours",
        "Petit-déjeuner · Chambre 12 : chambre absente des séjours",
    ]


@pytest.fixture
def reception(base) -> int:
    with Session(base) as session:
        user = User(email="ponctuelle@hotel-panorama.fr", nom="Réception", password_hash="x")
        session.add(user)
        session.commit()
        return user.id


def _poser(reservation_id: int, brut: str) -> None:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        assert reservation is not None
        reservation.notes_internes = brut
        session.add(reservation)
        session.commit()


@pytest.mark.parametrize("brut", ["[", "Consommation: [1]\n"])
def test_une_note_illisible_n_est_jamais_ecrasee(brut: str, reception: int) -> None:
    reservation_id = creer_reservation(creer_client(f"NOTE {brut!r}"))
    _poser(reservation_id, brut)

    with pytest.raises(NoteIllisible):
        modifier_consommation_ponctuelle(
            reservation_id,
            OperationPonctuelle("basculer", "12", "Petit-déjeuner", jour=JOUR, nombre=2),
            reception,
        )

    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        assert reservation is not None
        assert reservation.notes_internes == brut
    assert fiche_sejour(reservation_id)["historique"] == []
    assert fiche_sejour(reservation_id)["reservation"]["notes_internes"] == brut


def test_l_historique_decrit_chaque_changement(reception: int) -> None:
    reservation_id = creer_reservation(creer_client("LE CLOEREC"))
    operation = OperationPonctuelle("basculer", "12", "Petit-déjeuner", jour=JOUR, nombre=2)

    modifier_consommation_ponctuelle(reservation_id, operation, reception)
    modifier_consommation_ponctuelle(reservation_id, operation, reception)
    modifier_consommation_ponctuelle(
        reservation_id,
        OperationPonctuelle("basculer", "12", "Petit-déjeuner", jour=LENDEMAIN, nombre=2),
        reception,
    )

    fiche = fiche_sejour(reservation_id)
    assert [(note["description"], note["auteur"]) for note in fiche["historique"]] == [
        ("Petit-déjeuner · Chambre 12 · 12/11 : 2", "Réception"),
        ("Petit-déjeuner · Chambre 12 · 11/11 : 2", "Réception"),
    ]
    assert lire(fiche["reservation"]["notes_internes"]) == lire(EXEMPLE)
    assert fiche["consommations"] == []

    modifier_consommation_ponctuelle(
        reservation_id,
        OperationPonctuelle("tout_cocher", "12", "Petit-déjeuner", jours=(JOUR, LENDEMAIN, SURPLUS), nombre=3),
        reception,
    )
    modifier_consommation_ponctuelle(
        reservation_id,
        OperationPonctuelle("tout_retirer", "12", "Petit-déjeuner"),
        reception,
    )
    fiche = fiche_sejour(reservation_id)
    assert [note["description"] for note in fiche["historique"][:2]] == [
        "Petit-déjeuner · Chambre 12 · tout retiré",
        "Petit-déjeuner · Chambre 12 · tout sélectionné : 3",
    ]
    assert fiche["reservation"]["notes_internes"] is None
    assert fiche["consommations"] == []
