from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select, update

from ma_receptionniste.consultations import MODE_REGLEMENT_LABEL
from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import format_euros
from ma_receptionniste.models import (
    Chambre,
    Client,
    Consommation,
    EtatChambre,
    Historique,
    ModeReglement,
    OccupationChambre,
    Reglement,
    Reservation,
    Sejour,
    StatutReservation,
    TypeChambre,
)
from ma_receptionniste.sejours import enregistrer_sejour

# Champs du haut de la fiche séjour, dans l'ordre d'affichage et du journal.
CHAMPS_FICHE: dict[str, tuple[type[Client] | type[Reservation], str]] = {
    "nom": (Client, "Nom"),
    "pays": (Client, "Pays de nat."),
    "partenaire": (Reservation, "Partenaire"),
    "traitee": (Reservation, "Traité"),
    "type_voiture": (Reservation, "Type voiture"),
    "telephone": (Client, "Téléphone"),
    "email": (Client, "Email"),
    "adresse": (Client, "Adresse"),
    "notes": (Reservation, "Notes"),
    "notes_internes": (Reservation, "Notes internes"),
    "notes_tempo": (Reservation, "Notes tempo"),
    "facturation": (Reservation, "Facturation client"),
}


class FicheInvalide(ValueError):
    """Une valeur obligatoire de la fiche est vide."""


class FacturationImpossible(ValueError):
    """Une réservation annulée ne reçoit pas de facture."""


class CatalogueInvalide(ValueError):
    """Le message est affiché tel quel : libellé vide, doublon, lien inconnu ou encore cité."""


def creer_type_chambre(libelle: str) -> int:
    propre = _exiger_libelle(libelle)
    with get_session() as session:
        if _type_existe(session, propre):
            raise CatalogueInvalide("Ce type existe déjà")
        type_chambre = TypeChambre(libelle=propre)
        session.add(type_chambre)
        _commit_unique(session, "Ce type existe déjà")
        return type_chambre.id


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
        _commit_unique(session, "Ce type existe déjà")
        return True


def supprimer_type_chambre(type_chambre_id: int) -> None:
    with get_session() as session:
        type_chambre = session.get(TypeChambre, type_chambre_id)
        if type_chambre is None:
            raise CatalogueInvalide("Ce type est introuvable")
        if _chambre_cite(session, Chambre.type_chambre_id, type_chambre_id):
            raise CatalogueInvalide("Ce type est utilisé par une chambre")
        session.delete(type_chambre)
        _commit_utilise(session, "Ce type est utilisé par une chambre")


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
) -> int:
    with get_session() as session:
        _exiger_liens(session, type_chambre_id, occupation_chambre_id)
        chambre = Chambre(
            nom=nom.strip(),
            position=position,
            type_chambre_id=type_chambre_id,
            occupation_chambre_id=occupation_chambre_id,
        )
        session.add(chambre)
        _commit_liens(session)
        return chambre.id


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
    with get_session() as session:
        client = Client(
            nom=nom.strip(),
            pays=_vide(pays),
            email=_vide(email),
            telephone=_vide(telephone),
            adresse=_vide(adresse),
            notes=_vide(notes),
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
    date_debut: date,
    date_fin: date,
    nom_client: str | None = None,
    adultes: int = 1,
    enfants: int = 0,
    prix_nuit_centimes: int = 0,
    remise_pct: int = 0,
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
            remise_pct=remise_pct,
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
    remise_pct: int,
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
            remise_pct=remise_pct,
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


def ajouter_consommation(
    reservation_id: int, libelle: str, quantite: int, prix_unitaire_centimes: int, user_id: int | None = None
) -> int:
    with get_session() as session:
        consommation = Consommation(
            reservation_id=reservation_id,
            libelle=libelle.strip(),
            quantite=quantite,
            prix_unitaire_centimes=prix_unitaire_centimes,
        )
        session.add(consommation)
        montant = format_euros(quantite * prix_unitaire_centimes)
        _journaliser(
            session, reservation_id, user_id, f"Consommation ajoutée : {quantite} × {consommation.libelle} ({montant})"
        )
        session.commit()
        return consommation.id


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


def ajouter_note(reservation_id: int, user_id: int | None, description: str) -> None:
    with get_session() as session:
        _journaliser(session, reservation_id, user_id, description.strip())
        session.commit()


def champs_modifies(avant: dict, apres: dict) -> list[str]:
    """Clés de CHAMPS_FICHE présentes dans apres dont la valeur normalisée diffère de avant."""
    return [cle for cle in CHAMPS_FICHE if cle in apres and _normaliser(apres[cle]) != avant.get(cle)]


def enregistrer_fiche(reservation_id: int, user_id: int | None, valeurs: dict) -> list[str]:
    if "nom" in valeurs and _vide(valeurs["nom"]) is None:
        raise FicheInvalide("Le nom du client est obligatoire")
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            return []
        cibles = {Client: reservation.client, Reservation: reservation}
        avant = {cle: getattr(cibles[modele], cle) for cle, (modele, _) in CHAMPS_FICHE.items()}
        modifies = champs_modifies(avant, valeurs)
        if not modifies:
            return []
        for cle in modifies:
            modele, _ = CHAMPS_FICHE[cle]
            setattr(cibles[modele], cle, _normaliser(valeurs[cle]))
            session.add(cibles[modele])
        libelles = [CHAMPS_FICHE[cle][1] for cle in modifies]
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
        # Une seule instruction : le numéro suivant est calculé et posé sans fenêtre pour un second poste.
        emise = session.exec(
            update(Reservation)
            .where(Reservation.id == reservation_id, Reservation.numero_facture.is_(None))
            .values(
                numero_facture=select(func.coalesce(func.max(Reservation.numero_facture), 0) + 1).scalar_subquery(),
                date_facture=date.today(),
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        session.refresh(reservation)
        if emise:
            _journaliser(session, reservation_id, user_id, f"Facture n° {reservation.numero_facture} émise")
        session.commit()
        return reservation.numero_facture


def _journaliser(session: Session, reservation_id: int, user_id: int | None, description: str) -> None:
    session.add(
        Historique(reservation_id=reservation_id, user_id=user_id, description=description, date=datetime.now(UTC))
    )


def _decrire(session: Session, sejour: Sejour) -> str:
    chambre = session.get(Chambre, sejour.chambre_id)
    return f"chambre {chambre.nom} du {sejour.date_debut:%d/%m/%Y} au {sejour.date_fin:%d/%m/%Y}"


def _normaliser(valeur: object) -> object:
    return valeur if isinstance(valeur, bool) else _vide(valeur)


def _vide(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None


def _exiger_libelle(libelle: str | None) -> str:
    propre = _vide(libelle)
    if propre is None:
        raise CatalogueInvalide("Le libellé est obligatoire")
    return propre


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


def _type_existe(session: Session, libelle: str) -> bool:
    return session.exec(select(TypeChambre.id).where(TypeChambre.libelle == libelle)).first() is not None


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


def _commit_unique(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if "unique" in str(erreur.orig).lower():
            raise CatalogueInvalide(message) from erreur
        raise


def _commit_utilise(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        raise CatalogueInvalide(message) from erreur


def _commit_lien(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if "foreign key" in str(erreur.orig).lower():
            raise CatalogueInvalide(message) from erreur
        raise


def _commit_liens(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as erreur:
        if "foreign key" in str(erreur.orig).lower():
            raise CatalogueInvalide("Ce type ou cette occupation est introuvable") from erreur
        raise
