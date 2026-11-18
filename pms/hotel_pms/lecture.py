"""Lectures prêtes à afficher (liste, planning, totaux)."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from hotel_pms.compta import totaux_sejour
from hotel_pms.models import Chambre, Client, Produit, Sejour


@dataclass
class ResumeSejour:
    id: int
    nom: str
    client: str
    partenaire: str
    est_en_cours: bool
    debut: date | None
    fin: date | None
    chambres: str
    reste: Decimal


def resumer_sejour(sejour: Sejour) -> ResumeSejour:
    lignes = list(sejour.lignes)
    debut = min((ligne.date_debut for ligne in lignes), default=None)
    fin = max((ligne.date_fin for ligne in lignes), default=None)
    numeros: list[str] = []
    for ligne in lignes:
        if ligne.chambre is not None and ligne.chambre.numero not in numeros:
            numeros.append(ligne.chambre.numero)
    totaux = totaux_sejour(lignes, list(sejour.reglements))
    return ResumeSejour(
        id=sejour.id or 0,
        nom=sejour.nom,
        client=sejour.client.nom if sejour.client else "",
        partenaire=sejour.partenaire,
        est_en_cours=sejour.est_en_cours,
        debut=debut,
        fin=fin,
        chambres=", ".join(numeros),
        reste=totaux.reste,
    )


def resumer_sejours(session: Session) -> list[ResumeSejour]:
    sejours = list(session.exec(select(Sejour)).all())
    resumes = [resumer_sejour(sejour) for sejour in sejours]
    resumes.sort(key=lambda resume: (resume.debut or date.max, resume.nom))
    return resumes


def lister_chambres(session: Session) -> list[Chambre]:
    chambres = list(session.exec(select(Chambre)).all())
    chambres.sort(key=lambda chambre: (len(chambre.numero), chambre.numero))
    return chambres


def lister_clients(session: Session) -> list[Client]:
    return list(session.exec(select(Client).order_by(Client.nom)).all())


def lister_produits(session: Session) -> list[Produit]:
    return list(session.exec(select(Produit).order_by(Produit.nom)).all())


@dataclass(frozen=True)
class SegmentPlanning:
    """Une ligne de réservation posée sur une chambre, du soir d'arrivée au matin du départ."""

    sejour_id: int
    nom: str
    chambre_id: int
    debut: date
    fin: date
    en_cours: bool


@dataclass(frozen=True)
class CellulePlanning:
    span: int
    jour: date | None = None
    sejour_id: int | None = None
    nom: str = ""
    nuits: int = 0
    en_cours: bool = False


@dataclass
class _Occupation:
    sejour_id: int
    nom: str
    debut_index: int
    span: int
    nuits: int
    en_cours: bool
    lane: int = 0


def grille_planning(
    segments: list[SegmentPlanning],
    chambre_ids: list[int],
    jours: list[date],
) -> dict[int, list[list[CellulePlanning]]]:
    """Une voie de cellules par chambre. Un séjour de plusieurs nuits occupe une seule cellule."""

    if not jours:
        return {chambre_id: [] for chambre_id in chambre_ids}
    debut_fenetre = jours[0]
    fin_fenetre = jours[-1] + timedelta(days=1)
    grille: dict[int, list[list[CellulePlanning]]] = {}
    for chambre_id in chambre_ids:
        occupations: list[_Occupation] = []
        for segment in segments:
            if segment.chambre_id != chambre_id or segment.fin <= segment.debut:
                continue
            debut = max(segment.debut, debut_fenetre)
            fin = min(segment.fin, fin_fenetre)
            if debut >= fin:
                continue
            occupations.append(
                _Occupation(
                    sejour_id=segment.sejour_id,
                    nom=segment.nom,
                    debut_index=(debut - debut_fenetre).days,
                    span=(fin - debut).days,
                    nuits=(segment.fin - segment.debut).days,
                    en_cours=segment.en_cours,
                )
            )
        grille[chambre_id] = _voies(occupations, jours)
    return grille


def _voies(occupations: list[_Occupation], jours: list[date]) -> list[list[CellulePlanning]]:
    if not occupations:
        return [[CellulePlanning(span=1, jour=jour) for jour in jours]]
    occupations.sort(key=lambda occ: (occ.debut_index, occ.sejour_id, occ.nom))
    fins_voies: list[int] = []
    for occupation in occupations:
        for index, fin in enumerate(fins_voies):
            if occupation.debut_index >= fin:
                occupation.lane = index
                fins_voies[index] = occupation.debut_index + occupation.span
                break
        else:
            occupation.lane = len(fins_voies)
            fins_voies.append(occupation.debut_index + occupation.span)
    voies: list[list[CellulePlanning]] = []
    for lane in range(len(fins_voies)):
        dans_la_voie = sorted(
            (occ for occ in occupations if occ.lane == lane),
            key=lambda occ: occ.debut_index,
        )
        cellules: list[CellulePlanning] = []
        curseur = 0
        for occupation in dans_la_voie:
            while curseur < occupation.debut_index:
                cellules.append(CellulePlanning(span=1, jour=jours[curseur]))
                curseur += 1
            cellules.append(
                CellulePlanning(
                    span=occupation.span,
                    sejour_id=occupation.sejour_id,
                    nom=occupation.nom,
                    nuits=occupation.nuits,
                    en_cours=occupation.en_cours,
                )
            )
            curseur += occupation.span
        while curseur < len(jours):
            cellules.append(CellulePlanning(span=1, jour=jours[curseur]))
            curseur += 1
        voies.append(cellules)
    return voies
