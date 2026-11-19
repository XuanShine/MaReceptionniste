import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ma_receptionniste.consommation_ponctuelle import basculer, ecrire, lire, tout_cocher, tout_retirer
from ma_receptionniste.consultations import MODE_REGLEMENT_LABEL
from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import (
    TAUX_TVA_DEFAUT,
    TAUX_TVA_POUR_MILLE,
    EmissionImpossible,
    destinataire_de_sejour,
    emettre_facture,
    format_euros,
    obtenir_facture_courante,
    preparer_apercu,
)
from ma_receptionniste.models import (
    Chambre,
    ChambreVirtuelle,
    Client,
    Consommation,
    EtatChambre,
    Historique,
    ModeReglement,
    OccupationChambre,
    Produit,
    Reglement,
    Reservation,
    Sejour,
    StatutReservation,
    TypeChambre,
)
from ma_receptionniste.sejours import ChambreOccupee, chambre_libre, enregistrer_sejour

# Réservations sans personne identifiée : un seul client partagé, jamais une fiche individuelle.
NOM_CLIENT_PASSAGE = "CLIENT PASSAGE"
CHAMPS_CLIENT = ("nom", "pays", "telephone", "email", "adresse", "notes_client")
# Deux fiches ouvertes en même temps ne doivent pas créer deux clients de passage.
_VERROU_CLIENT_PASSAGE = threading.Lock()

# Champs du haut de la fiche séjour, dans l'ordre d'affichage et du journal.
CHAMPS_FICHE: dict[str, tuple[type[Client] | type[Reservation], str]] = {
    "nom": (Client, "Nom"),
    "pays": (Client, "Pays de nat."),
    "nom_occupant": (Reservation, "Occupant"),
    "partenaire": (Reservation, "Partenaire"),
    "statut": (Reservation, "Statut"),
    "type_voiture": (Reservation, "Type voiture"),
    "telephone": (Client, "Téléphone"),
    "email": (Client, "Email"),
    "adresse": (Client, "Adresse"),
    "notes": (Reservation, "Notes"),
    "notes_client": (Client, "Notes Client"),
    "facturation": (Reservation, "Facturation client"),
}
ATTRIBUTS_FICHE = {"notes_client": "notes"}


class FicheInvalide(ValueError):
    """Une valeur obligatoire de la fiche est vide."""


class FacturationImpossible(ValueError):
    """Une réservation annulée ne reçoit pas de facture."""


class CatalogueInvalide(ValueError):
    """Un libellé, une occupation ou un lien de chambre est refusé."""


class ProduitInvalide(ValueError):
    """Un produit ou une vente de produit est refusé."""


@dataclass(frozen=True)
class OperationPonctuelle:
    """Une modification de la note : une case, toutes les dates, ou le retrait du produit."""

    action: Literal["basculer", "tout_cocher", "tout_retirer"]
    chambre: str
    produit: str
    jour: date | None = None
    jours: tuple[date, ...] = ()
    nombre: int | None = None




def creer_type_chambre(
    libelle: str,
    *,
    nom_raccourci: str | None = None,
    prix_defaut: float = 0,
    prix_mini: float = 0,
    channel_manager_uniquement: bool = False,
) -> int:
    propre = _exiger_libelle(libelle)
    raccourci = _exiger_raccourci(nom_raccourci)
    defaut, mini = _exiger_prix(prix_defaut), _exiger_prix(prix_mini)
    with get_session() as session:
        if _type_existe(session, propre):
            raise CatalogueInvalide("Ce type existe déjà")
        if raccourci is not None and _raccourci_existe(session, raccourci):
            raise CatalogueInvalide("Ce nom raccourci existe déjà")
        type_chambre = TypeChambre(
            libelle=propre,
            nom_raccourci=raccourci,
            prix_defaut=defaut,
            prix_mini=mini,
            channel_manager_uniquement=channel_manager_uniquement,
        )
        session.add(type_chambre)
        _commit_type(session)
        return type_chambre.id


def enregistrer_type_chambre(
    type_chambre_id: int,
    libelle: str,
    nom_raccourci: str | None,
    prix_defaut: float,
    prix_mini: float,
    channel_manager_uniquement: bool,
    *,
    description: str | None = None,
) -> bool:
    propre = _exiger_libelle(libelle)
    raccourci = _exiger_raccourci(nom_raccourci)
    defaut, mini = _exiger_prix(prix_defaut), _exiger_prix(prix_mini)
    with get_session() as session:
        type_chambre = session.get(TypeChambre, type_chambre_id)
        if type_chambre is None:
            raise CatalogueInvalide("Ce type est introuvable")
        description_propre = type_chambre.description if description is None else description.strip()
        if (
            type_chambre.libelle == propre
            and type_chambre.description == description_propre
            and type_chambre.nom_raccourci == raccourci
            and type_chambre.prix_defaut == defaut
            and type_chambre.prix_mini == mini
            and bool(type_chambre.channel_manager_uniquement) == bool(channel_manager_uniquement)
        ):
            return False
        if type_chambre.libelle != propre and _type_existe(session, propre):
            raise CatalogueInvalide("Ce type existe déjà")
        if raccourci is not None and raccourci != type_chambre.nom_raccourci and _raccourci_existe(session, raccourci):
            raise CatalogueInvalide("Ce nom raccourci existe déjà")
        type_chambre.libelle = propre
        type_chambre.description = description_propre
        type_chambre.nom_raccourci = raccourci
        type_chambre.prix_defaut = defaut
        type_chambre.prix_mini = mini
        type_chambre.channel_manager_uniquement = channel_manager_uniquement
        session.add(type_chambre)
        _commit_type(session)
        return True


