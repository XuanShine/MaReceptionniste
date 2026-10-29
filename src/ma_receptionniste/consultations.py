from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import NamedTuple

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import montant_consommation, montant_sejour, nuits, taxe_du_sejour, totaux
from ma_receptionniste.models import (
    Chambre,
    Client,
    EtatChambre,
    Historique,
    ModeReglement,
    Reservation,
    Sejour,
    StatutReservation,
)

ETAT_LABEL = {
    EtatChambre.pret: "Prête",
    EtatChambre.non_pret: "Non prête",
}
MODE_REGLEMENT_LABEL = {
    ModeReglement.especes: "Espèces",
    ModeReglement.carte: "Carte bancaire",
    ModeReglement.virement: "Virement",
    ModeReglement.cheque: "Chèque",
    ModeReglement.ota: "OTA (prépayé)",
}


class StatutSejour(StrEnum):
    a_venir = "a_venir"
    en_cours = "en_cours"
    parti = "parti"
    annule = "annule"


class Affichage(NamedTuple):
    libelle: str
    couleur: str


STATUT_SEJOUR = {
    StatutSejour.a_venir: Affichage("À venir", "secondary"),
    StatutSejour.en_cours: Affichage("En cours", "primary"),
    StatutSejour.parti: Affichage("Parti", "ardoise"),
    StatutSejour.annule: Affichage("Annulée", "negative"),
}


@dataclass(frozen=True)
class ResumeJour:
    arrivees: int
    departs: int
    en_maison: int
    chambres_non_pretes: int


def statut_sejour(
    statut_reservation: StatutReservation | str, debut: date | None, fin: date | None, aujourd_hui: date
) -> StatutSejour:
    """Le jour d'arrivée compte comme en cours, le matin du départ comme parti."""
    if statut_reservation == StatutReservation.annulee:
        return StatutSejour.annule
    if debut is None or fin is None or aujourd_hui < debut:
        return StatutSejour.a_venir
    if aujourd_hui < fin:
        return StatutSejour.en_cours
    return StatutSejour.parti


def resume_du_jour(sejours: list[dict], chambres: list[dict], jour: date) -> ResumeJour:
    return ResumeJour(
        arrivees=sum(sejour["date_debut"] == jour for sejour in sejours),
        departs=sum(sejour["date_fin"] == jour for sejour in sejours),
        en_maison=sum(sejour["date_debut"] <= jour < sejour["date_fin"] for sejour in sejours),
        chambres_non_pretes=sum(chambre["etat"] == EtatChambre.non_pret for chambre in chambres),
    )


def nuits_entre(debut_sejour: date, fin_sejour: date, debut_fenetre: date, fin_fenetre: date) -> list[date]:
    """Nuits du séjour visibles dans [debut_fenetre, fin_fenetre). Le matin du départ est exclu."""
    jour = max(debut_sejour, debut_fenetre)
    borne = min(fin_sejour, fin_fenetre)
    nuits: list[date] = []
    while jour < borne:
        nuits.append(jour)
        jour += timedelta(days=1)
    return nuits


def segments(jours: list[date], sejours: list[dict]) -> list[dict]:
    """Découpe une ligne de planning : un bloc par séjour continu, une case par nuit libre."""
    par_nuit: dict[date, dict] = {}
    for sejour in sejours:
        for nuit in sejour["nuits"]:
            par_nuit[nuit] = sejour
    resultat: list[dict] = []
    index = 0
    while index < len(jours):
        sejour = par_nuit.get(jours[index])
        longueur = 1
        if sejour is not None:
            while index + longueur < len(jours) and par_nuit.get(jours[index + longueur]) is sejour:
                longueur += 1
        resultat.append({"sejour": sejour, "longueur": longueur})
        index += longueur
    return resultat


def _etat(valeur: EtatChambre | str) -> str:
    return valeur.value if isinstance(valeur, EtatChambre) else str(valeur)


def _chambre_dict(chambre: Chambre) -> dict:
    etat = _etat(chambre.etat)
    return {
        "id": chambre.id,
        "nom": chambre.nom,
        "type_chambre": chambre.type_chambre,
        "position": chambre.position,
        "etat": etat,
        "etat_label": ETAT_LABEL.get(EtatChambre(etat), etat),
    }


