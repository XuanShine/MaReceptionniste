from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from ma_receptionniste2.calendrier import JOURS, titre_semaine
from ma_receptionniste2.models import (
    Chambre,
    Client,
    EtatChambre,
    Historique,
    Reservation,
    Sejour,
    StatutReservation,
    User,
)

ETAT_LABEL = {
    EtatChambre.pret: "Prête",
    EtatChambre.non_pret: "Non prête",
}
STATUT_LABEL = {
    StatutReservation.confirmee: "Confirmée",
    StatutReservation.annulee: "Annulée",
}


def nuits_entre(debut_sejour: date, fin_sejour: date, debut_fenetre: date, fin_fenetre: date) -> list[date]:
    """Nuits du séjour visibles dans [debut_fenetre, fin_fenetre). Le matin du départ est exclu."""
    jour = max(debut_sejour, debut_fenetre)
    borne = min(fin_sejour, fin_fenetre)
    nuits: list[date] = []
    while jour < borne:
        nuits.append(jour)
        jour += timedelta(days=1)
    return nuits


@dataclass(frozen=True)
class BlocSejour:
    reservation_id: int
    nom: str
    nuits: tuple[date, ...]


@dataclass(frozen=True)
class Segment:
    sejour: BlocSejour | None
    longueur: int


def segments(jours: list[date], sejours: list[BlocSejour]) -> list[Segment]:
    """Découpe une ligne de planning. Un bloc par séjour continu, une case par nuit libre."""
    par_nuit: dict[date, BlocSejour] = {}
    for sejour in sejours:
        for nuit in sejour.nuits:
            par_nuit[nuit] = sejour
    resultat: list[Segment] = []
    index = 0
    while index < len(jours):
        sejour = par_nuit.get(jours[index])
        longueur = 1
        if sejour is not None:
            while index + longueur < len(jours) and par_nuit.get(jours[index + longueur]) is sejour:
                longueur += 1
        resultat.append(Segment(sejour=sejour, longueur=longueur))
        index += longueur
    return resultat


def nom_complet(prenom: str | None, nom: str) -> str:
    if prenom:
        return f"{prenom} {nom}"
    return nom


def _etat(valeur: EtatChambre | str) -> str:
    return valeur.value if isinstance(valeur, EtatChambre) else str(valeur)


def _statut(valeur: StatutReservation | str) -> str:
    return valeur.value if isinstance(valeur, StatutReservation) else str(valeur)


@dataclass(frozen=True)
class JourPlanning:
    date: date
    court: str
    numero: int
    aujourdhui: bool


@dataclass(frozen=True)
class LignePlanning:
    id: int
    nom: str
    etat: str
    etat_label: str
    segments: tuple[Segment, ...]

    @property
    def prete(self) -> bool:
        return self.etat == EtatChambre.pret.value


@dataclass(frozen=True)
class Semaine:
    debut: date
    precedente: date
    suivante: date
    titre: str
    jours: tuple[JourPlanning, ...]
    lignes: tuple[LignePlanning, ...]


def semaine_planning(session: Session, debut: date, aujourd_hui: date) -> Semaine:
    fin = debut + timedelta(days=7)
    jours = [debut + timedelta(days=offset) for offset in range(7)]
    chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
    lignes = session.exec(
        select(Sejour, Client)
        .join(Reservation, Reservation.id == Sejour.reservation_id)
        .join(Client, Client.id == Reservation.client_id)
        .where(Reservation.statut != StatutReservation.annulee)
        .where(Sejour.date_debut < fin)
        .where(Sejour.date_fin > debut)
        .order_by(Sejour.date_debut)
    ).all()
    par_chambre: dict[int, list[BlocSejour]] = {}
    for sejour, client in lignes:
        bloc = BlocSejour(
            reservation_id=sejour.reservation_id,
            nom=sejour.nom_client or nom_complet(client.prenom, client.nom),
            nuits=tuple(nuits_entre(sejour.date_debut, sejour.date_fin, debut, fin)),
        )
        par_chambre.setdefault(sejour.chambre_id, []).append(bloc)
    return Semaine(
        debut=debut,
        precedente=debut - timedelta(days=7),
        suivante=debut + timedelta(days=7),
        titre=titre_semaine(debut),
        jours=tuple(
            JourPlanning(date=jour, court=JOURS[jour.weekday()], numero=jour.day, aujourdhui=jour == aujourd_hui)
            for jour in jours
        ),
        lignes=tuple(
            LignePlanning(
                id=chambre.id,
                nom=chambre.nom,
                etat=_etat(chambre.etat),
                etat_label=ETAT_LABEL.get(EtatChambre(_etat(chambre.etat)), _etat(chambre.etat)),
                segments=tuple(segments(jours, par_chambre.get(chambre.id, []))),
            )
            for chambre in chambres
        ),
    )