def renommer_type_chambre(type_chambre_id: int, libelle: str) -> bool:
    propre = _exiger_libelle(libelle)
    with get_session() as session:
        type_chambre = session.get(TypeChambre, type_chambre_id)
        if type_chambre is None:
            raise CatalogueInvalide("Ce type est introuvable")
        if type_chambre.libelle == propre:
            return False
        if _type_existe(session, propre):
            raise CatalogueInvalide("Ce type existe déjà")
        type_chambre.libelle = propre
        _commit_type(session)
        return True


def supprimer_type_chambre(type_chambre_id: int) -> None:
    with get_session() as session:
        type_chambre = session.get(TypeChambre, type_chambre_id)
        if type_chambre is None:
            raise CatalogueInvalide("Ce type est introuvable")
        if _chambre_cite(session, Chambre.type_chambre_id, type_chambre_id):
            raise CatalogueInvalide("Ce type est utilisé par une chambre")
        if _virtuelle_cite(session, type_chambre_id):
            raise CatalogueInvalide("Ce type est utilisé par une chambre virtuelle")
        session.delete(type_chambre)
        _commit_utilise(session, "Ce type est utilisé par une chambre")


def creer_chambre_virtuelle(
    type_chambre_id: int,
    nom_raccourci: str | None,
    prix_defaut: float | str | None,
    prix_mini: float | str | None,
    *,
    description: str = "",
) -> int:
    raccourci = _exiger_raccourci_obligatoire(nom_raccourci)
    defaut, mini = _exiger_prix_present(prix_defaut), _exiger_prix_present(prix_mini)
    with get_session() as session:
        if session.get(TypeChambre, type_chambre_id) is None:
            raise CatalogueInvalide("Ce type est introuvable")
        if _raccourci_virtuel_existe(session, raccourci):
            raise CatalogueInvalide("Ce nom raccourci existe déjà")
        virtuelle = ChambreVirtuelle(
            type_chambre_id=type_chambre_id,
            description=description.strip(),
            nom_raccourci=raccourci,
            prix_defaut=defaut,
            prix_mini=mini,
        )
        session.add(virtuelle)
        _commit_type(session)
        return virtuelle.id


def enregistrer_chambre_virtuelle(
    chambre_virtuelle_id: int,
    nom_raccourci: str | None,
    prix_defaut: float | str | None,
    prix_mini: float | str | None,
    *,
    description: str | None = None,
) -> bool:
    raccourci = _exiger_raccourci_obligatoire(nom_raccourci)
    defaut, mini = _exiger_prix_present(prix_defaut), _exiger_prix_present(prix_mini)
    with get_session() as session:
        virtuelle = session.get(ChambreVirtuelle, chambre_virtuelle_id)
        if virtuelle is None:
            raise CatalogueInvalide("Cette chambre virtuelle est introuvable")
        description_propre = virtuelle.description if description is None else description.strip()
        if (
            virtuelle.nom_raccourci == raccourci
            and virtuelle.description == description_propre
            and virtuelle.prix_defaut == defaut
            and virtuelle.prix_mini == mini
        ):
            return False
        if raccourci != virtuelle.nom_raccourci and _raccourci_virtuel_existe(session, raccourci, virtuelle.id):
            raise CatalogueInvalide("Ce nom raccourci existe déjà")
        virtuelle.nom_raccourci = raccourci
        virtuelle.description = description_propre
        virtuelle.prix_defaut = defaut
        virtuelle.prix_mini = mini
        session.add(virtuelle)
        _commit_type(session)
        return True


def supprimer_chambre_virtuelle(chambre_virtuelle_id: int) -> None:
    with get_session() as session:
        virtuelle = session.get(ChambreVirtuelle, chambre_virtuelle_id)
        if virtuelle is None:
            raise CatalogueInvalide("Cette chambre virtuelle est introuvable")
        session.delete(virtuelle)
        session.commit()


def creer_occupation_chambre(nombre_personnes: int, type_lits: str) -> int:
    personnes, lits = _exiger_occupation(nombre_personnes, type_lits)
    with get_session() as session:
        if _occupation_existe(session, personnes, lits):
            raise CatalogueInvalide("Cette occupation existe déjà")
        occupation = OccupationChambre(nombre_personnes=personnes, type_lits=lits)
        session.add(occupation)
        _commit_unique(session, "Cette occupation existe déjà")
        return occupation.id


