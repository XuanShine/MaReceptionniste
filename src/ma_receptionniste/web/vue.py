from datetime import date, timedelta

from ma_receptionniste.affichage import JOURS, MOIS, date_courte, saisie_euros
from ma_receptionniste.consultations import STATUT_SEJOUR, segments
from ma_receptionniste.facturation import format_euros, montant_ligne, nuits, taxe_sejour
from ma_receptionniste.models import StatutReservation


def lundi_de(jour: date) -> date:
    return jour - timedelta(days=jour.weekday())


def _periode(lundi: date) -> str:
    dimanche = lundi + timedelta(days=6)
    debut = f"{lundi.day} {MOIS[lundi.month - 1]}" if lundi.month != dimanche.month else str(lundi.day)
    return f"Du {debut} au {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"


def _fond(jour: date, aujourd_hui: date) -> str:
    if jour == aujourd_hui:
        return "bg-primary-pale"
    return "bg-slate-50" if jour.weekday() >= 5 else "bg-white"


def preparer_planning(lundi: date, aujourd_hui: date, data: dict) -> dict:
    jours = [lundi + timedelta(days=offset) for offset in range(7)]
    fin_visible = jours[-1] + timedelta(days=1)
    lignes = []
    for chambre in data["chambres"]:
        sejours = [sejour for sejour in data["sejours"] if sejour["chambre_id"] == chambre["id"]]
        cases = []
        index = 0
        for bloc in segments(jours, sejours):
            jour = jours[index]
            index += bloc["longueur"]
            sejour = bloc["sejour"]
            case = {"longueur": bloc["longueur"], "fond": _fond(jour, aujourd_hui), "sejour": None}
            if sejour is not None:
                affichage = STATUT_SEJOUR[sejour["statut"]]
                titre = " · ".join(
                    filter(
                        None,
                        (
                            sejour["nom"],
                            sejour["partenaire"],
                            f"{date_courte(sejour['date_debut'])} → {date_courte(sejour['date_fin'])}",
                        ),
                    )
                )
                case["sejour"] = {
                    "reservation_id": sejour["reservation_id"],
                    "nom": sejour["nom"],
                    "partenaire": sejour["partenaire"],
                    "couleur": affichage.couleur,
                    "coupe_gauche": sejour["date_debut"] < jours[0],
                    "coupe_droite": sejour["date_fin"] > fin_visible,
                    "titre": titre,
                }
            cases.append(case)
        lignes.append({**chambre, "prete": chambre["etat"] == "pret", "cases": cases})
    return {
        "lundi": lundi,
        "periode": _periode(lundi),
        "precedent": lundi - timedelta(days=7),
        "suivant": lundi + timedelta(days=7),
        "aujourdhui": lundi_de(aujourd_hui),
        "entetes": [
            {
                "nom": JOURS[jour.weekday()][:3] + ".",
                "numero": jour.day,
                "aujourdhui": jour == aujourd_hui,
                "fond": _fond(jour, aujourd_hui),
                "couleur": "text-primary" if jour == aujourd_hui else "text-ardoise",
            }
            for jour in jours
        ],
        "lignes": lignes,
        "legende": [statut for statut in STATUT_SEJOUR.values() if statut.couleur != "negative"],
        "vide": not data["chambres"],
    }


def preparer_reservations(lignes: list[dict]) -> list[dict]:
    triees = sorted(lignes, key=lambda reservation: reservation["date_debut"] or date.max, reverse=True)
    resultat = []
    for reservation in triees:
        statut = STATUT_SEJOUR[reservation["statut"]]
        resultat.append(
            {
                "id": reservation["id"],
                "client": reservation["client"],
                "canal": reservation["partenaire"] or "—",
                "chambres": reservation["chambres"] or "—",
                "arrivee": date_courte(reservation["date_debut"]),
                "depart": date_courte(reservation["date_fin"]),
                "nuits": reservation["nuits"] or "",
                "statut": statut.libelle,
                "couleur": statut.couleur,
                "total": format_euros(reservation["total"]),
            }
        )
    return resultat


def sous_titre(fiche: dict) -> str:
    details = [f"Réservation n° {fiche['id']}"]
    if fiche["debut"]:
        nombre = nuits(fiche["debut"], fiche["fin"])
        details.append(f"du {date_courte(fiche['debut'])} au {date_courte(fiche['fin'])}")
        details.append(f"{nombre} nuit{'s' if nombre > 1 else ''}")
    if fiche["reservation"]["partenaire"]:
        details.append(fiche["reservation"]["partenaire"])
    return " · ".join(details)


def bornes_brouillon(fiche: dict) -> tuple[date, date]:
    debut = fiche["debut"] or date.today()
    fin = fiche["fin"] or debut + timedelta(days=1)
    if fin <= debut:
        fin = debut + timedelta(days=1)
    return debut, fin


def calculer_apercu(
    chambres: list[dict],
    chambre_id: int | None,
    debut: date | None,
    fin: date | None,
    adultes: int,
    prix_centimes: int,
    remise: int,
) -> dict:
    type_chambre = "—"
    for chambre in chambres:
        if chambre["id"] == chambre_id:
            type_chambre = chambre["type_chambre"] or "—"
            break
    if debut is None or fin is None or fin <= debut:
        return {
            "type": type_chambre,
            "nuits": "—",
            "taxe": "—",
            "montant": "—",
            "phrase": "Le départ doit être après l'arrivée.",
        }
    nombre = nuits(debut, fin)
    montant = montant_ligne(prix_centimes, nombre, remise)
    taxe = taxe_sejour(adultes, nombre)
    return {
        "type": type_chambre,
        "nuits": str(nombre),
        "taxe": format_euros(taxe),
        "montant": format_euros(montant),
        "phrase": (
            f"{nombre} nuit{'s' if nombre > 1 else ''} · montant {format_euros(montant)}"
            f" · taxe de séjour {format_euros(taxe)}"
        ),
    }


def contexte_fiche(fiche: dict, **extra) -> dict:
    return {
        "fiche": fiche,
        "statut": STATUT_SEJOUR[fiche["statut_sejour"]],
        "sous_titre": sous_titre(fiche),
        "solde_saisie": saisie_euros(fiche["totaux"].solde),
        "annulee": fiche["reservation"]["statut"] == StatutReservation.annulee,
        **extra,
    }