@dataclass(frozen=True)
class ChambreVue:
    id: int
    nom: str
    position: int
    etat: str
    etat_label: str

    @property
    def prete(self) -> bool:
        return self.etat == EtatChambre.pret.value


def _chambre_vue(chambre: Chambre) -> ChambreVue:
    etat = _etat(chambre.etat)
    return ChambreVue(
        id=chambre.id,
        nom=chambre.nom,
        position=chambre.position,
        etat=etat,
        etat_label=ETAT_LABEL.get(EtatChambre(etat), etat),
    )


def lister_chambres(session: Session) -> list[ChambreVue]:
    chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
    return [_chambre_vue(chambre) for chambre in chambres]


def chambre_vue(session: Session, chambre_id: int) -> ChambreVue | None:
    chambre = session.get(Chambre, chambre_id)
    if chambre is None:
        return None
    return _chambre_vue(chambre)


@dataclass(frozen=True)
class ClientVue:
    id: int
    nom: str
    prenom: str | None
    email: str | None
    telephone: str | None
    adresse: str | None
    notes: str | None


def lister_clients(session: Session) -> list[ClientVue]:
    clients = session.exec(select(Client).order_by(Client.cree_le.desc(), Client.id.desc())).all()
    return [
        ClientVue(
            id=client.id,
            nom=client.nom,
            prenom=client.prenom,
            email=client.email,
            telephone=client.telephone,
            adresse=client.adresse,
            notes=client.notes,
        )
        for client in clients
    ]


@dataclass(frozen=True)
class Choix:
    id: int
    libelle: str


def choix_clients(session: Session) -> list[Choix]:
    return [Choix(id=client.id, libelle=nom_complet(client.prenom, client.nom)) for client in lister_clients(session)]


def choix_chambres(session: Session) -> list[Choix]:
    return [Choix(id=chambre.id, libelle=chambre.nom) for chambre in lister_chambres(session)]


@dataclass(frozen=True)
class SejourVue:
    chambre_nom: str
    date_debut: date
    date_fin: date
    nom_client: str | None


@dataclass(frozen=True)
class NoteVue:
    description: str
    date: datetime
    auteur: str | None


@dataclass(frozen=True)
class ReservationVue:
    id: int
    client: str
    statut: str
    statut_label: str
    sejours: tuple[SejourVue, ...]
    notes: tuple[NoteVue, ...] = ()

    @property
    def annulee(self) -> bool:
        return self.statut == StatutReservation.annulee.value


def _sejour_vue(session: Session, sejour: Sejour) -> SejourVue:
    chambre = session.get(Chambre, sejour.chambre_id)
    return SejourVue(
        chambre_nom=chambre.nom if chambre else "Chambre retirée",
        date_debut=sejour.date_debut,
        date_fin=sejour.date_fin,
        nom_client=sejour.nom_client,
    )


def _auteur(session: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = session.get(User, user_id)
    return user.nom if user else None


def _reservation_vue(session: Session, reservation: Reservation, *, avec_notes: bool) -> ReservationVue:
    client = session.get(Client, reservation.client_id)
    sejours = session.exec(
        select(Sejour).where(Sejour.reservation_id == reservation.id).order_by(Sejour.date_debut)
    ).all()
    notes: tuple[NoteVue, ...] = ()
    if avec_notes:
        lignes = session.exec(
            select(Historique).where(Historique.reservation_id == reservation.id).order_by(Historique.date.desc())
        ).all()
        notes = tuple(
            NoteVue(description=note.description, date=note.date, auteur=_auteur(session, note.user_id))
            for note in lignes
        )
    statut = _statut(reservation.statut)
    return ReservationVue(
        id=reservation.id,
        client=nom_complet(client.prenom, client.nom) if client else "Client inconnu",
        statut=statut,
        statut_label=STATUT_LABEL.get(StatutReservation(statut), statut),
        sejours=tuple(_sejour_vue(session, sejour) for sejour in sejours),
        notes=notes,
    )


def lister_reservations(session: Session) -> list[ReservationVue]:
    reservations = session.exec(
        select(Reservation).order_by(Reservation.date_creation.desc(), Reservation.id.desc())
    ).all()
    return [_reservation_vue(session, reservation, avec_notes=False) for reservation in reservations]


def detail_reservation(session: Session, reservation_id: int) -> ReservationVue | None:
    reservation = session.get(Reservation, reservation_id)
    if reservation is None:
        return None
    return _reservation_vue(session, reservation, avec_notes=True)
