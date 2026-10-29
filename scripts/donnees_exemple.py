"""Remplit la base pointée par DATABASE_URL avec un hôtel de démonstration, autour de la semaine courante.

    DATABASE_URL=sqlite:////tmp/demo.db uv run python scripts/donnees_exemple.py

Relançable : chaque étape vérifie ce qui existe déjà et n'ajoute que ce qui manque.
"""

from datetime import date, timedelta

from sqlmodel import select

from ma_receptionniste.auth import register_user
from ma_receptionniste.db import create_db_and_tables, get_session
from ma_receptionniste.models import (
    Chambre,
    Client,
    Consommation,
    EtatChambre,
    Historique,
    ModeReglement,
    Reglement,
    Reservation,
    Sejour,
    User,
)
from ma_receptionniste.saisie import (
    ajouter_consommation,
    ajouter_note,
    ajouter_reglement,
    ajouter_sejour,
    annuler_reservation,
    creer_chambre,
    creer_client,
    creer_reservation,
    enregistrer_fiche,
    facturer,
)

EMAIL = "reception@hotel-panorama.fr"
MOT_DE_PASSE = "panorama"

# nom → (type, prête)
CHAMBRES = {
    "101": ("Single BB", True),
    "102": ("Double", True),
    "103": ("Twin", False),
    "104": ("Double", True),
    "105": ("Triple", True),
    "106": ("Familiale", False),
    "201": ("Double", True),
    "202": ("Double", True),
    "203": ("Twin", True),
    "204": ("Suite", False),
    "205": ("Single BB", True),
    "206": ("Double", True),
    "406": ("Single BB", True),
}

NOTES_CAPTURE = (
    "** THIS RESERVATION HAS BEEN PRE-PAID **\n"
    "BOOKING NOTE : Payment charge is EUR 1.92696\n"
    "This is a corporate booking for FORMAVENIR PERFORMANCES.\n"
    "BED PREFERENCE: Twin/Double: 1 large double\n"
    "arrivé : 19h20 (arrivé à 19h à la gare de grasse)"
)

# Décalages en jours depuis aujourd'hui. Séjour : (chambre, arrivée, nuits, prix/nuit en centimes, adultes, enfants).
RESERVATIONS = [
    {
        "client": ("Bénédicte LE CLOEREC", "France", "+33 6 12 34 56 78", "b.lecloerec@formavenir.fr"),
        "fiche": {"partenaire": "Booking.com", "traitee": True, "notes": NOTES_CAPTURE},
        "sejours": [("406", -1, 2, 6882, 1, 0)],
        "consommations": [("Petit-déjeuner", 1, 1400)],
        "reglements": [(ModeReglement.ota, 13764)],
        "note": "Client arrivé à 19h20 depuis la gare de Grasse, clé remise.",
    },
    {
        "client": ("Paul MARTIN", "France", "+33 6 22 10 45 98", "paul.martin@orange.fr"),
        "fiche": {"partenaire": "Direct", "type_voiture": "Peugeot 308 grise"},
        "sejours": [("101", -2, 3, 7500, 1, 0)],
        "consommations": [("Bar : verre de rosé", 2, 650)],
        "reglements": [(ModeReglement.carte, 10000)],
    },
    {
        "client": ("Giulia ROSSI", "Italie", "+39 333 456 7890", "giulia.rossi@libero.it"),
        "fiche": {"partenaire": "Booking.com", "notes": "Late arrival around 22:00."},
        "sejours": [("102", 0, 2, 9500, 2, 0)],
        "reglements": [(ModeReglement.ota, 19000)],
    },
    {
        "client": ("Jonas SCHMIDT", "Allemagne", "+49 171 2345678", "j.schmidt@web.de"),
        "fiche": {"partenaire": "Expedia", "traitee": True},
        "sejours": [("103", -3, 3, 9000, 2, 0)],
        "consommations": [("Petit-déjeuner", 6, 1400)],
        "reglements": [(ModeReglement.carte, 36600)],
        "facturer": True,
    },
    {
        "client": ("Claire DUBOIS", "France", "+33 4 93 36 12 45", None),
        "fiche": {"partenaire": "Téléphone", "notes_internes": "Habituée, préfère le côté jardin."},
        "sejours": [("104", 1, 4, 9500, 2, 0)],
    },
    {
        "client": ("Oliver SMITH", "Royaume-Uni", "+44 7700 900123", "oliver.smith@gmail.com"),
        "fiche": {"partenaire": "Booking.com", "notes": "Baby cot requested."},
        "sejours": [("105", -1, 5, 12500, 2, 1)],
        "consommations": [("Petit-déjeuner", 3, 1400)],
    },
    {
        "client": ("Lucía GARCÍA", "Espagne", "+34 612 345 678", "lucia.garcia@gmail.com"),
        "fiche": {"partenaire": "Expedia"},
        "sejours": [("106", 2, 3, 15500, 2, 2)],
    },
    {
        "client": ("Hugo BERNARD", "France", "+33 6 45 78 12 03", "hugo.bernard@free.fr"),
        "fiche": {"partenaire": "Direct", "notes_tempo": "Rappeler pour l'heure d'arrivée."},
        "sejours": [("201", 0, 1, 9500, 1, 0)],
    },
    {
        "client": ("Camille PETIT", "France", "+33 6 98 76 54 32", "camille.petit@gmail.com"),
        "fiche": {"partenaire": "Site web", "traitee": True},
        "sejours": [("202", -4, 2, 9500, 2, 0)],
        "reglements": [(ModeReglement.especes, 19800)],
        "facturer": True,
    },
    {
        "client": ("Léa MOREAU", "France", "+33 7 81 22 33 44", "lea.moreau@outlook.fr"),
        "fiche": {"partenaire": "Booking.com"},
        "sejours": [("202", 3, 2, 9500, 2, 0)],
    },
    {
        "client": ("Minh NGUYEN", "Viêt Nam", "+84 90 123 45 67", "minh.nguyen@gmail.com"),
        "fiche": {"partenaire": "Expedia", "facturation": "VIETCOM TRAVEL\n12 rue de la Paix\n75002 Paris"},
        "sejours": [("203", -1, 3, 9000, 2, 0)],
    },
    {
        "client": ("Sophie LAURENT", "Suisse", "+41 79 123 45 67", "s.laurent@bluewin.ch"),
        "fiche": {"partenaire": "Téléphone"},
        "sejours": [("204", 4, 3, 21000, 2, 0)],
    },
    {
        "client": ("Marc FONTAINE", "Belgique", "+32 470 12 34 56", "marc.fontaine@skynet.be"),
        "fiche": {"partenaire": "Direct", "notes": "Famille, deux chambres communicantes si possible."},
        "sejours": [("205", 0, 3, 6882, 1, 0), ("206", 0, 3, 9500, 2, 1)],
    },
    {
        "client": ("Anna KOWALSKA", "Pologne", "+48 501 234 567", "anna.kowalska@wp.pl"),
        "fiche": {"partenaire": "Booking.com"},
        "sejours": [("201", 2, 2, 9500, 2, 0)],
    },
    {
        "client": ("Thomas LEROY", "France", "+33 6 11 22 33 44", None),
        "fiche": {"partenaire": "Booking.com"},
        "sejours": [("101", 3, 2, 6882, 1, 0)],
    },
    {
        "client": ("Julie BLANC", "France", "+33 6 55 44 33 22", "julie.blanc@gmail.com"),
        "fiche": {"partenaire": "Expedia"},
        "sejours": [("103", 1, 2, 9000, 2, 0)],
        "annuler": True,
    },
]


