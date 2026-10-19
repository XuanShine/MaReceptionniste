from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from sqlmodel import Session, select

from ma_receptionniste.models import (
    Client,
    Consommation,
    EtatDossier,
    Reglement,
    Reservation,
    Sejour,
    StatutReservation,
    Ticket,
)
from ma_receptionniste.sejours import ChambreOccupee, chambre_libre

_CENTIME = Decimal("0.01")


class DossierInvalide(ValueError):
    pass


@dataclass(frozen=True)
class DossierSaisi:
    client_id: int
    nom_occupant: str | None
    pays: str | None
    telephone: str | None
    email: str | None
    adresse: str | None
    partenaire: str | None
    etat: str
    traite: bool
    type_voiture: str | None
    date_facture: date | None
    numero_facture: str | None
    notes: str | None
    notes_internes: str | None
    notes_tempo: str | None
    notes_facturation: str | None


@dataclass(frozen=True)
class Compte:
    ttc: Decimal
    taxe: Decimal
    consommations: Decimal
    regle: Decimal
    reste: Decimal


LIBELLES_ETAT = {
    "en_cours": "En cours",
    "option": "Option",
    "parti": "Parti",
    "annulee": "Annulée",
}


def etat_affiche(statut: StatutReservation | str, etat_dossier: EtatDossier | str) -> str:
    if str(statut) == StatutReservation.annulee:
        return StatutReservation.annulee.value
    return str(etat_dossier)


def libelle_etat(statut: StatutReservation | str, etat_dossier: EtatDossier | str) -> str:
    return LIBELLES_ETAT.get(etat_affiche(statut, etat_dossier), str(etat_dossier))


def nombre_nuits(debut: date, fin: date) -> int:
    return (fin - debut).days


def lire_montant(valeur: object) -> Decimal | None:
    if valeur is None:
        return None
    texte = str(valeur).strip().replace(" ", "").replace(",", ".")
    if not texte:
        return None
    try:
        return Decimal(texte).quantize(_CENTIME)
    except InvalidOperation as exc:
        raise DossierInvalide("Montant illisible") from exc


def prix_apres_remise(prix: Decimal | None, remise: Decimal | None) -> Decimal:
    if prix is None:
        return Decimal("0.00")
    taux = Decimal("0") if remise is None else Decimal(remise)
    return (Decimal(prix) * (Decimal("1") - taux / Decimal("100"))).quantize(_CENTIME)


def synthese(
    sejours: list[Sejour],
    consommations: list[Consommation],
    reglements: list[Reglement],
) -> Compte:
    ttc = sum((prix_apres_remise(sejour.prix_ttc, sejour.remise_pct) for sejour in sejours), Decimal("0.00"))
    taxe = sum((_argent(sejour.taxe_sejour) for sejour in sejours), Decimal("0.00"))
    extras = sum((_argent(ligne.montant) for ligne in consommations), Decimal("0.00"))
    regle = sum((_argent(ligne.montant) for ligne in reglements), Decimal("0.00"))
    return Compte(
        ttc=ttc,
        taxe=taxe,
        consommations=extras,
        regle=regle,
        reste=(ttc + taxe + extras - regle).quantize(_CENTIME),
    )


def compte_fiche(sejours: list[dict], consommations: list[dict], reglements: list[dict]) -> Compte:
    return synthese(
        [
            SimpleNamespace(
                prix_ttc=ligne["prix_ttc"],
                remise_pct=ligne["remise_pct"],
                taxe_sejour=ligne["taxe_sejour"],
            )
            for ligne in sejours
        ],
        [SimpleNamespace(montant=ligne["montant"]) for ligne in consommations],
        [SimpleNamespace(montant=ligne["montant"]) for ligne in reglements],
    )


def jour_fr(valeur: date | None) -> str:
    if valeur is None:
        return ""
    return valeur.strftime("%d/%m/%Y")


def euros(montant: Decimal | None) -> str:
    if montant is None:
        return ""
    quantifie = Decimal(montant).quantize(_CENTIME)
    signe = "-" if quantifie < 0 else ""
    entier, centimes = f"{abs(quantifie):.2f}".split(".")
    groupes: list[str] = []
    while entier:
        groupes.append(entier[-3:])
        entier = entier[:-3]
    return f"{signe}{' '.join(reversed(groupes))},{centimes}"


def pourcent(remise: Decimal | None) -> str:
    if remise is None:
        return "0 %"
    valeur = Decimal(remise)
    if valeur == valeur.to_integral():
        return f"{int(valeur)} %"
    return f"{euros(valeur)} %"