def modifier_occupation_chambre(occupation_chambre_id: int, nombre_personnes: int, type_lits: str) -> bool:
    personnes, lits = _exiger_occupation(nombre_personnes, type_lits)
    with get_session() as session:
        occupation = session.get(OccupationChambre, occupation_chambre_id)
        if occupation is None:
            raise CatalogueInvalide("Cette occupation est introuvable")
        if occupation.nombre_personnes == personnes and occupation.type_lits == lits:
            return False
        if _occupation_existe(session, personnes, lits):
            raise CatalogueInvalide("Cette occupation existe déjà")
        occupation.nombre_personnes = personnes
        occupation.type_lits = lits
        _commit_unique(session, "Cette occupation existe déjà")
        return True


def supprimer_occupation_chambre(occupation_chambre_id: int) -> None:
    with get_session() as session:
        occupation = session.get(OccupationChambre, occupation_chambre_id)
        if occupation is None:
            raise CatalogueInvalide("Cette occupation est introuvable")
        if _chambre_cite(session, Chambre.occupation_chambre_id, occupation_chambre_id):
            raise CatalogueInvalide("Cette occupation est utilisée par une chambre")
        session.delete(occupation)
        _commit_utilise(session, "Cette occupation est utilisée par une chambre")


def creer_chambre(
    nom: str,
    position: int,
    *,
    type_chambre_id: int | None = None,
    occupation_chambre_id: int | None = None,
    etage: int = 0,
    chambres_virtuelles_ids: list[int] | None = None,
) -> int:
    etage = _exiger_etage(etage)
    with get_session() as session:
        _exiger_liens(session, type_chambre_id, occupation_chambre_id)
        virtuelles = _exiger_chambres_virtuelles(session, chambres_virtuelles_ids or [])
        chambre = Chambre(
            nom=nom.strip(),
            position=position,
            etage=etage,
            type_chambre_id=type_chambre_id,
            occupation_chambre_id=occupation_chambre_id,
        )
        chambre.chambres_virtuelles = virtuelles
        session.add(chambre)
        _commit_liens(session)
        return chambre.id


def modifier_etage_chambre(chambre_id: int, etage: int) -> bool:
    etage = _exiger_etage(etage)
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            raise CatalogueInvalide("Cette chambre est introuvable")
        if chambre.etage == etage:
            return False
        chambre.etage = etage
        session.add(chambre)
        session.commit()
        return True


def _exiger_etage(etage: int) -> int:
    if isinstance(etage, bool) or not isinstance(etage, (int, float)) or not float(etage).is_integer():
        raise CatalogueInvalide("L'étage doit être un nombre entier")
    return int(etage)


def attribuer_type_chambre(chambre_id: int, type_chambre_id: int | None) -> bool:
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None or chambre.type_chambre_id == type_chambre_id:
            return False
        if type_chambre_id is not None and session.get(TypeChambre, type_chambre_id) is None:
            raise CatalogueInvalide("Ce type est introuvable")
        chambre.type_chambre_id = type_chambre_id
        session.add(chambre)
        _commit_lien(session, "Ce type est introuvable")
        return True


def attribuer_chambres_virtuelles(chambre_id: int, chambres_virtuelles_ids: list[int]) -> bool:
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            raise CatalogueInvalide("Cette chambre est introuvable")
        virtuelles = _exiger_chambres_virtuelles(session, chambres_virtuelles_ids)
        if {virtuelle.id for virtuelle in chambre.chambres_virtuelles} == {virtuelle.id for virtuelle in virtuelles}:
            return False
        chambre.chambres_virtuelles = virtuelles
        _commit_lien(session, "Une chambre virtuelle est introuvable")
        return True


def attribuer_occupation_chambre(chambre_id: int, occupation_chambre_id: int | None) -> bool:
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None or chambre.occupation_chambre_id == occupation_chambre_id:
            return False
        if occupation_chambre_id is not None and session.get(OccupationChambre, occupation_chambre_id) is None:
            raise CatalogueInvalide("Cette occupation est introuvable")
        chambre.occupation_chambre_id = occupation_chambre_id
        session.add(chambre)
        _commit_lien(session, "Cette occupation est introuvable")
        return True


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
    email: str | None = None,
    telephone: str | None = None,
    adresse: str | None = None,
    notes: str | None = None,
    pays: str | None = None,
) -> int:
    nom_propre = nom.strip()
    if nom_propre == NOM_CLIENT_PASSAGE:
        with _VERROU_CLIENT_PASSAGE, get_session() as session:
            client = _client_passage(session)
            session.commit()
            return client.id
    with get_session() as session:
        client = Client(
            nom=nom_propre,
            pays=_vide(pays),
            email=_vide(email),
            telephone=_vide(telephone),
            adresse=_vide(adresse),
            notes=_vide(notes),
        )
        session.add(client)
        session.commit()
        return client.id


