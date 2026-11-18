from copy import deepcopy
from datetime import date, timedelta

import pytest
from sqlalchemy import event
from sqlmodel import Session

from ma_receptionniste.disponibilites import disponibilites_par_type, matrice_disponibilites
from ma_receptionniste.models import Chambre, Client, EtatChambre, Reservation, Sejour, StatutReservation, TypeChambre
from ma_receptionniste.sejours import chambre_libre

DEBUT = date(2026, 11, 15)
FIN = date(2026, 11, 18)
DATES = [date(2026, 11, jour) for jour in (15, 16, 17)]


@pytest.fixture
def catalogue(base) -> dict:
    with Session(base) as session:
        double = TypeChambre(libelle="Double", disponibilite=99)
        simple = TypeChambre(libelle="Simple")
        vide = TypeChambre(libelle="Sans chambre")
        session.add_all([double, simple, vide])
        session.flush()
        chambres = [
            Chambre(nom="102", position=1, type_chambre_id=double.id, etat=EtatChambre.pret),
            Chambre(nom="101", position=1, type_chambre_id=double.id, etat=EtatChambre.non_pret),
            Chambre(nom="201", position=2, type_chambre_id=simple.id),
            Chambre(nom="301", position=3),
        ]
        session.add_all(chambres)
        session.commit()
        return {
            "types": {type_.libelle: type_.id for type_ in (double, simple, vide)},
            "chambres": {chambre.nom: chambre.id for chambre in chambres},
        }


def ajouter_sejour(base, chambre_id, debut=DEBUT, fin=FIN, statut=StatutReservation.confirmee) -> None:
    with Session(base) as session:
        client = Client(nom="Dupont")
        session.add(client)
        session.flush()
        reservation = Reservation(client_id=client.id, statut=statut)
        session.add(reservation)
        session.flush()
        session.add(Sejour(reservation_id=reservation.id, chambre_id=chambre_id, date_debut=debut, date_fin=fin))
        session.commit()


def test_matrice_libre_triee_avec_metadonnees_et_sans_ecriture(base, catalogue) -> None:
    ecritures = []

    def observer(connexion, curseur, requete, parametres, contexte, multiple):
        if not requete.lstrip().upper().startswith("SELECT"):
            ecritures.append(requete)

    event.listen(base, "before_cursor_execute", observer)
    try:
        matrice = matrice_disponibilites(DEBUT, FIN)
    finally:
        event.remove(base, "before_cursor_execute", observer)

    assert ecritures == []
    assert matrice["dates"] == DATES
    assert [chambre["nom"] for chambre in matrice["chambres"]] == ["101", "102", "201", "301"]
    assert matrice["chambres"][0] == {
        "id": catalogue["chambres"]["101"],
        "nom": "101",
        "type_chambre_id": catalogue["types"]["Double"],
        "type_chambre": "Double",
    }
    assert matrice["chambres"][-1]["type_chambre_id"] is None
    assert matrice["chambres"][-1]["type_chambre"] is None
    assert matrice["valeurs"] == [[1, 1, 1]] * 4
    assert all(type(valeur) is int for ligne in matrice["valeurs"] for valeur in ligne)


@pytest.mark.parametrize("statut", list(StatutReservation))
def test_statuts_et_jour_du_depart(base, catalogue, statut) -> None:
    ajouter_sejour(base, catalogue["chambres"]["101"], fin=date(2026, 11, 17), statut=statut)

    matrice = matrice_disponibilites(DEBUT, FIN)

    assert matrice["valeurs"][0] == ([1, 1, 1] if statut == StatutReservation.annulee else [0, 0, 1])
    assert matrice["valeurs"][1:] == [[1, 1, 1]] * 3


@pytest.mark.parametrize(
    ("debut", "fin", "attendu"),
    [
        (date(2026, 11, 14), date(2026, 11, 19), [0, 0, 0]),
        (date(2026, 11, 14), date(2026, 11, 16), [0, 1, 1]),
        (date(2026, 11, 17), date(2026, 11, 19), [1, 1, 0]),
        (date(2026, 11, 14), DEBUT, [1, 1, 1]),
        (FIN, date(2026, 11, 19), [1, 1, 1]),
    ],
)
def test_sejours_aux_bornes(base, catalogue, debut, fin, attendu) -> None:
    ajouter_sejour(base, catalogue["chambres"]["101"], debut, fin)

    assert matrice_disponibilites(DEBUT, FIN)["valeurs"][0] == attendu


