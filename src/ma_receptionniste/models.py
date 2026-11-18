from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import AutoString, Field, Relationship, SQLModel

# La base applique RESTRICT ou SET NULL. L'ORM ne réécrit pas les liens avant un DELETE.
_LA_BASE_DECIDE = {"passive_deletes": "all"}


class EtatChambre(StrEnum):
    pret = "pret"
    non_pret = "non_pret"


class StatutReservation(StrEnum):
    option_devis = "option_devis"
    confirmee = "confirmee"
    en_cours = "en_cours"
    parti = "parti"
    annulee = "annulee"


class ModeReglement(StrEnum):
    especes = "especes"
    carte = "carte"
    virement = "virement"
    cheque = "cheque"
    ota = "ota"


class FormeJuridique(StrEnum):
    ei = "ei"
    eurl = "eurl"
    sarl = "sarl"
    sasu = "sasu"
    sas = "sas"
    sa = "sa"
    sci = "sci"
    association = "association"
    autre = "autre"


class RegimeTVA(StrEnum):
    assujetti = "assujetti"
    franchise = "franchise"
    exonere = "exonere"


class TypeDestinataire(StrEnum):
    particulier = "particulier"
    professionnel = "professionnel"


class CategorieLigne(StrEnum):
    chambre = "chambre"
    consommation = "consommation"


class NatureReglement(StrEnum):
    paiement = "paiement"
    remboursement = "remboursement"


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
    pays: str | None = None
    telephone: str | None = None
    email: str | None = None
    adresse: str | None = None
    notes: str | None = None
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))

    reservations: list["Reservation"] = Relationship(back_populates="client", sa_relationship_kwargs=_LA_BASE_DECIDE)


class TypeChambre(SQLModel, table=True):
    __tablename__ = "type_chambre"

    id: int | None = Field(default=None, primary_key=True)
    wubook_id: int | None = None
    libelle: str = Field(unique=True)
    description: str = Field(default="", sa_column_kwargs={"server_default": ""})
    disponibilite: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    # L'unicité est un index, pas une contrainte de colonne : SQLite refuse UNIQUE dans un ALTER.
    nom_raccourci: str | None = Field(default=None, max_length=4)
    prix_defaut: float = Field(default=0, sa_column_kwargs={"server_default": "0"})
    prix_mini: float = Field(default=0, sa_column_kwargs={"server_default": "0"})
    channel_manager_uniquement: bool = Field(default=False, sa_column_kwargs={"server_default": "0"})

    chambres: list["Chambre"] = Relationship(back_populates="type_de_chambre", sa_relationship_kwargs=_LA_BASE_DECIDE)
    chambres_virtuelles: list["ChambreVirtuelle"] = Relationship(
        back_populates="type_de_chambre", sa_relationship_kwargs=_LA_BASE_DECIDE
    )


class ChambreChambreVirtuelle(SQLModel, table=True):
    __tablename__ = "chambre_chambre_virtuelle"

    chambre_id: int = Field(foreign_key="chambre.id", ondelete="CASCADE", primary_key=True)
    chambre_virtuelle_id: int = Field(
        foreign_key="chambre_virtuelle.id", ondelete="CASCADE", primary_key=True, index=True
    )


class ChambreVirtuelle(SQLModel, table=True):
    __tablename__ = "chambre_virtuelle"

    id: int | None = Field(default=None, primary_key=True)
    wubook_id: int | None = None
    type_chambre_id: int = Field(foreign_key="type_chambre.id", ondelete="RESTRICT", index=True)
    description: str = Field(default="", sa_column_kwargs={"server_default": ""})
    # Propre aux chambres virtuelles : pas le même espace d'unicité que TypeChambre.nom_raccourci.
    nom_raccourci: str = Field(max_length=4, unique=True)
    prix_defaut: float
    prix_mini: float

    type_de_chambre: TypeChambre = Relationship(back_populates="chambres_virtuelles")
    chambres: list["Chambre"] = Relationship(
        back_populates="chambres_virtuelles",
        link_model=ChambreChambreVirtuelle,
        sa_relationship_kwargs={"passive_deletes": True},
    )