def creer_reservation(client_id: int | None = None) -> int:
    if client_id is None:
        with _VERROU_CLIENT_PASSAGE:
            return _creer_reservation(None)
    return _creer_reservation(client_id)


def _creer_reservation(client_id: int | None) -> int:
    with get_session() as session:
        if client_id is None:
            client_id = _client_passage(session).id
        reservation = Reservation(client_id=client_id)
        session.add(reservation)
        session.commit()
        return reservation.id


def ajouter_sejour(
    reservation_id: int,
    chambre_id: int,
    date_debut: date,
    date_fin: date,
    nom_client: str | None = None,
    adultes: int = 1,
    enfants: int = 0,
    prix_nuit_centimes: int = 0,
    user_id: int | None = None,
) -> int:
    with get_session() as session:
        sejour = enregistrer_sejour(
            session,
            reservation_id=reservation_id,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            nom_client=_vide(nom_client),
            adultes=adultes,
            enfants=enfants,
            prix_nuit_centimes=prix_nuit_centimes,
        )
        _journaliser(session, reservation_id, user_id, f"Séjour ajouté : {_decrire(session, sejour)}")
        session.commit()
        return sejour.id


def modifier_sejour(
    sejour_id: int,
    chambre_id: int,
    date_debut: date,
    date_fin: date,
    adultes: int,
    enfants: int,
    prix_nuit_centimes: int,
    nom_client: str | None,
    user_id: int | None = None,
) -> None:
    with get_session() as session:
        reservation_id = session.exec(select(Sejour.reservation_id).where(Sejour.id == sejour_id)).first()
        if reservation_id is None:
            return
        sejour = enregistrer_sejour(
            session,
            reservation_id=reservation_id,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            nom_client=_vide(nom_client),
            adultes=adultes,
            enfants=enfants,
            prix_nuit_centimes=prix_nuit_centimes,
            ignorer_sejour_id=sejour_id,
        )
        _journaliser(session, reservation_id, user_id, f"Séjour modifié : {_decrire(session, sejour)}")
        session.commit()


def supprimer_sejour(sejour_id: int, user_id: int | None = None) -> None:
    with get_session() as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            return
        _journaliser(session, sejour.reservation_id, user_id, f"Séjour supprimé : {_decrire(session, sejour)}")
        session.delete(sejour)
        session.commit()


def modifier_consommation_ponctuelle(
    reservation_id: int, operation: OperationPonctuelle, user_id: int | None
) -> None:
    """Lit, modifie et réécrit la note dans la même transaction que le journal.

    Une note illisible lève ``NoteIllisible`` avant toute écriture.
    """
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            raise FicheInvalide("Réservation introuvable")
        actuelles = lire(reservation.notes_internes)
        nouvelles = _appliquer_ponctuelle(actuelles, operation)
        if ecrire(nouvelles) == ecrire(actuelles):
            return
        reservation.notes_internes = ecrire(nouvelles) or None
        session.add(reservation)
        _journaliser(session, reservation_id, user_id, _decrire_ponctuelle(operation))
        session.commit()


def _appliquer_ponctuelle(donnees: dict, operation: OperationPonctuelle) -> dict:
    if operation.action == "basculer":
        if operation.jour is None:
            raise ValueError("La date est obligatoire")
        return basculer(donnees, operation.chambre, operation.produit, operation.jour, operation.nombre)
    if operation.action == "tout_cocher":
        if operation.nombre is None:
            raise ValueError("Le nombre est obligatoire")
        return tout_cocher(donnees, operation.chambre, operation.produit, operation.jours, operation.nombre)
    if operation.action == "tout_retirer":
        return tout_retirer(donnees, operation.chambre, operation.produit)
    raise ValueError("Opération inconnue")


def _decrire_ponctuelle(operation: OperationPonctuelle) -> str:
    lieu = f"Chambre {operation.chambre}"
    if operation.action == "basculer":
        valeur = "retiré" if operation.nombre is None else str(operation.nombre)
        return f"{operation.produit} · {lieu} · {operation.jour:%d/%m} : {valeur}"
    if operation.action == "tout_cocher":
        return f"{operation.produit} · {lieu} · tout sélectionné : {operation.nombre}"
    return f"{operation.produit} · {lieu} · tout retiré"


def ajouter_consommation(
    reservation_id: int, libelle: str, quantite: int, prix_unitaire_centimes: int, user_id: int | None = None
) -> int:
    with get_session() as session:
        consommation = Consommation(
            reservation_id=reservation_id,
            libelle=libelle.strip(),
            quantite=quantite,
            prix_unitaire_centimes=prix_unitaire_centimes,
            taux_tva_pour_mille=TAUX_TVA_DEFAUT,
        )
        session.add(consommation)
        montant = format_euros(quantite * prix_unitaire_centimes)
        _journaliser(
            session, reservation_id, user_id, f"Consommation ajoutée : {quantite} × {consommation.libelle} ({montant})"
        )
        session.commit()
        return consommation.id


