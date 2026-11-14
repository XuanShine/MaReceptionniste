"""Statut affiché d'un séjour et résumé du jour du planning."""

from datetime import date

from sqlmodel import Session

from ma_receptionniste.consultations import STATUT_SEJOUR, ResumeJour, planning, resume_du_jour
from ma_receptionniste.models import Chambre, Client, EtatChambre, Reservation, Sejour, StatutReservation

ARRIVEE = date(2026, 10, 18)
DEPART = date(2026, 10, 20)


def test_les_statuts_affichables() -> None:
    assert [STATUT_SEJOUR[statut].libelle for statut in StatutReservation] == [
        "Option Devis",
        "Confirmé",
        "En cours",
        "Parti",
        "Annulée",
    ]


def test_resume_du_jour() -> None:
    jour = date(2026, 10, 19)
    sejours = [
        {"date_debut": date(2026, 10, 17), "date_fin": jour},  # part ce matin
        {"date_debut": jour, "date_fin": date(2026, 10, 21)},  # arrive ce soir
        {"date_debut": ARRIVEE, "date_fin": DEPART},  # reste
        {"date_debut": DEPART, "date_fin": date(2026, 10, 22)},  # pas encore là
    ]
    chambres = [{"etat": "pret"}, {"etat": "non_pret"}, {"etat": EtatChambre.non_pret}]

    assert resume_du_jour(sejours, chambres, jour) == ResumeJour(
        arrivees=1, departs=1, en_maison=2, chambres_non_pretes=2
    )


def test_le_planning_resume_aujourd_hui_meme_sur_une_autre_semaine(base) -> None:
    session = Session(base)
    jour = date(2026, 10, 19)
    client = Client(nom="Dupont")
    chambres = [Chambre(nom=nom, position=position) for position, nom in enumerate(["101", "102", "103"])]
    session.add(client)
    session.add_all(chambres)
    session.commit()
    confirmee = Reservation(client_id=client.id, partenaire="Booking.com")
    annulee = Reservation(client_id=client.id, statut=StatutReservation.annulee)
    session.add_all([confirmee, annulee])
    session.commit()
    session.add_all(
        [
            Sejour(reservation_id=confirmee.id, chambre_id=chambres[0].id, date_debut=ARRIVEE, date_fin=jour),
            Sejour(reservation_id=confirmee.id, chambre_id=chambres[1].id, date_debut=jour, date_fin=DEPART),
            Sejour(reservation_id=annulee.id, chambre_id=chambres[2].id, date_debut=jour, date_fin=DEPART),
        ]
    )
    session.commit()

    semaine_suivante = planning(session, date(2026, 10, 26), date(2026, 11, 2), aujourd_hui=jour)
    cette_semaine = planning(session, date(2026, 10, 19), date(2026, 10, 26), aujourd_hui=jour)

    assert semaine_suivante["sejours"] == []
    assert semaine_suivante["resume"] == ResumeJour(arrivees=1, departs=1, en_maison=1, chambres_non_pretes=3)
    arrivee = next(sejour for sejour in cette_semaine["sejours"] if sejour["date_debut"] == jour)
    assert arrivee["statut"] == StatutReservation.confirmee
    assert arrivee["partenaire"] == "Booking.com"
