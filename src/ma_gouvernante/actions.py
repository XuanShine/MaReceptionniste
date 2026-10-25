from datetime import date

from ma_gouvernante.menage import (
    Acteur,
    FicheChambre,
    LigneChambre,
    LigneHistorique,
    LigneMenage,
    changer_statut,
    creer_chambre,
    definir_etat,
    fiche_chambre,
    lister_chambres,
    lister_historique,
    lister_menages,
    poser_menage,
    retirer_menage,
)
from ma_receptionniste.db import get_session


def poser(acteur: Acteur, jour: date, chambre_id: int, type_menage: str, notes: str | None) -> LigneMenage:
    with get_session() as session:
        return poser_menage(session, acteur, jour, chambre_id, type_menage, notes)


def retirer(acteur: Acteur, menage_id: int) -> None:
    with get_session() as session:
        retirer_menage(session, acteur, menage_id)


def statut(acteur: Acteur, menage_id: int, valeur: str) -> LigneMenage:
    with get_session() as session:
        return changer_statut(session, acteur, menage_id, valeur)


def liste(acteur: Acteur, jour: date) -> list[LigneMenage]:
    with get_session() as session:
        return lister_menages(session, acteur, jour)


def historique(acteur: Acteur, jour: date | None) -> list[LigneHistorique]:
    with get_session() as session:
        return lister_historique(session, acteur, jour)


def chambres(acteur: Acteur) -> list[LigneChambre]:
    with get_session() as session:
        return lister_chambres(session, acteur)


def fiche(acteur: Acteur, chambre_id: int, jour: date) -> FicheChambre:
    with get_session() as session:
        return fiche_chambre(session, acteur, chambre_id, jour)


def ajouter_chambre(acteur: Acteur, nom: str, position: int, type_chambre: str | None) -> int:
    with get_session() as session:
        return creer_chambre(session, acteur, nom, position, type_chambre)


def etat_chambre(acteur: Acteur, chambre_id: int, etat: str) -> None:
    with get_session() as session:
        definir_etat(session, acteur, chambre_id, etat)
