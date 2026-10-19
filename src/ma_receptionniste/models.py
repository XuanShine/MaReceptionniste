from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column, Numeric, Text
from sqlmodel import AutoString, Field, Relationship, SQLModel

# La base applique RESTRICT ou SET NULL. L'ORM ne réécrit pas les liens avant un DELETE.
_LA_BASE_DECIDE = {"passive_deletes": "all"}


class EtatChambre(StrEnum):
    pret = "pret"
    non_pret = "non_pret"


class StatutReservation(StrEnum):
    confirmee = "confirmee"
    annulee = "annulee"


class EtatDossier(StrEnum):
    en_cours = "en_cours"
    option = "option"
    parti = "parti"


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    nom: str
    password_hash: str
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))

    historiques: list["Historique"] = Relationship(back_populates="user", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Client(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    prenom: str | None = None
    telephone: str | None = None
    email: str | None = None
    adresse: str | None = None
    pays: str | None = None
    notes: str | None = None
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))

    reservations: list["Reservation"] = Relationship(back_populates="client", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Chambre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(unique=True)
    position: int
    etat: EtatChambre = Field(default=EtatChambre.non_pret, sa_type=AutoString)

    sejours: list["Sejour"] = Relationship(back_populates="chambre", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Reservation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    statut: StatutReservation = Field(default=StatutReservation.confirmee, sa_type=AutoString)
    etat_dossier: EtatDossier = Field(default=EtatDossier.en_cours, sa_type=AutoString)
    traite: bool = Field(default=False)
    nom_occupant: str | None = None
    partenaire: str | None = None
    type_voiture: str | None = None
    date_facture: date | None = None
    numero_facture: str | None = None
    notes: str | None = Field(default=None, sa_column=Column(Text))
    notes_internes: str | None = Field(default=None, sa_column=Column(Text))
    notes_tempo: str | None = Field(default=None, sa_column=Column(Text))
    notes_facturation: str | None = Field(default=None, sa_column=Column(Text))
    date_creation: datetime = Field(default_factory=lambda: datetime.now(UTC))

    client: Client = Relationship(back_populates="reservations")
    sejours: list["Sejour"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)
    historiques: list["Historique"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Sejour(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    chambre_id: int = Field(foreign_key="chambre.id", index=True)
    date_debut: date
    date_fin: date
    nom_client: str | None = None
    type_produit: str | None = None
    prix_ttc: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 2)))
    remise_pct: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(5, 2), nullable=False, server_default="0"),
    )
    adultes: int = Field(default=1)
    enfants: int = Field(default=0)
    taxe_sejour: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 2)))

    reservation: Reservation = Relationship(back_populates="sejours")
    chambre: Chambre = Relationship(back_populates="sejours")


class Historique(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int | None = Field(default=None, foreign_key="reservation.id", ondelete="SET NULL", index=True)
    user_id: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    description: str
    date: datetime

    reservation: Reservation | None = Relationship(back_populates="historiques")
    user: User | None = Relationship(back_populates="historiques")


class Consommation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    libelle: str
    quantite: int = Field(default=1)
    montant: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(12, 2), nullable=False, server_default="0"),
    )
    jour: date


class Reglement(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    mode: str
    montant: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    jour: date
    reference: str | None = None


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    objet: str
    detail: str | None = Field(default=None, sa_column=Column(Text))
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