def appliquer_etat_dossier(session: Session, reservation: Reservation, choix: str) -> None:
    if choix == StatutReservation.annulee:
        reservation.statut = StatutReservation.annulee
        return
    if choix not in {etat.value for etat in EtatDossier}:
        raise DossierInvalide("Statut inconnu")
    if str(reservation.statut) == StatutReservation.annulee:
        sejours = session.exec(select(Sejour).where(Sejour.reservation_id == reservation.id)).all()
        for sejour in sejours:
            if not chambre_libre(session, sejour.chambre_id, sejour.date_debut, sejour.date_fin, sejour.id):
                raise ChambreOccupee("La chambre est déjà occupée sur cette période")
    reservation.statut = StatutReservation.confirmee
    reservation.etat_dossier = EtatDossier(choix)


def enregistrer_dossier(session: Session, reservation_id: int, saisi: DossierSaisi) -> Reservation:
    reservation = session.get(Reservation, reservation_id)
    if reservation is None:
        raise DossierInvalide("Réservation introuvable")
    client = session.get(Client, saisi.client_id)
    if client is None:
        raise DossierInvalide("Client introuvable")
    appliquer_etat_dossier(session, reservation, saisi.etat)
    reservation.client_id = saisi.client_id
    reservation.nom_occupant = _vide(saisi.nom_occupant)
    reservation.partenaire = _vide(saisi.partenaire)
    reservation.traite = saisi.traite
    reservation.type_voiture = _vide(saisi.type_voiture)
    reservation.date_facture = saisi.date_facture
    reservation.numero_facture = _vide(saisi.numero_facture)
    reservation.notes = _vide(saisi.notes)
    reservation.notes_internes = _vide(saisi.notes_internes)
    reservation.notes_tempo = _vide(saisi.notes_tempo)
    reservation.notes_facturation = _vide(saisi.notes_facturation)
    client.pays = _vide(saisi.pays)
    client.telephone = _vide(saisi.telephone)
    client.email = _vide(saisi.email)
    client.adresse = _vide(saisi.adresse)
    session.add(reservation)
    session.add(client)
    return reservation


def ajouter_consommation(
    session: Session,
    reservation_id: int,
    libelle: str,
    quantite: int,
    montant: Decimal,
    jour: date,
) -> Consommation:
    if session.get(Reservation, reservation_id) is None:
        raise DossierInvalide("Réservation introuvable")
    texte = _vide(libelle)
    if texte is None:
        raise DossierInvalide("Le libellé est obligatoire")
    if quantite < 1:
        raise DossierInvalide("La quantité est invalide")
    if montant < 0:
        raise DossierInvalide("Le montant est invalide")
    ligne = Consommation(
        reservation_id=reservation_id,
        libelle=texte,
        quantite=quantite,
        montant=montant,
        jour=jour,
    )
    session.add(ligne)
    return ligne


def ajouter_reglement(
    session: Session,
    reservation_id: int,
    mode: str,
    montant: Decimal,
    jour: date,
    reference: str | None = None,
) -> Reglement:
    if session.get(Reservation, reservation_id) is None:
        raise DossierInvalide("Réservation introuvable")
    texte = _vide(mode)
    if texte is None:
        raise DossierInvalide("Le mode de règlement est obligatoire")
    if montant < 0:
        raise DossierInvalide("Le montant est invalide")
    ligne = Reglement(
        reservation_id=reservation_id,
        mode=texte,
        montant=montant,
        jour=jour,
        reference=_vide(reference),
    )
    session.add(ligne)
    return ligne


def ajouter_ticket(
    session: Session,
    reservation_id: int,
    objet: str,
    detail: str | None = None,
    quand: datetime | None = None,
) -> Ticket:
    if session.get(Reservation, reservation_id) is None:
        raise DossierInvalide("Réservation introuvable")
    texte = _vide(objet)
    if texte is None:
        raise DossierInvalide("L'objet du ticket est obligatoire")
    ticket = Ticket(reservation_id=reservation_id, objet=texte, detail=_vide(detail))
    if quand is not None:
        ticket.date = quand
    session.add(ticket)
    return ticket


def _argent(valeur: Decimal | None) -> Decimal:
    if valeur is None:
        return Decimal("0.00")
    return Decimal(valeur).quantize(_CENTIME)


def _vide(valeur: Any) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None