def _sejours_visibles(session: Session, debut: date, fin: date, aujourd_hui: date) -> list[dict]:
    lignes = session.exec(
        select(Sejour, Reservation, Client)
        .join(Reservation, Reservation.id == Sejour.reservation_id)
        .join(Client, Client.id == Reservation.client_id)
        .where(Reservation.statut != StatutReservation.annulee)
        .where(Sejour.date_debut < fin)
        .where(Sejour.date_fin > debut)
        .order_by(Sejour.date_debut)
    ).all()
    return [
        {
            "id": sejour.id,
            "chambre_id": sejour.chambre_id,
            "reservation_id": sejour.reservation_id,
            "date_debut": sejour.date_debut,
            "date_fin": sejour.date_fin,
            "nom": sejour.nom_client or client.nom,
            "partenaire": reservation.partenaire,
            "statut": statut_sejour(reservation.statut, sejour.date_debut, sejour.date_fin, aujourd_hui),
            "nuits": nuits_entre(sejour.date_debut, sejour.date_fin, debut, fin),
        }
        for sejour, reservation, client in lignes
    ]


def planning(session: Session, debut: date, fin: date, aujourd_hui: date | None = None) -> dict:
    aujourd_hui = aujourd_hui or date.today()
    chambres = [
        _chambre_dict(chambre) for chambre in session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom))
    ]
    # La fenêtre [veille, lendemain) attrape aussi les départs du jour, dont date_fin vaut aujourd'hui.
    du_jour = _sejours_visibles(session, aujourd_hui - timedelta(days=1), aujourd_hui + timedelta(days=1), aujourd_hui)
    return {
        "chambres": chambres,
        "sejours": _sejours_visibles(session, debut, fin, aujourd_hui),
        "resume": resume_du_jour(du_jour, chambres, aujourd_hui),
    }


def charger_planning(debut: date, fin: date) -> dict:
    with get_session() as session:
        return planning(session, debut, fin)


def charger_resume() -> ResumeJour:
    aujourd_hui = date.today()
    with get_session() as session:
        return planning(session, aujourd_hui, aujourd_hui)["resume"]


def lister_chambres() -> list[dict]:
    with get_session() as session:
        chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
        return [_chambre_dict(chambre) for chambre in chambres]


def lister_clients() -> list[dict]:
    with get_session() as session:
        clients = session.exec(select(Client).order_by(Client.cree_le.desc())).all()
        return [
            {
                "id": client.id,
                "nom": client.nom,
                "pays": client.pays,
                "email": client.email,
                "telephone": client.telephone,
                "adresse": client.adresse,
                "notes": client.notes,
            }
            for client in clients
        ]


def options_clients() -> dict[int, str]:
    return {client["id"]: f"{client['nom']} #{client['id']}" for client in lister_clients()}


def options_chambres() -> dict[int, str]:
    return {
        chambre["id"]: " · ".join(filter(None, (chambre["nom"], chambre["type_chambre"])))
        for chambre in lister_chambres()
    }


def _avec_tout(requete):
    return requete.options(
        selectinload(Reservation.client),
        selectinload(Reservation.sejours).selectinload(Sejour.chambre),
        selectinload(Reservation.consommations),
        selectinload(Reservation.reglements),
    )


def _bornes(sejours: list[Sejour]) -> tuple[date | None, date | None]:
    if not sejours:
        return None, None
    return min(sejour.date_debut for sejour in sejours), max(sejour.date_fin for sejour in sejours)


