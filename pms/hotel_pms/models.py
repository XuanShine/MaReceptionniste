"""Forme du domaine.

User
Client
Chambre
Produit
Sejour (statut en_cours | traite, partenaire, notes, contacts)
    ├── LigneReservation (type, chambre, nuits, dates, prix TTC, remise, adultes, enfants, taxe)
    ├── LigneConsommation (produit, prix unitaire, quantité, total dérivé)
    ├── Reglement (date, type, montant)
    └── ModificationSejour
"""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from sqlalchemy import Column, ForeignKey, Integer, Numeric
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel


class StatutSejour(StrEnum):
    en_cours = "en_cours"
    traite = "traite"


class EtatChambre(StrEnum):
    pret = "pret"
    non_pret = "non_pret"


def _enum(enum_cls: type[StrEnum]) -> Column:
    return Column(
        SAEnum(enum_cls, native_enum=False, values_callable=lambda membres: [m.value for m in membres]),
        nullable=False,
    )


def _montant() -> Column:
    return Column(Numeric(10, 2), nullable=False)


def _maintenant() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    identifiant: str = Field(index=True, unique=True)
    nom: str
    password_hash: str
    cree_le: datetime = Field(default_factory=_maintenant)


class Client(SQLModel, table=True):
    __tablename__ = "client"

    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    telephone: str = ""
    email: str = ""

    sejours: list["Sejour"] = Relationship(back_populates="client")


class Chambre(SQLModel, table=True):
    __tablename__ = "chambre"

    id: int | None = Field(default=None, primary_key=True)
    numero: str = Field(unique=True, index=True)
    type_chambre: str
    etat: EtatChambre = Field(default=EtatChambre.non_pret, sa_column=_enum(EtatChambre))

    lignes: list["LigneReservation"] = Relationship(back_populates="chambre")

    @property
    def etat_libelle(self) -> str:
        valeur = self.etat.value if isinstance(self.etat, EtatChambre) else str(self.etat)
        return "Prêt" if valeur == EtatChambre.pret.value else "Non prêt"


class Produit(SQLModel, table=True):
    __tablename__ = "produit"

    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    prix_ttc: Decimal = Field(default=Decimal("0.00"), sa_column=_montant())
    taux_tva: Decimal = Field(default=Decimal("10.00"), sa_column=_montant())

    consommations: list["LigneConsommation"] = Relationship(back_populates="produit")


class Sejour(SQLModel, table=True):
    __tablename__ = "sejour"

    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    client_id: int | None = Field(default=None, foreign_key="client.id", index=True)
    pays_nat: str = ""
    partenaire: str = ""
    statut: StatutSejour = Field(default=StatutSejour.en_cours, sa_column=_enum(StatutSejour))
    type_voiture: str = ""
    date_facture: date | None = None
    num_facture: str | None = None
    fact_client_uniquement: bool = Field(default=False)
    telephone_fixe: str = ""
    telephone_mobile: str = ""
    fax: str = ""
    email: str = ""
    ref_partenaire: str = ""
    ref_distributeur: str = ""
    notes: str = ""
    notes_internes: str = ""
    notes_tempo: str = ""
    facturation_client: str = ""

    client: Client | None = Relationship(back_populates="sejours")
    lignes: list["LigneReservation"] = Relationship(
        back_populates="sejour",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    reglements: list["Reglement"] = Relationship(
        back_populates="sejour",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    consommations: list["LigneConsommation"] = Relationship(
        back_populates="sejour",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    modifications: list["ModificationSejour"] = Relationship(
        back_populates="sejour",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    @property
    def statut_enum(self) -> StatutSejour:
        if isinstance(self.statut, StatutSejour):
            return self.statut
        return StatutSejour(str(self.statut))

    @property
    def est_en_cours(self) -> bool:
        return self.statut_enum == StatutSejour.en_cours

    @property
    def statut_libelle(self) -> str:
        return "En cours" if self.est_en_cours else "Traité"

    @property
    def total_consommations(self) -> Decimal:
        return sum((ligne.prix_total for ligne in self.consommations), Decimal("0.00"))


class LigneReservation(SQLModel, table=True):
    __tablename__ = "ligne_reservation"

    id: int | None = Field(default=None, primary_key=True)
    sejour_id: int = Field(
        sa_column=Column(Integer, ForeignKey("sejour.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    chambre_id: int | None = Field(default=None, foreign_key="chambre.id", index=True)
    type_chambre: str
    nb_jours: int
    date_debut: date
    date_fin: date
    prix_ttc: Decimal = Field(default=Decimal("0.00"), sa_column=_montant())
    remise_pct: Decimal = Field(default=Decimal("0.00"), sa_column=_montant())
    adultes: int = 1
    enfants: int = 0
    taxe_sejour: Decimal = Field(default=Decimal("0.00"), sa_column=_montant())

    sejour: Sejour = Relationship(back_populates="lignes")
    chambre: Chambre | None = Relationship(back_populates="lignes")


class Reglement(SQLModel, table=True):
    __tablename__ = "reglement"

    id: int | None = Field(default=None, primary_key=True)
    sejour_id: int = Field(
        sa_column=Column(Integer, ForeignKey("sejour.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    date_reglement: date
    type_reglement: str
    montant: Decimal = Field(default=Decimal("0.00"), sa_column=_montant())

    sejour: Sejour = Relationship(back_populates="reglements")


class LigneConsommation(SQLModel, table=True):
    """Extra du séjour (minibar, parking…). Le total est prix unitaire × quantité."""

    __tablename__ = "ligne_consommation"

    id: int | None = Field(default=None, primary_key=True)
    sejour_id: int = Field(
        sa_column=Column(Integer, ForeignKey("sejour.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    produit_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("produit.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    nom: str
    prix_unitaire: Decimal = Field(default=Decimal("0.00"), sa_column=_montant())
    quantite: int = 1

    sejour: Sejour = Relationship(back_populates="consommations")
    produit: Produit | None = Relationship(back_populates="consommations")

    @property
    def prix_total(self) -> Decimal:
        total = Decimal(self.prix_unitaire) * Decimal(self.quantite)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ModificationSejour(SQLModel, table=True):
    __tablename__ = "modification_sejour"

    id: int | None = Field(default=None, primary_key=True)
    sejour_id: int = Field(
        sa_column=Column(Integer, ForeignKey("sejour.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    date_modif: datetime
    description: str

    sejour: Sejour = Relationship(back_populates="modifications")
