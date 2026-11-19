import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import NamedTuple

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import montant_consommation, montant_sejour, nuits, taxe_du_sejour, totaux
from ma_receptionniste.models import (
    Chambre,
    ChambreChambreVirtuelle,
    ChambreVirtuelle,
    Client,
    EtatChambre,
    Historique,
    ModeReglement,
    OccupationChambre,
    Produit,
    Reservation,
    Sejour,
    StatutReservation,
    TypeChambre,
)

ETAT_LABEL = {
    EtatChambre.pret: "Prête",
    EtatChambre.non_pret: "Non prête",
}
MODE_REGLEMENT_LABEL = {
    ModeReglement.especes: "Espèces",
    ModeReglement.carte: "Carte bancaire",
    ModeReglement.virement: "Virement",
    ModeReglement.cheque: "Chèque",
    ModeReglement.ota: "OTA (prépayé)",
}


class Affichage(NamedTuple):
    libelle: str
    couleur: str
    symbole: str


STATUT_SEJOUR = {
    StatutReservation.option_devis: Affichage("Option Devis", "warning", "📄"),
    StatutReservation.confirmee: Affichage("Confirmé", "positive", "📁"),
    StatutReservation.en_cours: Affichage("En cours", "primary", "▶️"),
    StatutReservation.parti: Affichage("Parti", "ardoise", "👋"),
    StatutReservation.annulee: Affichage("Annulée", "negative", ""),
}


def nom_planning(nom: str, statut: StatutReservation) -> str:
    """Nom d'un séjour sur le planning, précédé du symbole de son statut."""
    symbole = STATUT_SEJOUR[statut].symbole
    return f"{symbole} {nom}" if symbole else nom


@dataclass(frozen=True)
class ResumeJour:
    arrivees: int
    departs: int
    en_maison: int
    chambres_non_pretes: int


def resume_du_jour(sejours: list[dict], chambres: list[dict], jour: date) -> ResumeJour:
    return ResumeJour(
        arrivees=sum(sejour["date_debut"] == jour for sejour in sejours),
        departs=sum(sejour["date_fin"] == jour for sejour in sejours),
        en_maison=sum(sejour["date_debut"] <= jour < sejour["date_fin"] for sejour in sejours),
        chambres_non_pretes=sum(chambre["etat"] == EtatChambre.non_pret for chambre in chambres),
    )


def nuits_entre(debut_sejour: date, fin_sejour: date, debut_fenetre: date, fin_fenetre: date) -> list[date]:
    """Nuits du séjour visibles dans [debut_fenetre, fin_fenetre). Le matin du départ est exclu."""
    jour = max(debut_sejour, debut_fenetre)
    borne = min(fin_sejour, fin_fenetre)
    nuits: list[date] = []
    while jour < borne:
        nuits.append(jour)
        jour += timedelta(days=1)
    return nuits


def segments(jours: list[date], sejours: list[dict]) -> list[dict]:
    """Découpe une ligne de planning : un bloc par séjour continu, une case par nuit libre."""
    par_nuit: dict[date, dict] = {}
    for sejour in sejours:
        for nuit in sejour["nuits"]:
            par_nuit[nuit] = sejour
    resultat: list[dict] = []
    index = 0
    while index < len(jours):
        sejour = par_nuit.get(jours[index])
        longueur = 1
        if sejour is not None:
            while index + longueur < len(jours) and par_nuit.get(jours[index + longueur]) is sejour:
                longueur += 1
        resultat.append({"sejour": sejour, "longueur": longueur})
        index += longueur
    return resultat


def _etat(valeur: EtatChambre | str) -> str:
    return valeur.value if isinstance(valeur, EtatChambre) else str(valeur)


def _libelle_type(chambre: Chambre) -> str | None:
    type_chambre = chambre.type_de_chambre
    if type_chambre is None or not type_chambre.libelle:
        return None
    return type_chambre.libelle.strip() or None


def _chambre_dict(chambre: Chambre) -> dict:
    etat = _etat(chambre.etat)
    return {
        "id": chambre.id,
        "nom": chambre.nom,
        "position": chambre.position,
        "etage": chambre.etage,
        "etat": etat,
        "etat_label": ETAT_LABEL.get(EtatChambre(etat), etat),
        "type_chambre": _libelle_type(chambre),
        "type_chambre_id": chambre.type_chambre_id,
        "occupation_chambre_id": chambre.occupation_chambre_id,
    }


def _requete_chambres():
    return select(Chambre).options(selectinload(Chambre.type_de_chambre)).order_by(Chambre.position, Chambre.nom)