def lister_reservations(aujourd_hui: date | None = None) -> list[dict]:
    aujourd_hui = aujourd_hui or date.today()
    with get_session() as session:
        reservations = session.exec(_avec_tout(select(Reservation)).order_by(Reservation.date_creation.desc())).all()
        resultat = []
        for reservation in reservations:
            sejours = sorted(reservation.sejours, key=lambda sejour: (sejour.date_debut, sejour.id))
            debut, fin = _bornes(sejours)
            statut = statut_sejour(reservation.statut, debut, fin, aujourd_hui)
            resultat.append(
                {
                    "id": reservation.id,
                    "client": reservation.client.nom,
                    "partenaire": reservation.partenaire,
                    "chambres": ", ".join(sejour.chambre.nom for sejour in sejours),
                    "date_debut": debut,
                    "date_fin": fin,
                    "nuits": nuits(debut, fin) if debut and fin else 0,
                    "statut": statut,
                    "total": totaux(sejours, reservation.consommations, reservation.reglements).total,
                }
            )
        return resultat


def fiche_sejour(reservation_id: int, aujourd_hui: date | None = None) -> dict | None:
    aujourd_hui = aujourd_hui or date.today()
    with get_session() as session:
        reservation = session.exec(
            _avec_tout(select(Reservation))
            .options(selectinload(Reservation.historiques).selectinload(Historique.user))
            .where(Reservation.id == reservation_id)
        ).first()
        if reservation is None:
            return None
        client = reservation.client
        sejours = sorted(reservation.sejours, key=lambda sejour: (sejour.date_debut, sejour.id))
        consommations = sorted(reservation.consommations, key=lambda consommation: consommation.date)
        reglements = sorted(reservation.reglements, key=lambda reglement: reglement.date)
        historique = sorted(reservation.historiques, key=lambda note: (note.date, note.id), reverse=True)
        debut, fin = _bornes(sejours)
        return {
            "id": reservation.id,
            "client": {
                "id": client.id,
                "nom": client.nom,
                "nom_complet": client.nom,
                "pays": client.pays,
                "telephone": client.telephone,
                "email": client.email,
                "adresse": client.adresse,
            },
            "reservation": {
                "statut": StatutReservation(str(reservation.statut)),
                "partenaire": reservation.partenaire,
                "traitee": reservation.traitee,
                "type_voiture": reservation.type_voiture,
                "date_facture": reservation.date_facture,
                "numero_facture": reservation.numero_facture,
                "notes": reservation.notes,
                "notes_internes": reservation.notes_internes,
                "notes_tempo": reservation.notes_tempo,
                "facturation": reservation.facturation,
            },
            "debut": debut,
            "fin": fin,
            "statut_sejour": statut_sejour(reservation.statut, debut, fin, aujourd_hui),
            "lignes": [
                {
                    "id": sejour.id,
                    "chambre_id": sejour.chambre_id,
                    "chambre_nom": sejour.chambre.nom,
                    "type_chambre": sejour.chambre.type_chambre,
                    "date_debut": sejour.date_debut,
                    "date_fin": sejour.date_fin,
                    "nuits": nuits(sejour.date_debut, sejour.date_fin),
                    "prix_nuit_centimes": sejour.prix_nuit_centimes,
                    "remise_pct": sejour.remise_pct,
                    "adultes": sejour.adultes,
                    "enfants": sejour.enfants,
                    "nom_client": sejour.nom_client,
                    "taxe": taxe_du_sejour(sejour),
                    "montant": montant_sejour(sejour),
                }
                for sejour in sejours
            ],
            "consommations": [
                {
                    "id": consommation.id,
                    "date": consommation.date,
                    "libelle": consommation.libelle,
                    "quantite": consommation.quantite,
                    "prix_unitaire_centimes": consommation.prix_unitaire_centimes,
                    "montant": montant_consommation(consommation),
                }
                for consommation in consommations
            ],
            "reglements": [
                {
                    "id": reglement.id,
                    "date": reglement.date,
                    "mode": ModeReglement(str(reglement.mode)),
                    "montant_centimes": reglement.montant_centimes,
                }
                for reglement in reglements
            ],
            "historique": [
                {
                    "id": note.id,
                    "date": note.date,
                    "auteur": note.user.nom if note.user else None,
                    "description": note.description,
                }
                for note in historique
            ],
            "compteurs": {
                "reservations": len(sejours),
                "consommations": len(consommations),
                "reglements": len(reglements),
                "modifications": len(historique),
            },
            "totaux": totaux(sejours, consommations, reglements),
        }
