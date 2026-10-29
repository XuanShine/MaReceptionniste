"""Écritures de la fiche séjour, appelées comme le font les pages, et ce que la fiche relit ensuite."""

from datetime import date

import pytest
from sqlmodel import Session

from ma_receptionniste.consultations import StatutSejour, fiche_sejour, lister_reservations
from ma_receptionniste.models import ModeReglement, User
from ma_receptionniste.saisie import (
    FacturationImpossible,
    FicheInvalide,
    ajouter_consommation,
    ajouter_reglement,
    ajouter_sejour,
    annuler_reservation,
    creer_chambre,
    creer_client,
    creer_reservation,
    enregistrer_fiche,
    facturer,
    modifier_sejour,
    supprimer_sejour,
)
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide

ARRIVEE = date(2026, 10, 18)
DEPART = date(2026, 10, 20)
JOUR = date(2026, 10, 19)


@pytest.fixture
def reception(base) -> int:
    with Session(base) as session:
        user = User(email="reception@hotel-panorama.fr", nom="Réception", password_hash="x")
        session.add(user)
        session.commit()
        return user.id


def nouvelle_reservation() -> int:
    return creer_reservation(creer_client("LE CLOEREC"))


def descriptions(reservation_id: int) -> list[str]:
    return [note["description"] for note in fiche_sejour(reservation_id, JOUR)["historique"]]