def creer_produit(
    nom: str,
    prix_unitaire_centimes: int,
    *,
    taux_tva_pour_mille: int = TAUX_TVA_DEFAUT,
    ponctuel: bool = False,
) -> int:
    propre = _exiger_nom_produit(nom)
    prix = _exiger_centimes(prix_unitaire_centimes)
    taux = _exiger_taux_tva(taux_tva_pour_mille)
    with get_session() as session:
        if _produit_nom_pris(session, propre):
            raise ProduitInvalide("Ce produit existe déjà")
        produit = Produit(
            nom=propre,
            prix_unitaire_centimes=prix,
            taux_tva_pour_mille=taux,
            actif=True,
            ponctuel=bool(ponctuel),
        )
        session.add(produit)
        _commit_produit(session)
        return produit.id


def modifier_produit(
    produit_id: int,
    nom: str,
    prix_unitaire_centimes: int,
    *,
    taux_tva_pour_mille: int = TAUX_TVA_DEFAUT,
    ponctuel: bool | None = None,
) -> bool:
    propre = _exiger_nom_produit(nom)
    prix = _exiger_centimes(prix_unitaire_centimes)
    taux = _exiger_taux_tva(taux_tva_pour_mille)
    with get_session() as session:
        produit = session.get(Produit, produit_id)
        if produit is None:
            raise ProduitInvalide("Ce produit est introuvable")
        # None laisse le drapeau tel quel : un ancien appel qui ne connaît pas « ponctuel » ne l'efface pas.
        voulu = bool(produit.ponctuel) if ponctuel is None else bool(ponctuel)
        if (
            produit.nom == propre
            and produit.prix_unitaire_centimes == prix
            and produit.taux_tva_pour_mille == taux
            and bool(produit.ponctuel) == voulu
        ):
            return False
        if produit.nom != propre and _produit_nom_pris(session, propre, sauf=produit_id):
            raise ProduitInvalide("Ce produit existe déjà")
        produit.nom = propre
        produit.prix_unitaire_centimes = prix
        produit.taux_tva_pour_mille = taux
        produit.ponctuel = voulu
        session.add(produit)
        _commit_produit(session)
        return True


def definir_produit_actif(produit_id: int, actif: bool) -> bool:
    with get_session() as session:
        produit = session.get(Produit, produit_id)
        if produit is None:
            raise ProduitInvalide("Ce produit est introuvable")
        if bool(produit.actif) == bool(actif):
            return False
        produit.actif = bool(actif)
        session.add(produit)
        session.commit()
        return True


def ajouter_consommation_produit(
    reservation_id: int,
    produit_id: int,
    quantite: int,
    prix_unitaire_centimes: int,
    user_id: int | None = None,
) -> int:
    quantite = _exiger_quantite(quantite)
    prix = _exiger_centimes(prix_unitaire_centimes)
    with get_session() as session:
        if session.get(Reservation, reservation_id) is None:
            raise ProduitInvalide("Cette réservation est introuvable")
        produit = session.get(Produit, produit_id)
        if produit is None:
            raise ProduitInvalide("Ce produit est introuvable")
        if not produit.actif:
            raise ProduitInvalide("Ce produit n'est plus en vente")
        consommation = Consommation(
            reservation_id=reservation_id,
            libelle=produit.nom,
            quantite=quantite,
            prix_unitaire_centimes=prix,
            taux_tva_pour_mille=produit.taux_tva_pour_mille,
        )
        session.add(consommation)
        montant = format_euros(quantite * prix)
        _journaliser(
            session,
            reservation_id,
            user_id,
            f"Consommation ajoutée : {quantite} × {consommation.libelle} ({montant})",
        )
        try:
            session.commit()
        except IntegrityError as erreur:
            session.rollback()
            if _nom_sqlite(erreur) == "SQLITE_CONSTRAINT_FOREIGNKEY":
                raise ProduitInvalide("Cette réservation est introuvable") from erreur
            raise
        return consommation.id


def modifier_consommation(
    consommation_id: int,
    quantite: int,
    prix_unitaire_centimes: int,
    jour: date,
    user_id: int | None = None,
) -> bool:
    """Met à jour la ligne vendue. Le catalogue et le libellé restent inchangés."""
    quantite = _exiger_quantite(quantite)
    prix = _exiger_centimes(prix_unitaire_centimes)
    jour = _exiger_jour(jour)
    with get_session() as session:
        consommation = session.get(Consommation, consommation_id)
        if consommation is None:
            raise ProduitInvalide("Cette consommation est introuvable")
        if (
            consommation.quantite == quantite
            and consommation.prix_unitaire_centimes == prix
            and _en_local(consommation.date).date() == jour
        ):
            return False
        consommation.quantite = quantite
        consommation.prix_unitaire_centimes = prix
        consommation.date = _poser_jour(consommation.date, jour)
        session.add(consommation)
        montant = format_euros(quantite * prix)
        _journaliser(
            session,
            consommation.reservation_id,
            user_id,
            f"Consommation modifiée : {quantite} × {consommation.libelle} ({montant}) le {jour:%d/%m/%Y}",
        )
        session.commit()
        return True


