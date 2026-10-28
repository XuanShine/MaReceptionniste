"""Lectures prêtes à afficher (liste, planning, totaux)."""

from dataclasses import dataclass
from datetime import date
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