def _lire_chambres(session: Session) -> list[dict]:
    return [_chambre_dict(chambre) for chambre in session.exec(_requete_chambres())]


def _sejours_visibles(session: Session, debut: date, fin: date) -> list[dict]:
    lignes = session.exec(
        select(Sejour, Reservation, Client)
        .join(Reservation, Reservation.id == Sejour.reservation_id)
        .join(Client, Client.id == Reservation.client_id)
        .where(Reservation.statut != StatutReservation.annulee)
        .where(Sejour.date_debut < fin)
        .where(Sejour.date_fin > debut)
        .order_by(Sejour.date_debut)
    ).all()
    return [
        {
            "id": sejour.id,
            "chambre_id": sejour.chambre_id,
            "reservation_id": sejour.reservation_id,
            "date_debut": sejour.date_debut,
            "date_fin": sejour.date_fin,
            "nom": reservation.nom_occupant or sejour.nom_client or client.nom,
            "partenaire": reservation.partenaire,
            "statut": StatutReservation(str(reservation.statut)),
            "nuits": nuits_entre(sejour.date_debut, sejour.date_fin, debut, fin),
        }
        for sejour, reservation, client in lignes
    ]


def planning(session: Session, debut: date, fin: date, aujourd_hui: date | None = None) -> dict:
    aujourd_hui = aujourd_hui or date.today()
    chambres = _lire_chambres(session)
    # La fenêtre [veille, lendemain) attrape aussi les départs du jour, dont date_fin vaut aujourd'hui.
    du_jour = _sejours_visibles(session, aujourd_hui - timedelta(days=1), aujourd_hui + timedelta(days=1))
    return {
        "chambres": chambres,
        "sejours": _sejours_visibles(session, debut, fin),
        "resume": resume_du_jour(du_jour, chambres, aujourd_hui),
    }


def charger_planning(debut: date, fin: date) -> dict:
    with get_session() as session:
        return planning(session, debut, fin)


def charger_resume() -> ResumeJour:
    aujourd_hui = date.today()
    with get_session() as session:
        return planning(session, aujourd_hui, aujourd_hui)["resume"]


def lister_chambres() -> list[dict]:
    with get_session() as session:
        return _lire_chambres(session)


def ecran_parametres() -> dict:
    with get_session() as session:
        types = session.exec(select(TypeChambre).order_by(TypeChambre.libelle)).all()
        virtuelles = session.exec(
            select(ChambreVirtuelle).order_by(ChambreVirtuelle.nom_raccourci, ChambreVirtuelle.id)
        ).all()
        occupations = session.exec(
            select(OccupationChambre).order_by(OccupationChambre.nombre_personnes, OccupationChambre.type_lits)
        ).all()
        chambres = _lire_chambres(session)
        liens_par_chambre: dict[int, list[int]] = {}
        requete_liens = select(ChambreChambreVirtuelle).order_by(ChambreChambreVirtuelle.chambre_virtuelle_id)
        for lien in session.exec(requete_liens):
            liens_par_chambre.setdefault(lien.chambre_id, []).append(lien.chambre_virtuelle_id)
        for chambre in chambres:
            chambre["chambres_virtuelles_ids"] = liens_par_chambre.get(chambre["id"], [])
        virtuelles_par_type: dict[int, list[dict]] = {}
        for virtuelle in virtuelles:
            virtuelles_par_type.setdefault(virtuelle.type_chambre_id, []).append(
                {
                    "id": virtuelle.id,
                    "wubook_id": virtuelle.wubook_id,
                    "description": virtuelle.description,
                    "nom_raccourci": virtuelle.nom_raccourci.strip(),
                    "prix_defaut": virtuelle.prix_defaut,
                    "prix_mini": virtuelle.prix_mini,
                }
            )
    return {
        "types": [
            {
                "id": type_chambre.id,
                "wubook_id": type_chambre.wubook_id,
                "libelle": type_chambre.libelle.strip(),
                "description": type_chambre.description,
                "nom_raccourci": (type_chambre.nom_raccourci or "").strip() or None,
                "prix_defaut": type_chambre.prix_defaut,
                "prix_mini": type_chambre.prix_mini,
                "channel_manager_uniquement": bool(type_chambre.channel_manager_uniquement),
                "virtuelles": virtuelles_par_type.get(type_chambre.id, []),
            }
            for type_chambre in types
            if type_chambre.libelle and type_chambre.libelle.strip()
        ],
        "occupations": [
            {
                "id": occupation.id,
                "nombre_personnes": occupation.nombre_personnes,
                "type_lits": occupation.type_lits,
            }
            for occupation in occupations
        ],
        "virtuelles": [
            {
                "id": virtuelle.id,
                "nom_raccourci": virtuelle.nom_raccourci.strip(),
                "type_chambre_id": virtuelle.type_chambre_id,
            }
            for virtuelle in virtuelles
        ],
        "chambres": chambres,
        "position": max((chambre["position"] for chambre in chambres), default=0) + 1,
    }


