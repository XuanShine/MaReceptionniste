"""Note YAML des consommations ponctuelles : lecture, cases, totaux, incohérences."""

import copy
from datetime import date
from types import SimpleNamespace

import pytest

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
