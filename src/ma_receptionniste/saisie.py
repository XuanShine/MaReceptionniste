from datetime import UTC, datetime

from ma_receptionniste.db import get_session
from ma_receptionniste.dossier import (
    DossierSaisi,
    ajouter_consommation,
    ajouter_reglement,
    ajouter_ticket,
    enregistrer_dossier,
)
from ma_receptionniste.models import Chambre, Client, EtatChambre, Historique, Reservation, Sejour, StatutReservation
from ma_receptionniste.sejours import SejourInvalide, enregistrer_sejour


def creer_chambre(nom: str, position: int) -> int:
    with get_session() as session:
        chambre = Chambre(nom=nom.strip(), position=position)
        session.add(chambre)
        session.commit()
        return chambre.id


def basculer_etat(chambre_id: int) -> None:
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            return
        chambre.etat = EtatChambre.pret if str(chambre.etat) == EtatChambre.non_pret else EtatChambre.non_pret
        session.add(chambre)
        session.commit()


def creer_client(
    nom: str,
    prenom: str | None = None,
    email: str | None = None,
    telephone: str | None = None,
    adresse: str | None = None,
    notes: str | None = None,
    pays: str | None = None,
) -> int:
    with get_session() as session:
        client = Client(
            nom=nom.strip(),
            prenom=_vide(prenom),
            email=_vide(email),
            telephone=_vide(telephone),
            adresse=_vide(adresse),
            notes=_vide(notes),
            pays=_vide(pays),
        )
        session.add(client)
        session.commit()
        return client.id


def creer_reservation(client_id: int) -> int:
    with get_session() as session:
        reservation = Reservation(client_id=client_id)
        session.add(reservation)
        session.commit()
        return reservation.id


def ajouter_sejour(
    reservation_id: int,
    chambre_id: int,
    date_debut,
    date_fin,
    nom_client: str | None = None,
    *,
    type_produit: str | None = None,
    prix_ttc=None,
    remise_pct=None,
    adultes: int | None = None,
    enfants: int | None = None,
    taxe_sejour=None,
) -> int:
    with get_session() as session:
        sejour = enregistrer_sejour(
            session,
            reservation_id=reservation_id,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            nom_client=_vide(nom_client),
            type_produit=_vide(type_produit),
            prix_ttc=prix_ttc,
            remise_pct=remise_pct if remise_pct is not None else 0,
            adultes=1 if adultes is None else adultes,
            enfants=0 if enfants is None else enfants,
            taxe_sejour=taxe_sejour,
        )
        session.commit()
        return sejour.id


def modifier_sejour(
    sejour_id: int,
    chambre_id: int,
    date_debut,
    date_fin,
    *,
    type_produit: str | None,
    prix_ttc,
    remise_pct,
    adultes: int,
    enfants: int,
    taxe_sejour,
) -> None:
    with get_session() as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            raise SejourInvalide("Séjour introuvable")
        enregistrer_sejour(
            session,
            reservation_id=sejour.reservation_id,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            ignorer_sejour_id=sejour_id,
            type_produit=_vide(type_produit),
            prix_ttc=prix_ttc,
            remise_pct=remise_pct if remise_pct is not None else 0,
            adultes=adultes,
            enfants=enfants,
            taxe_sejour=taxe_sejour,
        )
        session.commit()


def sauver_dossier(reservation_id: int, saisi: DossierSaisi) -> None:
    with get_session() as session:
        enregistrer_dossier(session, reservation_id, saisi)
        session.commit()


def noter_consommation(reservation_id: int, libelle: str, quantite: int, montant, jour) -> int:
    with get_session() as session:
        ligne = ajouter_consommation(session, reservation_id, libelle, quantite, montant, jour)
        session.commit()
        return ligne.id


def noter_reglement(reservation_id: int, mode: str, montant, jour, reference: str | None = None) -> int:
    with get_session() as session:
        ligne = ajouter_reglement(session, reservation_id, mode, montant, jour, reference)
        session.commit()
        return ligne.id


def noter_ticket(reservation_id: int, objet: str, detail: str | None = None) -> int:
    with get_session() as session:
        ticket = ajouter_ticket(session, reservation_id, objet, detail)
        session.commit()
        return ticket.id


def annuler_reservation(reservation_id: int) -> None:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            return
        reservation.statut = StatutReservation.annulee
        session.add(reservation)
        session.commit()


def ajouter_note(reservation_id: int, user_id: int | None, description: str) -> None:
    with get_session() as session:
        session.add(
            Historique(
                reservation_id=reservation_id,
                user_id=user_id,
                description=description.strip(),
                date=datetime.now(UTC),
            )
        )
        session.commit()


def _vide(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None