def _client_dict(client: Client) -> dict:
    return {
        "id": client.id,
        "nom": client.nom,
        "pays": client.pays,
        "email": client.email,
        "telephone": client.telephone,
        "adresse": client.adresse,
        "notes": client.notes,
    }


def lister_clients() -> list[dict]:
    with get_session() as session:
        clients = session.exec(select(Client).order_by(Client.cree_le.desc())).all()
        return [_client_dict(client) for client in clients]


def lister_produits(*, actifs_seulement: bool = False) -> list[Produit]:
    """Exemplaires détachés : la session est déjà fermée quand la page les lit."""
    with get_session() as session:
        requete = select(
            Produit.id,
            Produit.nom,
            Produit.prix_unitaire_centimes,
            Produit.taux_tva_pour_mille,
            Produit.actif,
            Produit.ponctuel,
        )
        if actifs_seulement:
            requete = requete.where(Produit.actif.is_(True))
        lignes = list(session.exec(requete).all())
    copies = [
        Produit(
            id=identifiant,
            nom=nom,
            prix_unitaire_centimes=prix,
            taux_tva_pour_mille=taux,
            actif=bool(actif),
            ponctuel=bool(ponctuel),
        )
        for identifiant, nom, prix, taux, actif, ponctuel in lignes
    ]
    copies.sort(key=lambda produit: (produit.nom.casefold(), produit.id or 0))
    return copies


def lire_client(client_id: int) -> dict | None:
    with get_session() as session:
        client = session.get(Client, client_id)
        return _client_dict(client) if client is not None else None


def normaliser_nom(nom: str | None) -> str:
    """Minuscules, sans accents ni espaces superflus, pour comparer les noms saisis."""
    decompose = unicodedata.normalize("NFD", (nom or "").casefold())
    sans_accent = "".join(caractere for caractere in decompose if unicodedata.category(caractere) != "Mn")
    return " ".join(sans_accent.split())


def _detail_client(client: dict) -> str | None:
    for cle in ("telephone", "email", "pays"):
        texte = client.get(cle)
        if texte and texte.strip():
            return texte.strip()
    return None


def libelle_client(client: dict) -> str:
    detail = _detail_client(client)
    identifiant = f"n° {client['id']}"
    if detail is None:
        return f"{client['nom']} · {identifiant}"
    return f"{client['nom']} · {detail} · {identifiant}"


def _proximite(requete: str, nom: str) -> float:
    scores = [SequenceMatcher(None, requete, nom).ratio()]
    compact_requete = requete.replace(" ", "")
    compact_nom = nom.replace(" ", "")
    if compact_requete and compact_nom:
        scores.append(SequenceMatcher(None, compact_requete, compact_nom).ratio())
    scores.extend(SequenceMatcher(None, requete, mot).ratio() for mot in nom.split())
    return max(scores)


def rechercher_clients(texte: str) -> list[dict]:
    """Exact, puis contenant, puis noms proches. Une recherche vide renvoie tout le répertoire."""
    clients = lister_clients()
    requete = normaliser_nom(texte)
    if not requete:
        return sorted(clients, key=lambda client: (normaliser_nom(client["nom"]), client["id"]))
    exacts: list[dict] = []
    contenus: list[dict] = []
    proches: list[tuple[float, dict]] = []
    compact_requete = requete.replace(" ", "")
    for client in clients:
        nom = normaliser_nom(client["nom"])
        if nom == requete:
            exacts.append(client)
            continue
        compact_nom = nom.replace(" ", "")
        if requete in nom or (compact_requete and compact_requete in compact_nom):
            contenus.append(client)
            continue
        score = _proximite(requete, nom)
        if score >= 0.6:
            proches.append((score, client))
    exacts.sort(key=lambda client: client["id"])
    contenus.sort(key=lambda client: (normaliser_nom(client["nom"]), client["id"]))
    proches.sort(key=lambda item: (-item[0], normaliser_nom(item[1]["nom"]), item[1]["id"]))
    return exacts + contenus + [client for _, client in proches]


def options_chambres() -> dict[int, str]:
    return {
        chambre["id"]: " · ".join(filter(None, (chambre["nom"], chambre["type_chambre"])))
        for chambre in lister_chambres()
    }


