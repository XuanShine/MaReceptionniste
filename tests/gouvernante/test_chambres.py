import pytest

from ma_gouvernante.chambres import NomDejaPris, changer_etat, creer_chambre, tableau
from ma_gouvernante.droits import Refus
from ma_gouvernante.models import EtatChambre


def test_nom_en_double(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    creer_chambre(admin["id"], "101", 1)
    with pytest.raises(NomDejaPris):
        creer_chambre(admin["id"], "101", 2)
    assert [ligne["nom"] for ligne in tableau()] == ["101"]


def test_second_hors_service_sans_nouvel_historique(compte, descriptions) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    changer_etat(admin["id"], chambre_id, EtatChambre.hors_service)
    avant = descriptions()
    changer_etat(admin["id"], chambre_id, EtatChambre.hors_service)
    assert descriptions() == avant
    assert tableau()[0]["etat"] == EtatChambre.hors_service.value


def test_femme_de_chambre_ne_cree_pas(compte) -> None:
    menage = compte("menage@hotel-panorama.fr")
    with pytest.raises(Refus):
        creer_chambre(menage["id"], "101", 1)
    assert tableau() == []