class OccupationChambre(SQLModel, table=True):
    __tablename__ = "occupation_chambre"
    __table_args__ = (UniqueConstraint("nombre_personnes", "type_lits"),)

    id: int | None = Field(default=None, primary_key=True)
    nombre_personnes: int
    type_lits: str

    chambres: list["Chambre"] = Relationship(back_populates="occupation", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Chambre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(unique=True)
    position: int
    etage: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    etat: EtatChambre = Field(default=EtatChambre.non_pret, sa_type=AutoString)
    type_chambre_id: int | None = Field(default=None, foreign_key="type_chambre.id", ondelete="RESTRICT", index=True)
    occupation_chambre_id: int | None = Field(
        default=None, foreign_key="occupation_chambre.id", ondelete="RESTRICT", index=True
    )

    type_de_chambre: TypeChambre | None = Relationship(back_populates="chambres")
    occupation: OccupationChambre | None = Relationship(back_populates="chambres")
    chambres_virtuelles: list["ChambreVirtuelle"] = Relationship(
        back_populates="chambres",
        link_model=ChambreChambreVirtuelle,
        sa_relationship_kwargs={"passive_deletes": True},
    )
    sejours: list["Sejour"] = Relationship(back_populates="chambre", sa_relationship_kwargs=_LA_BASE_DECIDE)


class Reservation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    statut: StatutReservation = Field(default=StatutReservation.confirmee, sa_type=AutoString)
    date_creation: datetime = Field(default_factory=lambda: datetime.now(UTC))
    partenaire: str | None = None
    # Une colonne NOT NULL ajoutée après coup a besoin d'un DEFAULT en base pour les lignes existantes.
    nom_occupant: str | None = None
    type_voiture: str | None = None
    date_facture: date | None = None
    numero_facture: int | None = None
    notes: str | None = None
    notes_internes: str | None = None
    notes_tempo: str | None = None
    notes_facturation: str | None = None
    facturation: str | None = None

    client: Client = Relationship(back_populates="reservations")
    sejours: list["Sejour"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)
    consommations: list["Consommation"] = Relationship(
        back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE
    )
    reglements: list["Reglement"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)
    historiques: list["Historique"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)
    factures: list["Facture"] = Relationship(back_populates="reservation", sa_relationship_kwargs=_LA_BASE_DECIDE)


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

    reservation: Reservation = Relationship(back_populates="sejours")
    chambre: Chambre = Relationship(back_populates="sejours")


class Produit(SQLModel, table=True):
    # Pas de lien vers Consommation : une vente copie le nom et le prix acceptés.
    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(unique=True)
    prix_unitaire_centimes: int = Field(sa_column_kwargs={"server_default": "0"})
    # Millièmes : 200 = 20 %, 100 = 10 %, 55 = 5,5 %, 21 = 2,1 %, 0 = exonéré.
    taux_tva_pour_mille: int = Field(default=100, sa_column_kwargs={"server_default": "100"})
    actif: bool = Field(default=True, sa_column_kwargs={"server_default": "1"})


class Consommation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    libelle: str
    quantite: int = 1
    # NOT NULL sur une table déjà créée : SQLite n'ajoute la colonne que s'il a un DEFAULT constant.
    prix_unitaire_centimes: int = Field(sa_column_kwargs={"server_default": "0"})
    # Copié à la vente : un changement de taux du produit ne réécrit pas une consommation déjà notée.
    taux_tva_pour_mille: int = Field(default=100, sa_column_kwargs={"server_default": "100"})
    date: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"server_default": "1970-01-01 00:00:00"},
    )

    reservation: Reservation = Relationship(back_populates="consommations")


class Reglement(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", index=True)
    mode: ModeReglement = Field(sa_type=AutoString)
    montant_centimes: int = Field(sa_column_kwargs={"server_default": "0"})
    date: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"server_default": "1970-01-01 00:00:00"},
    )

    reservation: Reservation = Relationship(back_populates="reglements")