def main() -> None:
    create_db_and_tables()
    aujourd_hui = date.today()
    user_id = _reception()
    chambres = {nom: _chambre(nom, position, *infos) for position, (nom, infos) in enumerate(CHAMBRES.items(), 1)}
    for donnees in RESERVATIONS:
        _reservation(donnees, chambres, user_id, aujourd_hui)
    print(f"Base prête : {len(chambres)} chambres, {len(RESERVATIONS)} réservations.")
    print(f"Connexion : {EMAIL} / {MOT_DE_PASSE}")


def _reception() -> int:
    with get_session() as session:
        user = session.exec(select(User).where(User.email == EMAIL)).first()
        if user is None:
            user = register_user(session, EMAIL, "Réception Panorama", MOT_DE_PASSE)
        return user.id


def _chambre(nom: str, position: int, type_chambre: str, prete: bool) -> int:
    with get_session() as session:
        chambre = session.exec(select(Chambre).where(Chambre.nom == nom)).first()
    chambre_id = chambre.id if chambre else creer_chambre(nom, position, type_chambre)
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        chambre.etat = EtatChambre.pret if prete else EtatChambre.non_pret
        session.add(chambre)
        session.commit()
    return chambre_id


def _reservation(donnees: dict, chambres: dict[str, int], user_id: int, aujourd_hui: date) -> None:
    nom, pays, telephone, email = donnees["client"]
    with get_session() as session:
        client = session.exec(select(Client).where(Client.nom == nom)).first()
        client_id = client.id if client else None
        reservation = (
            session.exec(select(Reservation).where(Reservation.client_id == client_id)).first() if client_id else None
        )
        reservation_id = reservation.id if reservation else None
    if client_id is None:
        client_id = creer_client(nom, email, telephone, pays=pays)
    if reservation_id is None:
        reservation_id = creer_reservation(client_id)
        _historique(reservation_id, user_id, "Réservation créée")

    enregistrer_fiche(reservation_id, user_id, donnees["fiche"])
    for chambre, decalage, nuits, prix, adultes, enfants in donnees["sejours"]:
        if not _existe(Sejour, reservation_id, Sejour.chambre_id == chambres[chambre]):
            debut = aujourd_hui + timedelta(days=decalage)
            ajouter_sejour(
                reservation_id,
                chambres[chambre],
                debut,
                debut + timedelta(days=nuits),
                adultes=adultes,
                enfants=enfants,
                prix_nuit_centimes=prix,
                user_id=user_id,
            )
    for libelle, quantite, prix in donnees.get("consommations", []):
        if not _existe(Consommation, reservation_id, Consommation.libelle == libelle):
            ajouter_consommation(reservation_id, libelle, quantite, prix, user_id)
    for mode, montant in donnees.get("reglements", []):
        if not _existe(Reglement, reservation_id, Reglement.mode == mode, Reglement.montant_centimes == montant):
            ajouter_reglement(reservation_id, mode, montant, user_id)
    if note := donnees.get("note"):
        if not _existe(Historique, reservation_id, Historique.description == note):
            ajouter_note(reservation_id, user_id, note)
    if donnees.get("facturer"):
        facturer(reservation_id, user_id)
    if donnees.get("annuler"):
        annuler_reservation(reservation_id, user_id)


def _existe(modele, reservation_id: int, *criteres) -> bool:
    requete = select(modele.id).where(modele.reservation_id == reservation_id, *criteres)
    with get_session() as session:
        return session.exec(requete).first() is not None


def _historique(reservation_id: int, user_id: int, description: str) -> None:
    if not _existe(Historique, reservation_id, Historique.description == description):
        ajouter_note(reservation_id, user_id, description)


if __name__ == "__main__":
    main()