def test_chevauchements_restent_binaires(base, catalogue) -> None:
    ajouter_sejour(base, catalogue["chambres"]["101"], DEBUT, date(2026, 11, 17))
    ajouter_sejour(base, catalogue["chambres"]["101"], date(2026, 11, 16), FIN)

    assert matrice_disponibilites(DEBUT, FIN)["valeurs"][0] == [0, 0, 0]


@pytest.mark.parametrize("nombre_nuits", [1, 30, 365])
def test_trois_requetes_independamment_de_la_periode(base, catalogue, nombre_nuits) -> None:
    ajouter_sejour(base, catalogue["chambres"]["101"])
    requetes = []

    def observer(connexion, curseur, requete, parametres, contexte, multiple):
        requetes.append(requete)

    event.listen(base, "before_cursor_execute", observer)
    try:
        matrice_disponibilites(DEBUT, DEBUT + timedelta(days=nombre_nuits))
    finally:
        event.remove(base, "before_cursor_execute", observer)

    assert len(requetes) == 3
    assert all(requete.lstrip().upper().startswith("SELECT") for requete in requetes)


def test_matrice_identique_aux_verifications_individuelles(base, catalogue) -> None:
    for index, statut in enumerate(StatutReservation):
        chambre_id = catalogue["chambres"][["101", "102", "201"][index % 3]]
        debut = DEBUT + timedelta(days=index - 2)
        ajouter_sejour(base, chambre_id, debut, debut + timedelta(days=4), statut)
    ajouter_sejour(base, catalogue["chambres"]["101"], DEBUT, DEBUT + timedelta(days=2))
    ajouter_sejour(base, catalogue["chambres"]["101"], DEBUT + timedelta(days=2), FIN)
    matrice = matrice_disponibilites(DEBUT, DEBUT + timedelta(days=10))

    with Session(base) as session:
        attendu = [
            [int(chambre_libre(session, chambre["id"], jour, jour + timedelta(days=1))) for jour in matrice["dates"]]
            for chambre in matrice["chambres"]
        ]

    assert matrice["valeurs"] == attendu


def test_agregation_par_type_pure_et_sans_acces_base(base, catalogue) -> None:
    ajouter_sejour(base, catalogue["chambres"]["101"], DEBUT, date(2026, 11, 17))
    ajouter_sejour(base, catalogue["chambres"]["201"], date(2026, 11, 16), FIN)
    matrice = matrice_disponibilites(DEBUT, FIN)
    avant = deepcopy(matrice)

    def refuser_requete(*args):
        pytest.fail("L'agrégation ne doit pas accéder à la base")

    event.listen(base, "before_cursor_execute", refuser_requete)
    try:
        resultat = disponibilites_par_type(matrice)
    finally:
        event.remove(base, "before_cursor_execute", refuser_requete)

    assert resultat["dates"] == DATES
    assert resultat["types"] == matrice["types"]
    assert {type_["id"]: ligne for type_, ligne in zip(resultat["types"], resultat["valeurs"], strict=True)} == {
        catalogue["types"]["Double"]: [1, 1, 2],
        catalogue["types"]["Simple"]: [1, 0, 0],
        catalogue["types"]["Sans chambre"]: [0, 0, 0],
    }
    assert matrice == avant
    resultat["dates"].clear()
    resultat["types"][0]["libelle"] = "Modifié"
    resultat["valeurs"][0][0] = 99
    assert matrice == avant


def test_agregation_regroupe_par_identifiant_et_non_libelle() -> None:
    matrice = {
        "dates": [DEBUT],
        "types": [{"id": 1, "libelle": "Même nom"}, {"id": 2, "libelle": "Même nom"}],
        "chambres": [{"type_chambre_id": 1}, {"type_chambre_id": 2}],
        "valeurs": [[0], [1]],
    }

    assert disponibilites_par_type(matrice)["valeurs"] == [[0], [1]]


def test_sans_chambre_les_types_restent_a_zero(base) -> None:
    with Session(base) as session:
        session.add(TypeChambre(libelle="Double"))
        session.commit()

    matrice = matrice_disponibilites(DEBUT, FIN)

    assert matrice["chambres"] == []
    assert matrice["valeurs"] == []
    assert disponibilites_par_type(matrice)["valeurs"] == [[0, 0, 0]]


def test_base_vide(base) -> None:
    matrice = matrice_disponibilites(DEBUT, FIN)

    assert matrice == {"dates": DATES, "types": [], "chambres": [], "valeurs": []}
    assert disponibilites_par_type(matrice) == {"dates": DATES, "types": [], "valeurs": []}


@pytest.mark.parametrize("fin", [DEBUT, date(2026, 11, 14)])
def test_periode_invalide(base, fin) -> None:
    with pytest.raises(ValueError, match="date de fin"):
        matrice_disponibilites(DEBUT, fin)
