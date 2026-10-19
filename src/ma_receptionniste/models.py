from datetime import UTC, date, datetime
from enum import StrEnum

from sqlmodel import AutoString, Field, Relationship, SQLModel

# La base applique RESTRICT ou SET NULL. L'ORM ne réécrit pas les liens avant un DELETE.
_LA_BASE_DECIDE = {"passive_deletes": "all"}


class EtatChambre(StrEnum):
    pret = "pret"
    non_pret = "non_pret"


class StatutReservation(StrEnum):
    confirmee = "confirmee"
    annulee = "annulee"


class ModeReglement(StrEnum):
    especes = "especes"
    carte = "carte"
    virement = "virement"
    cheque = "cheque"
    ota = "ota"


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
    pays: str | None = None
    telephone: str | None = None
    email: str | None = None
    adresse: str | None = None
    notes: str | None = None
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))

    reservations: list["Reservation"] = Relationship(back_populates="client", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Chambre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(unique=True)
    type_chambre: str | None = None
    position: int
    etat: EtatChambre = Field(default=EtatChambre.non_pret, sa_type=AutoString)

    sejours: list["Sejour"] = Relationship(back_populates="chambre", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Reservation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    statut: StatutReservation = Field(default=StatutReservation.confirmee, sa_type=AutoString)
    date_creation: datetime = Field(default_factory=lambda: datetime.now(UTC))
    partenaire: str | None = None
    # Une colonne NOT NULL ajoutée après coup a besoin d'un DEFAULT en base pour les lignes existantes.
    traitee: bool = Field(default=False, sa_column_kwargs={"server_default": "0"})
    type_voiture: str | None = None
    date_facture: date | None = None
    numero_facture: int | None = None
    notes: str | None = None
    notes_internes: str | None = None
    notes_tempo: str | None = None
    facturation: str | None = None

    client: Client = Relationship(back_populates="reservations")
    sejours: list["Sejour"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)
    consommations: list["Consommation"] = Relationship(
        back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE
    )
    reglements: list["Reglement"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)
    historiques: list["Historique"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Sejour(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    chambre_id: int = Field(foreign_key="chambre.id", index=True)
    date_debut: date
    date_fin: date
    nom_client: str | None = None
    adultes: int = Field(default=1, sa_column_kwargs={"server_default": "1"})
    enfants: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    prix_nuit_centimes: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    remise_pct: int = Field(default=0, sa_column_kwargs={"server_default": "0"})

    reservation: Reservation = Relationship(back_populates="sejours")
    chambre: Chambre = Relationship(back_populates="sejours")


class Consommation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    libelle: str
    quantite: int = 1
    prix_unitaire_centimes: int
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))

    reservation: Reservation = Relationship(back_populates="consommations")


class Reglement(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    mode: ModeReglement = Field(sa_type=AutoString)
    montant_centimes: int
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))

    reservation: Reservation = Relationship(back_populates="reglements")


class Historique(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int | None = Field(default=None, foreign_key="reservation.id", ondelete="SET NULL", index=True)
    user_id: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    description: str
    date: datetime

    reservation: Reservation | None = Relationship(back_populates="historiques")
    user: User | None = Relationship(back_populates="historiques")