def ajouter_reglement(
    reservation_id: int, mode: ModeReglement, montant_centimes: int, user_id: int | None = None
) -> int:
    with get_session() as session:
        reglement = Reglement(reservation_id=reservation_id, mode=mode, montant_centimes=montant_centimes)
        session.add(reglement)
        _journaliser(
            session,
            reservation_id,
            user_id,
            f"Règlement {MODE_REGLEMENT_LABEL[ModeReglement(mode)]} : {format_euros(montant_centimes)}",
        )
        session.commit()
        return reglement.id


def annuler_reservation(reservation_id: int, user_id: int | None = None) -> None:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None or reservation.statut == StatutReservation.annulee:
            return
        reservation.statut = StatutReservation.annulee
        session.add(reservation)
        _journaliser(session, reservation_id, user_id, "Réservation annulée")
        session.commit()


def reprendre_reservation(reservation_id: int, user_id: int | None) -> None:
    """Une annulation libère les chambres : les reprendre échoue si une autre réservation les a prises."""
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None or reservation.statut != StatutReservation.annulee:
            return
        sejours = session.exec(select(Sejour).where(Sejour.reservation_id == reservation_id)).all()
        for sejour in sejours:
            if not chambre_libre(session, sejour.chambre_id, sejour.date_debut, sejour.date_fin, sejour.id):
                raise ChambreOccupee("La chambre est déjà occupée sur cette période")
        reservation.statut = StatutReservation.confirmee
        session.add(reservation)
        _journaliser(session, reservation_id, user_id, "Réservation reprise")
        session.commit()


def ajouter_note(reservation_id: int, user_id: int | None, description: str) -> None:
    with get_session() as session:
        _journaliser(session, reservation_id, user_id, description.strip())
        session.commit()


def champs_modifies(avant: dict, apres: dict) -> list[str]:
    """Clés de CHAMPS_FICHE présentes dans apres dont la valeur normalisée diffère de avant."""
    return [cle for cle in CHAMPS_FICHE if cle in apres and _comparable(apres[cle]) != _comparable(avant.get(cle))]


def enregistrer_fiche(
    reservation_id: int, user_id: int | None, valeurs: dict, client_id: int | None = None
) -> list[str]:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            return []
        actuel = reservation.client
        if client_id is None or client_id == actuel.id:
            cible = actuel
            changement = False
        else:
            cible = session.get(Client, client_id)
            if cible is None:
                raise FicheInvalide("Ce client est introuvable")
            changement = True
        # Les valeurs affichées sont celles du client choisi : les écrire sur l'ancien mélangerait deux personnes.
        if _est_passage(cible) and _coordonnees_modifiees(cible, valeurs):
            raise FicheInvalide("Le client CLIENT PASSAGE ne peut pas être modifié")
        if not _est_passage(cible) and "nom" in valeurs and _vide(valeurs["nom"]) == NOM_CLIENT_PASSAGE:
            raise FicheInvalide("Le nom CLIENT PASSAGE est réservé")
        if "nom" in valeurs and _vide(valeurs["nom"]) is None and not _est_passage(cible):
            raise FicheInvalide("Le nom du client est obligatoire")
        cibles = {Client: cible, Reservation: reservation}
        avant = {
            cle: getattr(cibles[modele], ATTRIBUTS_FICHE.get(cle, cle)) for cle, (modele, _) in CHAMPS_FICHE.items()
        }
        modifies = champs_modifies(avant, valeurs)
        if not modifies and not changement:
            return []
        if changement:
            reservation.client = cible
            session.add(reservation)
        for cle in modifies:
            modele, _ = CHAMPS_FICHE[cle]
            setattr(cibles[modele], ATTRIBUTS_FICHE.get(cle, cle), _valeur_fiche(cle, valeurs[cle]))
            session.add(cibles[modele])
        libelles = (["Client"] if changement else []) + [CHAMPS_FICHE[cle][1] for cle in modifies]
        _journaliser(session, reservation_id, user_id, f"Fiche modifiée : {', '.join(libelles)}")
        session.commit()
        return libelles


def facturer(reservation_id: int, user_id: int | None) -> int:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            raise FacturationImpossible("Réservation introuvable")
        if reservation.statut == StatutReservation.annulee:
            raise FacturationImpossible("Une réservation annulée ne peut pas être facturée")
        if reservation.numero_facture is not None:
            return reservation.numero_facture
    try:
        apercu = preparer_apercu(reservation_id, destinataire_de_sejour(reservation_id))
        return emettre_facture(apercu, uuid4(), user_id=user_id).numero
    except EmissionImpossible as erreur:
        courante = obtenir_facture_courante(reservation_id)
        if courante is not None:
            return courante.numero
        raise FacturationImpossible(str(erreur)) from erreur


