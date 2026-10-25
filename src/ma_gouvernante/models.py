from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import registry
from sqlmodel import AutoString, Field, SQLModel

# Registre à part : user, chambre et historique existent déjà sur SQLModel.metadata (la réception).
gouvernante_registry = registry()


class GouvernanteModel(SQLModel, registry=gouvernante_registry):
    pass


class Role(StrEnum):
    admin = "admin"
    receptionniste = "receptionniste"
    femme_de_chambre = "femme_de_chambre"
    technicien = "technicien"


class EtatChambre(StrEnum):
    en_service = "en_service"
    hors_service = "hors_service"


class StatutMenage(StrEnum):
    a_faire = "a_faire"
    en_cours = "en_cours"
    faite = "faite"


class StatutSignalement(StrEnum):
    ouvert = "ouvert"
    resolu = "resolu"


TOUS_LES_ROLES = (Role.admin, Role.receptionniste, Role.femme_de_chambre, Role.technicien)


def libelle_role(role: Role | str) -> str:
    return {
        Role.admin: "Admin",
        Role.receptionniste: "Réceptionniste",
        Role.femme_de_chambre: "Femme de chambre",
        Role.technicien: "Technicien",
    }[Role(role)]


def libelle_etat(etat: EtatChambre | str) -> str:
    return {
        EtatChambre.en_service: "En service",
        EtatChambre.hors_service: "Hors service",
    }[EtatChambre(etat)]


def libelle_menage(statut: StatutMenage | str | None) -> str:
    if statut is None:
        return "Pas au ménage"
    return {
        StatutMenage.a_faire: "À faire",
        StatutMenage.en_cours: "En cours",
        StatutMenage.faite: "Faite",
    }[StatutMenage(statut)]


def libelle_signalement(statut: StatutSignalement | str) -> str:
    return {
        StatutSignalement.ouvert: "Ouvert",
        StatutSignalement.resolu: "Résolu",
    }[StatutSignalement(statut)]


class User(GouvernanteModel, table=True):
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    nom: str
    password_hash: str
    role: Role = Field(sa_type=AutoString)
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chambre(GouvernanteModel, table=True):
    __tablename__ = "chambre"

    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(unique=True)
    position: int
    etat: EtatChambre = Field(default=EtatChambre.en_service, sa_type=AutoString)


class ListeMenage(GouvernanteModel, table=True):
    __tablename__ = "listemenage"

    id: int | None = Field(default=None, primary_key=True)
    jour: date = Field(unique=True)
    cree_par_user_id: int = Field(foreign_key="user.id")


class LigneMenage(GouvernanteModel, table=True):
    __tablename__ = "lignemenage"
    __table_args__ = (UniqueConstraint("liste_id", "chambre_id", name="ligne_liste_chambre"),)

    id: int | None = Field(default=None, primary_key=True)
    liste_id: int = Field(foreign_key="listemenage.id", index=True)
    chambre_id: int = Field(foreign_key="chambre.id", index=True)
    statut: StatutMenage = Field(default=StatutMenage.a_faire, sa_type=AutoString)


class Signalement(GouvernanteModel, table=True):
    __tablename__ = "signalement"

    id: int | None = Field(default=None, primary_key=True)
    chambre_id: int = Field(foreign_key="chambre.id", index=True)
    auteur_id: int = Field(foreign_key="user.id")
    note: str
    photo_path: str | None = None
    statut: StatutSignalement = Field(default=StatutSignalement.ouvert, sa_type=AutoString)
    resolu_par_id: int | None = Field(default=None, foreign_key="user.id")
    resolu_le: datetime | None = None
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Historique(GouvernanteModel, table=True):
    __tablename__ = "historique"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    chambre_id: int | None = Field(default=None, foreign_key="chambre.id")
    liste_id: int | None = Field(default=None, foreign_key="listemenage.id")
    signalement_id: int | None = Field(default=None, foreign_key="signalement.id")
    description: str
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
