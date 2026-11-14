import pytest

from ma_gouvernante.chambres import changer_etat, creer_chambre
from ma_gouvernante.menage import (
    RetraitRefuse,
    ajouter_chambres_en_service,
    assurer_liste,
    changer_statut,
    lire_liste,
    retirer_ligne,
)
from ma_gouvernante.models import EtatChambre, StatutMenage


def test_une_liste_par_jour(compte, descriptions) -> None:
    admin = compte("admin@hotel-panorama.fr")
    reception = compte("reception@hotel-panorama.fr")
    assert descriptions() == []
    premiere = assurer_liste(admin["id"])
    seconde = assurer_liste(reception["id"])
    assert premiere == seconde
    assert len(descriptions()) == 1


def test_ajout_repere(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    premiere = creer_chambre(admin["id"], "101", 1)
    deuxieme = creer_chambre(admin["id"], "102", 2)
    hors_service = creer_chambre(admin["id"], "103", 3)
    changer_etat(admin["id"], hors_service, EtatChambre.hors_service)
    liste_id = assurer_liste(admin["id"])
    assert ajouter_chambres_en_service(admin["id"], liste_id) == 2
    assert ajouter_chambres_en_service(admin["id"], liste_id) == 0
    liste = lire_liste()
    assert liste is not None
    assert {ligne["chambre_id"] for ligne in liste["lignes"]} == {premiere, deuxieme}
    assert {ligne["statut"] for ligne in liste["lignes"]} == {StatutMenage.a_faire.value}


def test_retrait_refuse_apres_en_cours(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    menage = compte("menage@hotel-panorama.fr")
    creer_chambre(admin["id"], "101", 1)
    liste_id = assurer_liste(admin["id"])
    ajouter_chambres_en_service(admin["id"], liste_id)
    ligne = lire_liste()["lignes"][0]
    changer_statut(menage["id"], ligne["id"], StatutMenage.en_cours)
    with pytest.raises(RetraitRefuse):
        retirer_ligne(admin["id"], ligne["id"])
    encore = lire_liste()["lignes"][0]
    assert encore["id"] == ligne["id"]
    assert encore["statut"] == StatutMenage.en_cours.value


def test_second_faite_sans_nouvel_historique(compte, descriptions) -> None:
    admin = compte("admin@hotel-panorama.fr")
    menage = compte("menage@hotel-panorama.fr")
    creer_chambre(admin["id"], "101", 1)
    liste_id = assurer_liste(admin["id"])
    ajouter_chambres_en_service(admin["id"], liste_id)
    ligne_id = lire_liste()["lignes"][0]["id"]
    changer_statut(menage["id"], ligne_id, StatutMenage.faite)
    avant = descriptions()
    changer_statut(menage["id"], ligne_id, StatutMenage.faite)
    assert descriptions() == avant
    assert lire_liste()["lignes"][0]["statut"] == StatutMenage.faite.value
