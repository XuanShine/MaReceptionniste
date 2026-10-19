"""L'argent d'un séjour : nuits, remise, taxe de séjour, totaux et affichage en euros."""

from datetime import date

import pytest

from ma_receptionniste.facturation import centimes, format_euros, montant_ligne, nuits, taxe_sejour, totaux
from ma_receptionniste.models import Consommation, ModeReglement, Reglement, Sejour

ARRIVEE = date(2026, 10, 18)
DEPART = date(2026, 10, 20)


def sejour(**valeurs) -> Sejour:
    return Sejour(reservation_id=1, chambre_id=1, date_debut=ARRIVEE, date_fin=DEPART, **valeurs)


def test_nuits_exclut_le_matin_du_depart() -> None:
    assert nuits(ARRIVEE, DEPART) == 2
    assert nuits(ARRIVEE, date(2026, 10, 19)) == 1


@pytest.mark.parametrize(
    ("prix", "nuits_", "remise", "attendu"),
    [
        (6882, 2, 0, 13764),  # la ligne de la capture : 2 nuits à 68,82 €
        (6882, 2, 10, 12388),  # 123,876 € arrondi au centime supérieur
        (1005, 1, 10, 905),  # 9,045 € : le demi-centime monte
        (1006, 1, 10, 905),  # 9,054 € : descend
        (6882, 2, 100, 0),
    ],
)
def test_montant_ligne(prix: int, nuits_: int, remise: int, attendu: int) -> None:
    assert montant_ligne(prix, nuits_, remise) == attendu


def test_taxe_par_adulte_et_par_nuit() -> None:
    # 2,00 € par adulte et par nuit : 1 adulte, 2 nuits donne les 4,00 € de la capture.
    assert taxe_sejour(1, 2) == 400
    assert taxe_sejour(2, 3) == 1200


def test_totaux_et_solde() -> None:
    lignes = [
        sejour(prix_nuit_centimes=6882, adultes=1, enfants=0),
        # Les deux enfants ne paient pas la taxe de séjour.
        sejour(prix_nuit_centimes=10000, remise_pct=10, adultes=2, enfants=2),
    ]
    consommations = [Consommation(reservation_id=1, libelle="Petit-déjeuner", quantite=2, prix_unitaire_centimes=1400)]
    reglements = [
        Reglement(reservation_id=1, mode=ModeReglement.ota, montant_centimes=13764),
        Reglement(reservation_id=1, mode=ModeReglement.carte, montant_centimes=10000),
    ]

    resultat = totaux(lignes, consommations, reglements)

    assert resultat.hebergement == 13764 + 18000
    assert resultat.taxe_sejour == 400 + 800
    assert resultat.consommations == 2800
    assert resultat.total == 31764 + 1200 + 2800
    assert resultat.regle == 23764
    assert resultat.solde == 35764 - 23764


def test_solde_negatif_quand_le_client_a_trop_paye() -> None:
    resultat = totaux([], [], [Reglement(reservation_id=1, mode=ModeReglement.especes, montant_centimes=500)])

    assert resultat.total == 0
    assert resultat.solde == -500


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (13764, "137,64\u00a0€"),
        (123456, "1\u202f234,56\u00a0€"),
        (123456789, "1\u202f234\u202f567,89\u00a0€"),
        (5, "0,05\u00a0€"),
        (0, "0,00\u00a0€"),
        (-400, "-4,00\u00a0€"),
    ],
)
def test_format_euros(valeur: int, attendu: str) -> None:
    assert format_euros(valeur) == attendu


@pytest.mark.parametrize(("saisie", "attendu"), [(68.82, 6882), (0.1 + 0.2, 30), ("12.5", 1250), (3, 300)])
def test_centimes_depuis_une_saisie_en_euros(saisie, attendu: int) -> None:
    assert centimes(saisie) == attendu