class Historique(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int | None = Field(default=None, foreign_key="reservation.id", ondelete="SET NULL", index=True)
    user_id: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    description: str
    date: datetime

    reservation: Reservation | None = Relationship(back_populates="historiques")
    user: User | None = Relationship(back_populates="historiques")


class IdentiteFacturation(SQLModel, table=True):
    """Une seule ligne, id 1. Une facture émise en copie les champs : cette ligne ne les réécrit pas."""

    __tablename__ = "identite_facturation"

    id: int | None = Field(default=None, primary_key=True)
    nom_commercial: str | None = None
    denomination: str | None = None
    forme_juridique: FormeJuridique | None = Field(default=None, sa_type=AutoString)
    capital_centimes: int | None = None
    adresse_siege: str | None = None
    adresse_facturation: str | None = None
    siren: str | None = None
    siret: str | None = None
    immatriculation: str | None = None
    numero_tva: str | None = None
    regime_tva: RegimeTVA | None = Field(default=None, sa_type=AutoString)
    taux_hebergement_pour_mille: int = Field(default=100, sa_column_kwargs={"server_default": "100"})
    delai_paiement_jours: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    conditions_paiement: str | None = None
    escompte: str | None = None
    penalites: str | None = None


class CompteurFacture(SQLModel, table=True):
    __tablename__ = "compteur_facture"

    id: int | None = Field(default=None, primary_key=True)
    dernier_numero: int = Field(default=0, sa_column_kwargs={"server_default": "0"})


class Facture(SQLModel, table=True):
    __tablename__ = "facture"

    id: int | None = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id", ondelete="RESTRICT", index=True)
    numero: int = Field(unique=True)
    cle_idempotence: str = Field(unique=True)
    courante: bool = Field(default=True, sa_column_kwargs={"server_default": "1"})
    remplace_id: int | None = Field(default=None, foreign_key="facture.id", ondelete="RESTRICT")
    date_emission: date
    date_prestation: date | None = None
    date_echeance: date
    nom_facture: str
    destinataire_type: TypeDestinataire = Field(sa_type=AutoString)
    destinataire_nom: str
    destinataire_adresse: str
    destinataire_adresse_facturation: str | None = None
    destinataire_siren: str | None = None
    destinataire_tva: str | None = None
    reference_commande: str | None = None
    hotel_nom_commercial: str | None = None
    hotel_denomination: str | None = None
    hotel_forme_juridique: FormeJuridique | None = Field(default=None, sa_type=AutoString)
    hotel_capital_centimes: int | None = None
    hotel_adresse_siege: str | None = None
    hotel_adresse_facturation: str | None = None
    hotel_siren: str | None = None
    hotel_siret: str | None = None
    hotel_immatriculation: str | None = None
    hotel_numero_tva: str | None = None
    hotel_regime_tva: RegimeTVA | None = Field(default=None, sa_type=AutoString)
    hotel_taux_hebergement_pour_mille: int
    hotel_delai_paiement_jours: int
    hotel_conditions_paiement: str | None = None
    hotel_escompte: str | None = None
    hotel_penalites: str | None = None
    taxe_sejour_centimes: int
    total_ht_centimes: int
    total_tva_centimes: int
    total_prestations_ttc_centimes: int
    total_a_payer_centimes: int
    montant_regle_centimes: int
    solde_centimes: int
    remplace_numero: int | None = None
    remplace_date: date | None = None
    pdf_chemin: str | None = None
    pdf_empreinte: str | None = None

    reservation: Reservation = Relationship(back_populates="factures")
    lignes: list["LigneFacture"] = Relationship(
        back_populates="facture", sa_relationship_kwargs=_LA_BASE_DECIDE
    )
    ventilations: list["VentilationTVA"] = Relationship(
        back_populates="facture", sa_relationship_kwargs=_LA_BASE_DECIDE
    )
    reglements_figes: list["ReglementFacture"] = Relationship(
        back_populates="facture", sa_relationship_kwargs=_LA_BASE_DECIDE
    )


class LigneFacture(SQLModel, table=True):
    __tablename__ = "ligne_facture"
    __table_args__ = (UniqueConstraint("facture_id", "ordre"),)

    id: int | None = Field(default=None, primary_key=True)
    facture_id: int = Field(foreign_key="facture.id", ondelete="RESTRICT", index=True)
    ordre: int
    categorie: CategorieLigne = Field(sa_type=AutoString)
    libelle: str
    periode_debut: date | None = None
    periode_fin: date | None = None
    quantite: int
    prix_unitaire_ht_centimes: int
    prix_unitaire_ttc_centimes: int
    remise_centimes: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    taux_tva_pour_mille: int
    montant_ht_centimes: int
    montant_tva_centimes: int
    montant_ttc_centimes: int

    facture: Facture = Relationship(back_populates="lignes")


class VentilationTVA(SQLModel, table=True):
    __tablename__ = "ventilation_tva"
    __table_args__ = (UniqueConstraint("facture_id", "taux_tva_pour_mille"),)

    id: int | None = Field(default=None, primary_key=True)
    facture_id: int = Field(foreign_key="facture.id", ondelete="RESTRICT", index=True)
    taux_tva_pour_mille: int
    base_ht_centimes: int
    montant_tva_centimes: int

    facture: Facture = Relationship(back_populates="ventilations")


class ReglementFacture(SQLModel, table=True):
    __tablename__ = "reglement_facture"

    id: int | None = Field(default=None, primary_key=True)
    facture_id: int = Field(foreign_key="facture.id", ondelete="RESTRICT", index=True)
    date_reglement: date
    mode: str
    montant_centimes: int
    nature: NatureReglement = Field(sa_type=AutoString)

    facture: Facture = Relationship(back_populates="reglements_figes")
