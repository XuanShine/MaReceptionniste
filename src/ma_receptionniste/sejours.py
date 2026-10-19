from datetime import date
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from ma_receptionniste.models import Reservation, Sejour, StatutReservation

_INCHANGE = object()


class SejourInvalide(ValueError):
    """date_fin n'est pas strictement après date_debut."""


class ChambreOccupee(ValueError):
    """Un séjour non annulé occupe déjà cette chambre sur ces nuits."""


def periodes_se_chevauchent(debut_a: date, fin_a: date, debut_b: date, fin_b: date) -> bool:
    # date_fin est le matin du départ : les périodes [debut, fin) se touchent sans se croiser.
    return debut_a < fin_b and debut_b < fin_a


def chambre_libre(
    session: Session,
    chambre_id: int,
    date_debut: date,
    date_fin: date,
    ignorer_sejour_id: int | None = None,
) -> bool:
    statement = (
        select(Sejour.id)
        .join(Reservation, Reservation.id == Sejour.reservation_id)
        .where(Sejour.chambre_id == chambre_id)
        .where(Reservation.statut != StatutReservation.annulee)
        .where(Sejour.date_debut < date_fin)
        .where(Sejour.date_fin > date_debut)
    )
    if ignorer_sejour_id is not None:
        statement = statement.where(Sejour.id != ignorer_sejour_id)
    return session.exec(statement).first() is None


def enregistrer_sejour(
    session: Session,
    *,
    reservation_id: int,
    chambre_id: int,
    date_debut: date,
    date_fin: date,
    nom_client: Any = _INCHANGE,
    ignorer_sejour_id: int | None = None,
    type_produit: Any = _INCHANGE,
    prix_ttc: Any = _INCHANGE,
    remise_pct: Any = _INCHANGE,
    adultes: Any = _INCHANGE,
    enfants: Any = _INCHANGE,
    taxe_sejour: Any = _INCHANGE,
) -> Sejour:
    if date_fin <= date_debut:
        raise SejourInvalide("Le départ doit être après l'arrivée")
    _verifier_ligne(prix_ttc, remise_pct, adultes, enfants, taxe_sejour)
    if not chambre_libre(session, chambre_id, date_debut, date_fin, ignorer_sejour_id):
        raise ChambreOccupee("La chambre est déjà occupée sur cette période")

    if ignorer_sejour_id is None:
        sejour = Sejour(
            reservation_id=reservation_id,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            nom_client=None if nom_client is _INCHANGE else nom_client,
        )
    else:
        sejour = session.get(Sejour, ignorer_sejour_id)
        if sejour is None:
            raise SejourInvalide("Séjour introuvable")
        sejour.reservation_id = reservation_id
        sejour.chambre_id = chambre_id
        sejour.date_debut = date_debut
        sejour.date_fin = date_fin
        if nom_client is not _INCHANGE:
            sejour.nom_client = nom_client
    _poser(sejour, "type_produit", type_produit)
    _poser(sejour, "prix_ttc", _decimal(prix_ttc))
    _poser(sejour, "remise_pct", _decimal(remise_pct))
    _poser(sejour, "adultes", adultes)
    _poser(sejour, "enfants", enfants)
    _poser(sejour, "taxe_sejour", _decimal(taxe_sejour))
    session.add(sejour)
    return sejour


def _poser(sejour: Sejour, attr: str, valeur: Any) -> None:
    if valeur is _INCHANGE:
        return
    setattr(sejour, attr, valeur)


def _decimal(valeur: Any) -> Any:
    if valeur is _INCHANGE or valeur is None:
        return valeur
    return Decimal(valeur).quantize(Decimal("0.01"))


def _verifier_ligne(prix: Any, remise: Any, adultes: Any, enfants: Any, taxe: Any) -> None:
    if adultes is not _INCHANGE and int(adultes) < 0:
        raise SejourInvalide("Le nombre d'adultes est invalide")
    if enfants is not _INCHANGE and int(enfants) < 0:
        raise SejourInvalide("Le nombre d'enfants est invalide")
    if remise is not _INCHANGE and remise is not None and not Decimal("0") <= Decimal(remise) <= Decimal("100"):
        raise SejourInvalide("La remise doit être entre 0 et 100")
    if prix is not _INCHANGE and prix is not None and Decimal(prix) < 0:
        raise SejourInvalide("Le prix est invalide")
    if taxe is not _INCHANGE and taxe is not None and Decimal(taxe) < 0:
        raise SejourInvalide("La taxe est invalide")
