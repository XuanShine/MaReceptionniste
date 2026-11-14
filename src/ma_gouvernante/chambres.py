from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ma_gouvernante.auth import utilisateur
from ma_gouvernante.db import get_session
from ma_gouvernante.droits import exiger
from ma_gouvernante.journal import ajouter
from ma_gouvernante.models import (
    Chambre,
    EtatChambre,
    LigneMenage,
    ListeMenage,
    Signalement,
    StatutMenage,
    StatutSignalement,
    libelle_etat,
)


class NomVide(ValueError):
    pass


class NomDejaPris(ValueError):
    pass


class EtatInvalide(ValueError):
    pass


class ChambreIntrouvable(ValueError):
    pass


def _etat(valeur: EtatChambre | str) -> EtatChambre:
    try:
        return valeur if isinstance(valeur, EtatChambre) else EtatChambre(valeur)
    except ValueError:
        raise EtatInvalide(str(valeur)) from None


def creer_chambre(user_id: int, nom: str, position: int) -> int:
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "gerer_chambres")
        nom = nom.strip()
        if not nom:
            raise NomVide
        if session.exec(select(Chambre).where(Chambre.nom == nom)).first():
            raise NomDejaPris(nom)
        chambre = Chambre(nom=nom, position=position, etat=EtatChambre.en_service)
        session.add(chambre)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise NomDejaPris(nom) from None
        ajouter(session, user.id, f"{user.nom} crée la chambre {chambre.nom}.", chambre_id=chambre.id)
        chambre_id = chambre.id
        session.commit()
        return chambre_id


def changer_etat(user_id: int, chambre_id: int, etat: EtatChambre | str) -> None:
    nouvel = _etat(etat)
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "gerer_chambres")
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            raise ChambreIntrouvable(chambre_id)
        if EtatChambre(chambre.etat) == nouvel:
            return
        chambre.etat = nouvel
        ajouter(
            session,
            user.id,
            f"{user.nom} passe la chambre {chambre.nom} à l'état {libelle_etat(nouvel).lower()}.",
            chambre_id=chambre.id,
        )
        session.commit()


def tableau() -> list[dict]:
    aujourdhui = date.today()
    with get_session() as session:
        chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
        liste = session.exec(select(ListeMenage).where(ListeMenage.jour == aujourdhui)).first()
        statuts: dict[int, str] = {}
        if liste is not None:
            lignes = session.exec(select(LigneMenage).where(LigneMenage.liste_id == liste.id)).all()
            for ligne in lignes:
                statuts[ligne.chambre_id] = StatutMenage(ligne.statut).value
        comptes: dict[int, int] = {}
        ouverts = session.exec(select(Signalement).where(Signalement.statut == StatutSignalement.ouvert)).all()
        for signalement in ouverts:
            comptes[signalement.chambre_id] = comptes.get(signalement.chambre_id, 0) + 1
        return [
            {
                "id": chambre.id,
                "nom": chambre.nom,
                "position": chambre.position,
                "etat": EtatChambre(chambre.etat).value,
                "menage": statuts.get(chambre.id),
                "signalements_ouverts": comptes.get(chambre.id, 0),
            }
            for chambre in chambres
        ]


def detail(chambre_id: int) -> dict | None:
    for ligne in tableau():
        if ligne["id"] == chambre_id:
            return ligne
    return None
