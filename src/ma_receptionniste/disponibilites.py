from datetime import date, timedelta

from sqlmodel import select

from ma_receptionniste.db import get_session
from ma_receptionniste.models import Chambre, Reservation, Sejour, StatutReservation, TypeChambre


def matrice_disponibilites(date_debut: date, date_fin: date) -> dict:
    """Retourne dates, chambres, types et valeurs (lignes chambres, colonnes nuits).

    La période est [date_debut, date_fin). Chaque valeur vaut 1 si la chambre
    est libre, 0 sinon. Les types correspondent aux affectations actuelles.
    Trois requêtes chargent les données ; les nuits sont calculées en mémoire.
    """
    if date_fin <= date_debut:
        raise ValueError("La date de fin doit être après la date de début")

    dates = [date_debut + timedelta(days=index) for index in range((date_fin - date_debut).days)]
    with get_session() as session:
        types = [
            {"id": type_.id, "libelle": type_.libelle}
            for type_ in session.exec(select(TypeChambre).order_by(TypeChambre.libelle, TypeChambre.id))
        ]
        libelles = {type_["id"]: type_["libelle"] for type_ in types}
        chambres = [
            {
                "id": chambre.id,
                "nom": chambre.nom,
                "type_chambre_id": chambre.type_chambre_id,
                "type_chambre": libelles.get(chambre.type_chambre_id),
            }
            for chambre in session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom, Chambre.id))
        ]
        sejours = session.exec(
            select(Sejour.chambre_id, Sejour.date_debut, Sejour.date_fin)
            .join(Reservation, Reservation.id == Sejour.reservation_id)
            .where(Reservation.statut != StatutReservation.annulee)
            .where(Sejour.date_debut < date_fin)
            .where(Sejour.date_fin > date_debut)
        ).all()

    differences = {chambre["id"]: [0] * (len(dates) + 1) for chambre in chambres}
    for chambre_id, debut, fin in sejours:
        differences[chambre_id][(max(debut, date_debut) - date_debut).days] += 1
        differences[chambre_id][(min(fin, date_fin) - date_debut).days] -= 1

    valeurs = []
    for chambre in chambres:
        occupations = 0
        ligne = []
        # Le cumul des débuts (+1) et fins (-1) gère aussi les séjours qui se chevauchent.
        for difference in differences[chambre["id"]][:-1]:
            occupations += difference
            ligne.append(int(occupations == 0))
        valeurs.append(ligne)
    return {"dates": dates, "chambres": chambres, "types": types, "valeurs": valeurs}


def disponibilites_par_type(matrice: dict) -> dict:
    """Additionne les lignes par type, sans accès en base ni modification de la matrice."""
    types = [dict(type_) for type_ in matrice["types"]]
    totaux = {type_["id"]: [0] * len(matrice["dates"]) for type_ in types}
    for chambre, ligne in zip(matrice["chambres"], matrice["valeurs"], strict=True):
        if chambre["type_chambre_id"] is None:
            continue
        total = totaux[chambre["type_chambre_id"]]
        for index, valeur in enumerate(ligne):
            total[index] += valeur
    return {
        "dates": list(matrice["dates"]),
        "types": types,
        "valeurs": [totaux[type_["id"]] for type_ in types],
    }