def test_enregistrer_fiche_ecrit_et_journalise_les_champs_changes(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    modifies = enregistrer_fiche(
        reservation_id,
        reception,
        {
            "nom": "Bénédicte LE CLOEREC",
            "pays": "France",
            "partenaire": "  Booking.com ",
            "traitee": False,
            "notes": "arrivé : 19h20",
            "notes_internes": "",
        },
    )

    assert modifies == ["Nom", "Pays de nat.", "Partenaire", "Notes"]
    fiche = fiche_sejour(reservation_id, JOUR)
    assert fiche["client"]["nom"] == "Bénédicte LE CLOEREC"
    assert fiche["client"]["nom_complet"] == "Bénédicte LE CLOEREC"
    assert fiche["client"]["pays"] == "France"
    assert fiche["reservation"]["partenaire"] == "Booking.com"
    assert fiche["reservation"]["notes"] == "arrivé : 19h20"
    assert fiche["reservation"]["notes_internes"] is None
    assert [(note["description"], note["auteur"]) for note in fiche["historique"]] == [
        ("Fiche modifiée : Nom, Pays de nat., Partenaire, Notes", "Réception")
    ]


def test_enregistrer_fiche_sans_changement_ne_journalise_rien(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    enregistrer_fiche(reservation_id, reception, {"partenaire": "Expedia", "traitee": True})

    assert enregistrer_fiche(reservation_id, reception, {"partenaire": "Expedia ", "traitee": True}) == []
    assert descriptions(reservation_id) == ["Fiche modifiée : Partenaire, Traité"]


def test_enregistrer_fiche_refuse_un_nom_vide(base) -> None:
    reservation_id = nouvelle_reservation()

    with pytest.raises(FicheInvalide):
        enregistrer_fiche(reservation_id, None, {"nom": "  "})
    assert fiche_sejour(reservation_id, JOUR)["client"]["nom"] == "LE CLOEREC"


def test_facturer_numerote_a_la_suite_une_seule_fois(reception: int) -> None:
    premiere = nouvelle_reservation()
    seconde = nouvelle_reservation()

    assert facturer(premiere, reception) == 1
    assert facturer(seconde, reception) == 2
    assert facturer(premiere, reception) == 1

    fiche = fiche_sejour(premiere, JOUR)
    assert fiche["reservation"]["numero_facture"] == 1
    assert fiche["reservation"]["date_facture"] == date.today()
    assert descriptions(premiere) == ["Facture n° 1 émise"]


def test_facturer_refuse_une_reservation_annulee(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    annuler_reservation(reservation_id, reception)

    with pytest.raises(FacturationImpossible):
        facturer(reservation_id, reception)
    assert fiche_sejour(reservation_id, JOUR)["reservation"]["numero_facture"] is None


def test_la_fiche_compte_et_totalise_comme_la_capture(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    chambre_id = creer_chambre("406", 406, "Single BB")
    ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, prix_nuit_centimes=6882, user_id=reception)
    ajouter_consommation(reservation_id, "Petit-déjeuner", 1, 1400, reception)
    ajouter_reglement(reservation_id, ModeReglement.ota, 13764, reception)

    fiche = fiche_sejour(reservation_id, JOUR)

    assert fiche["statut_sejour"] == StatutSejour.en_cours
    assert (fiche["debut"], fiche["fin"]) == (ARRIVEE, DEPART)
    [ligne] = fiche["lignes"]
    assert (ligne["type_chambre"], ligne["chambre_nom"], ligne["nuits"]) == ("Single BB", "406", 2)
    assert (ligne["adultes"], ligne["enfants"], ligne["taxe"], ligne["montant"]) == (1, 0, 400, 13764)
    assert fiche["compteurs"] == {"reservations": 1, "consommations": 1, "reglements": 1, "modifications": 3}
    assert fiche["totaux"].total == 13764 + 400 + 1400
    assert fiche["totaux"].solde == 1800
    assert descriptions(reservation_id) == [
        "Règlement OTA (prépayé) : 137,64\u00a0€",
        "Consommation ajoutée : 1 × Petit-déjeuner (14,00\u00a0€)",
        "Séjour ajouté : chambre 406 du 18/10/2026 au 20/10/2026",
    ]
    [ligne_liste] = lister_reservations(JOUR)
    assert (ligne_liste["chambres"], ligne_liste["nuits"], ligne_liste["total"]) == ("406", 2, 15564)
    assert ligne_liste["statut"] == StatutSejour.en_cours


def test_modifier_puis_supprimer_une_ligne(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    chambre_id = creer_chambre("406", 406)
    autre_id = creer_chambre("407", 407)
    sejour_id = ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, user_id=reception)
    ajouter_sejour(nouvelle_reservation(), autre_id, ARRIVEE, DEPART)

    with pytest.raises(ChambreOccupee):
        modifier_sejour(sejour_id, autre_id, ARRIVEE, DEPART, 1, 0, 6882, 0, None, reception)

    modifier_sejour(sejour_id, chambre_id, ARRIVEE, date(2026, 10, 21), 2, 1, 6882, 10, "M. Martin", reception)
    [ligne] = fiche_sejour(reservation_id, JOUR)["lignes"]
    assert (ligne["nuits"], ligne["adultes"], ligne["enfants"], ligne["remise_pct"]) == (3, 2, 1, 10)
    assert ligne["nom_client"] == "M. Martin"
    assert ligne["montant"] == 18581  # 3 × 68,82 € moins 10 % = 185,814 €
    assert ligne["taxe"] == 1200  # l'enfant est exonéré

    supprimer_sejour(sejour_id, reception)
    fiche = fiche_sejour(reservation_id, JOUR)
    assert fiche["lignes"] == []
    assert descriptions(reservation_id)[:2] == [
        "Séjour supprimé : chambre 406 du 18/10/2026 au 21/10/2026",
        "Séjour modifié : chambre 406 du 18/10/2026 au 21/10/2026",
    ]


def test_remise_hors_bornes_refusee(base) -> None:
    reservation_id = nouvelle_reservation()
    chambre_id = creer_chambre("406", 406)

    with pytest.raises(SejourInvalide):
        ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, prix_nuit_centimes=6882, remise_pct=120)
    assert fiche_sejour(reservation_id, JOUR)["lignes"] == []


def test_annuler_journalise_une_seule_fois(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    annuler_reservation(reservation_id, reception)
    annuler_reservation(reservation_id, reception)

    fiche = fiche_sejour(reservation_id, JOUR)
    assert fiche["statut_sejour"] == StatutSejour.annule
    assert descriptions(reservation_id) == ["Réservation annulée"]
