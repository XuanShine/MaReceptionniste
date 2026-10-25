from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ma_gouvernante.auth import utilisateur
from ma_gouvernante.db import get_session
from ma_gouvernante.droits import exiger
from ma_gouvernante.journal import ajouter
from ma_gouvernante.models import Chambre, EtatChambre, LigneMenage, ListeMenage, StatutMenage, libelle_menage


class ListeAbsente(ValueError):
    pass


class LigneIntrouvable(ValueError):
    pass


class RetraitRefuse(ValueError):
    pass


class StatutInvalide(ValueError):
    pass


def _statut(valeur: StatutMenage | str) -> StatutMenage:
    try:
        return valeur if isinstance(valeur, StatutMenage) else StatutMenage(valeur)
    except ValueError:
        raise StatutInvalide(str(valeur)) from None


def assurer_liste(user_id: int, jour: date | None = None) -> int:
    jour = jour or date.today()
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "creer_liste")
        existante = session.exec(select(ListeMenage).where(ListeMenage.jour == jour)).first()
        if existante is not None:
            return existante.id
        liste = ListeMenage(jour=jour, cree_par_user_id=user.id)
        session.add(liste)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existante = session.exec(select(ListeMenage).where(ListeMenage.jour == jour)).one()
            return existante.id
        ajouter(
            session,
            user.id,
            f"{user.nom} crée la liste de ménage du {jour.strftime('%d/%m/%Y')}.",
            liste_id=liste.id,
        )
        liste_id = liste.id
        session.commit()
        return liste_id


def ajouter_chambres_en_service(user_id: int, liste_id: int) -> int:
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "creer_liste")
        liste = session.get(ListeMenage, liste_id)
        if liste is None:
            raise ListeAbsente(liste_id)
        presentes = {
            ligne.chambre_id
            for ligne in session.exec(select(LigneMenage).where(LigneMenage.liste_id == liste_id)).all()
        }
        chambres = session.exec(select(Chambre).where(Chambre.etat == EtatChambre.en_service)).all()
        ajoutees = 0
        for chambre in chambres:
            if chambre.id in presentes:
                continue
            session.add(LigneMenage(liste_id=liste_id, chambre_id=chambre.id, statut=StatutMenage.a_faire))
            ajoutees += 1
        session.commit()
        return ajoutees


def remplir_liste(user_id: int) -> int:
    liste_id = assurer_liste(user_id)
    return ajouter_chambres_en_service(user_id, liste_id)


def lire_liste(jour: date | None = None) -> dict | None:
    jour = jour or date.today()
    with get_session() as session:
        liste = session.exec(select(ListeMenage).where(ListeMenage.jour == jour)).first()
        if liste is None:
            return None
        lignes = session.exec(
            select(LigneMenage, Chambre)
            .join(Chambre, Chambre.id == LigneMenage.chambre_id)
            .where(LigneMenage.liste_id == liste.id)
            .order_by(Chambre.position, Chambre.nom)
        ).all()
        return {
            "id": liste.id,
            "jour": liste.jour,
            "lignes": [
                {
                    "id": ligne.id,
                    "chambre_id": chambre.id,
                    "nom": chambre.nom,
                    "statut": StatutMenage(ligne.statut).value,
                }
                for ligne, chambre in lignes
            ],
        }


def retirer_ligne(user_id: int, ligne_id: int) -> None:
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "creer_liste")
        ligne = session.get(LigneMenage, ligne_id)
        if ligne is None:
            raise LigneIntrouvable(ligne_id)
        if StatutMenage(ligne.statut) != StatutMenage.a_faire:
            raise RetraitRefuse(ligne_id)
        chambre = session.get(Chambre, ligne.chambre_id)
        nom = chambre.nom if chambre is not None else str(ligne.chambre_id)
        session.delete(ligne)
        ajouter(
            session,
            user.id,
            f"{user.nom} retire la chambre {nom} de la liste de ménage.",
            chambre_id=ligne.chambre_id,
            liste_id=ligne.liste_id,
        )
        session.commit()


def changer_statut(user_id: int, ligne_id: int, statut: StatutMenage | str) -> None:
    nouveau = _statut(statut)
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "changer_menage")
        ligne = session.get(LigneMenage, ligne_id)
        if ligne is None:
            raise LigneIntrouvable(ligne_id)
        if StatutMenage(ligne.statut) == nouveau:
            return
        ligne.statut = nouveau
        chambre = session.get(Chambre, ligne.chambre_id)
        nom = chambre.nom if chambre is not None else str(ligne.chambre_id)
        ajouter(
            session,
            user.id,
            f"{user.nom} passe le ménage de la chambre {nom} à {libelle_menage(nouveau).lower()}.",
            chambre_id=ligne.chambre_id,
            liste_id=ligne.liste_id,
        )
        session.commit()