def _client_passage(session: Session) -> Client:
    client = session.exec(select(Client).where(Client.nom == NOM_CLIENT_PASSAGE).order_by(Client.id)).first()
    if client is not None:
        return client
    client = Client(nom=NOM_CLIENT_PASSAGE)
    session.add(client)
    session.flush()
    return client


def _est_passage(client: Client) -> bool:
    return client.nom.strip() == NOM_CLIENT_PASSAGE


def _coordonnees_modifiees(client: Client, valeurs: dict) -> bool:
    return any(
        cle in valeurs and _comparable(valeurs[cle]) != _comparable(getattr(client, ATTRIBUTS_FICHE.get(cle, cle)))
        for cle in CHAMPS_CLIENT
    )


def _journaliser(session: Session, reservation_id: int, user_id: int | None, description: str) -> None:
    session.add(
        Historique(reservation_id=reservation_id, user_id=user_id, description=description, date=datetime.now(UTC))
    )


def _decrire(session: Session, sejour: Sejour) -> str:
    chambre = session.get(Chambre, sejour.chambre_id)
    return f"chambre {chambre.nom} du {sejour.date_debut:%d/%m/%Y} au {sejour.date_fin:%d/%m/%Y}"


def _comparable(valeur: object) -> object:
    if isinstance(valeur, StatutReservation):
        return valeur.value
    return valeur if isinstance(valeur, bool) else _vide(valeur)


def _valeur_fiche(cle: str, valeur: object) -> object:
    normalise = _comparable(valeur)
    if cle == "statut":
        if normalise not in {statut.value for statut in StatutReservation}:
            raise FicheInvalide("Statut inconnu")
        return StatutReservation(str(normalise))
    return normalise