def _avec_tout(requete):
    return requete.options(
        selectinload(Reservation.client),
        selectinload(Reservation.sejours).selectinload(Sejour.chambre).selectinload(Chambre.type_de_chambre),
        selectinload(Reservation.consommations),
        selectinload(Reservation.reglements),
    )


def _bornes(sejours: list[Sejour]) -> tuple[date | None, date | None]:
    if not sejours:
        return None, None
    return min(sejour.date_debut for sejour in sejours), max(sejour.date_fin for sejour in sejours)


def lister_reservations() -> list[dict]:
    with get_session() as session:
        reservations = session.exec(_avec_tout(select(Reservation)).order_by(Reservation.date_creation.desc())).all()
        resultat = []
        for reservation in reservations:
            sejours = sorted(reservation.sejours, key=lambda sejour: (sejour.date_debut, sejour.id))
            debut, fin = _bornes(sejours)
            resultat.append(
                {
                    "id": reservation.id,
                    "client": reservation.nom_occupant or reservation.client.nom,
                    "partenaire": reservation.partenaire,
                    "chambres": ", ".join(sejour.chambre.nom for sejour in sejours),
                    "date_debut": debut,
                    "date_fin": fin,
                    "nuits": nuits(debut, fin) if debut and fin else 0,
                    "statut": StatutReservation(str(reservation.statut)),
                    "total": totaux(sejours, reservation.consommations, reservation.reglements).total,
                }
            )
        return resultat


def fiche_sejour(reservation_id: int) -> dict | None:
    with get_session() as session:
        reservation = session.exec(
            _avec_tout(select(Reservation))
            .options(selectinload(Reservation.historiques).selectinload(Historique.user))
            .where(Reservation.id == reservation_id)
        ).first()
        if reservation is None:
            return None
        client = reservation.client
        sejours = sorted(reservation.sejours, key=lambda sejour: (sejour.date_debut, sejour.id))
        consommations = sorted(reservation.consommations, key=lambda consommation: consommation.date)
        reglements = sorted(reservation.reglements, key=lambda reglement: reglement.date)
        historique = sorted(reservation.historiques, key=lambda note: (note.date, note.id), reverse=True)
        debut, fin = _bornes(sejours)
        return {
            "id": reservation.id,
            "client": {
                "id": client.id,
                "nom": client.nom,
                "nom_complet": client.nom,
                "pays": client.pays,
                "telephone": client.telephone,
                "email": client.email,
                "adresse": client.adresse,
                "notes_client": client.notes,
            },
            "reservation": {
                "statut": StatutReservation(str(reservation.statut)),
                "partenaire": reservation.partenaire,
                "nom_occupant": reservation.nom_occupant,
                "type_voiture": reservation.type_voiture,
                "date_facture": reservation.date_facture,
                "numero_facture": reservation.numero_facture,
                "notes": reservation.notes,
                "notes_internes": reservation.notes_internes,
                "facturation": reservation.facturation,
            },
            "debut": debut,
            "fin": fin,
            "statut_sejour": StatutReservation(str(reservation.statut)),
            "lignes": [
                {
                    "id": sejour.id,
                    "chambre_id": sejour.chambre_id,
                    "chambre_nom": sejour.chambre.nom,
                    "type_chambre": _libelle_type(sejour.chambre),
                    "date_debut": sejour.date_debut,
                    "date_fin": sejour.date_fin,
                    "nuits": nuits(sejour.date_debut, sejour.date_fin),
                    "prix_nuit_centimes": sejour.prix_nuit_centimes,
                    "adultes": sejour.adultes,
                    "enfants": sejour.enfants,
                    "nom_client": sejour.nom_client,
                    "taxe": taxe_du_sejour(sejour),
                    "montant": montant_sejour(sejour),
                }
                for sejour in sejours
            ],
            "consommations": [
                {
                    "id": consommation.id,
                    "date": consommation.date,
                    "libelle": consommation.libelle,
                    "quantite": consommation.quantite,
                    "prix_unitaire_centimes": consommation.prix_unitaire_centimes,
                    "montant": montant_consommation(consommation),
                }
                for consommation in consommations
            ],
            "reglements": [
                {
                    "id": reglement.id,
                    "date": reglement.date,
                    "mode": ModeReglement(str(reglement.mode)),
                    "montant_centimes": reglement.montant_centimes,
                }
                for reglement in reglements
            ],
            "historique": [
                {
                    "id": note.id,
                    "date": note.date,
                    "auteur": note.user.nom if note.user else None,
                    "description": note.description,
                }
                for note in historique
            ],
            "compteurs": {
                "reservations": len(sejours),
                "consommations": len(consommations),
                "reglements": len(reglements),
                "modifications": len(historique),
            },
            "totaux": totaux(sejours, consommations, reglements),
        }