def _vide(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None


def _exiger_nom_produit(nom: str | None) -> str:
    propre = _vide(nom)
    if propre is None:
        raise ProduitInvalide("Le nom est obligatoire")
    return propre


def _exiger_centimes(prix: int) -> int:
    if isinstance(prix, bool) or not isinstance(prix, int):
        raise ProduitInvalide("Le prix doit être un entier de centimes")
    if prix < 0:
        raise ProduitInvalide("Le prix ne peut pas être négatif")
    return prix


def _exiger_taux_tva(taux: int) -> int:
    if isinstance(taux, bool) or not isinstance(taux, int) or taux not in TAUX_TVA_POUR_MILLE:
        raise ProduitInvalide("Le taux de TVA n'est pas reconnu")
    return taux


def _exiger_quantite(quantite: int) -> int:
    if isinstance(quantite, bool) or not isinstance(quantite, int) or quantite <= 0:
        raise ProduitInvalide("La quantité doit être un entier supérieur à 0")
    return quantite


def _exiger_jour(jour: date) -> date:
    if type(jour) is not date:
        raise ProduitInvalide("La date n'est pas reconnue")
    return jour


def _en_local(moment: datetime) -> datetime:
    """SQLite rend les horodatages sans fuseau ; l'application les écrit en UTC."""
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone()


def _poser_jour(moment: datetime, jour: date) -> datetime:
    """Change le jour affiché et conserve l'heure locale, y compris au changement d'heure.

    astimezone() rend un décalage fixe (CEST, CET). On l'ajuste jusqu'à ce que l'heure affichée
    soit celle d'origine.
    """
    local = _en_local(moment)
    voulu = datetime(jour.year, jour.month, jour.day, local.hour, local.minute, local.second, local.microsecond)
    candidat = voulu.replace(tzinfo=UTC)
    for _ in range(3):
        affiche = _en_local(candidat).replace(tzinfo=None)
        decalage = voulu - affiche
        if decalage == timedelta(0):
            return candidat
        candidat += decalage
    return candidat


def _produit_nom_pris(session: Session, nom: str, sauf: int | None = None) -> bool:
    requete = select(Produit.id).where(Produit.nom == nom)
    if sauf is not None:
        requete = requete.where(Produit.id != sauf)
    return session.exec(requete).first() is not None


def _commit_produit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        session.rollback()
        if _nom_sqlite(erreur) == "SQLITE_CONSTRAINT_UNIQUE":
            raise ProduitInvalide("Ce produit existe déjà") from erreur
        raise


def _exiger_libelle(libelle: str | None) -> str:
    propre = _vide(libelle)
    if propre is None:
        raise CatalogueInvalide("Le libellé est obligatoire")
    return propre


def _exiger_raccourci(nom_raccourci: str | None) -> str | None:
    propre = _vide(nom_raccourci)
    if propre is not None and len(propre) > 4:
        raise CatalogueInvalide("Le nom raccourci tient sur 4 caractères")
    return propre


def _exiger_raccourci_obligatoire(nom_raccourci: str | None) -> str:
    propre = _exiger_raccourci(nom_raccourci)
    if propre is None:
        raise CatalogueInvalide("Le nom raccourci est obligatoire")
    return propre


def _exiger_prix(prix: float) -> float:
    try:
        valeur = round(float(prix), 2)
    except (TypeError, ValueError) as erreur:
        raise CatalogueInvalide("Le prix ne peut pas être négatif") from erreur
    if valeur < 0:
        raise CatalogueInvalide("Le prix ne peut pas être négatif")
    return valeur


def _exiger_prix_present(prix: float | str | None) -> float:
    if prix is None or (isinstance(prix, str) and not prix.strip()):
        raise CatalogueInvalide("Le prix est obligatoire")
    return _exiger_prix(prix)


def _exiger_personnes(nombre_personnes: int) -> int:
    if nombre_personnes < 1:
        raise CatalogueInvalide("Le nombre de personnes doit être au moins 1")
    return nombre_personnes


def _exiger_lits(type_lits: str | None) -> str:
    propre = _vide(type_lits)
    if propre is None:
        raise CatalogueInvalide("Le type de lits est obligatoire")
    return propre


def _exiger_occupation(nombre_personnes: int, type_lits: str | None) -> tuple[int, str]:
    return _exiger_personnes(nombre_personnes), _exiger_lits(type_lits)


def _exiger_liens(session: Session, type_chambre_id: int | None, occupation_chambre_id: int | None) -> None:
    if type_chambre_id is not None and session.get(TypeChambre, type_chambre_id) is None:
        raise CatalogueInvalide("Ce type est introuvable")
    if occupation_chambre_id is not None and session.get(OccupationChambre, occupation_chambre_id) is None:
        raise CatalogueInvalide("Cette occupation est introuvable")


def _exiger_chambres_virtuelles(session: Session, identifiants: list[int]) -> list[ChambreVirtuelle]:
    ids = set(identifiants)
    if not ids:
        return []
    virtuelles = list(session.exec(select(ChambreVirtuelle).where(ChambreVirtuelle.id.in_(ids))))
    if len(virtuelles) != len(ids):
        raise CatalogueInvalide("Une chambre virtuelle est introuvable")
    return virtuelles


def _type_existe(session: Session, libelle: str) -> bool:
    return session.exec(select(TypeChambre.id).where(TypeChambre.libelle == libelle)).first() is not None


def _raccourci_existe(session: Session, nom_raccourci: str) -> bool:
    return session.exec(select(TypeChambre.id).where(TypeChambre.nom_raccourci == nom_raccourci)).first() is not None


def _raccourci_virtuel_existe(session: Session, nom_raccourci: str, sauf: int | None = None) -> bool:
    requete = select(ChambreVirtuelle.id).where(ChambreVirtuelle.nom_raccourci == nom_raccourci)
    if sauf is not None:
        requete = requete.where(ChambreVirtuelle.id != sauf)
    return session.exec(requete).first() is not None


def _virtuelle_cite(session: Session, type_chambre_id: int) -> bool:
    return (
        session.exec(select(ChambreVirtuelle.id).where(ChambreVirtuelle.type_chambre_id == type_chambre_id)).first()
        is not None
    )


def _occupation_existe(session: Session, personnes: int, lits: str) -> bool:
    return (
        session.exec(
            select(OccupationChambre.id).where(
                OccupationChambre.nombre_personnes == personnes,
                OccupationChambre.type_lits == lits,
            )
        ).first()
        is not None
    )


def _chambre_cite(session: Session, colonne, valeur: int) -> bool:
    return session.exec(select(Chambre.id).where(colonne == valeur)).first() is not None


def _nom_sqlite(erreur: IntegrityError) -> str:
    return getattr(erreur.orig, "sqlite_errorname", "")


def _commit_type(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if _nom_sqlite(erreur) != "SQLITE_CONSTRAINT_UNIQUE":
            raise
        if "nom_raccourci" in str(erreur.orig):
            raise CatalogueInvalide("Ce nom raccourci existe déjà") from erreur
        raise CatalogueInvalide("Ce type existe déjà") from erreur


def _commit_unique(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if _nom_sqlite(erreur) == "SQLITE_CONSTRAINT_UNIQUE":
            raise CatalogueInvalide(message) from erreur
        raise


def _commit_utilise(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if _nom_sqlite(erreur) in {"SQLITE_CONSTRAINT_FOREIGNKEY", "SQLITE_CONSTRAINT_TRIGGER"}:
            raise CatalogueInvalide(message) from erreur
        raise


def _commit_lien(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if _nom_sqlite(erreur) == "SQLITE_CONSTRAINT_FOREIGNKEY":
            raise CatalogueInvalide(message) from erreur
        raise


def _commit_liens(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if _nom_sqlite(erreur) == "SQLITE_CONSTRAINT_FOREIGNKEY":
            raise CatalogueInvalide("Ce type, cette occupation ou cette chambre virtuelle est introuvable") from erreur
        raise
