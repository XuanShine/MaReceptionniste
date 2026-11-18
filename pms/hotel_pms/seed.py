"""Jeu de démonstration, dont la fiche Monnier Christophe / WuBook."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from hotel_pms.auth import hasher_mot_de_passe
from hotel_pms.models import (
    Chambre,
    Client,
    EtatChambre,
    LigneReservation,
    ModificationSejour,
    Produit,
    Reglement,
    Sejour,
    StatutSejour,
    User,
)

IDENTIFIANT_DEMO = "reception"
MOT_DE_PASSE_DEMO = "reception"

NOTES_MONNIER = "Montant payé en ligne : 61,20\nHeure d'arrivée prévue : 14:00\narrivé : ?"
NOTES_INTERNES_MONNIER = "Réservation WuBook. Ne pas déplacer la chambre 308 sans accord."
FACTURATION_MONNIER = "Client passage — facturation du séjour uniquement."
EMAIL_MONNIER = "chris.tem@sfr.fr"
MOBILE_MONNIER = "+33 0678157017"
REF_PARTENAIRE = "1793102243"
REF_DISTRIBUTEUR = "1793102243 ( WuBook )"

JOURNAL_MONNIER = (
    (datetime(2026, 10, 26, 18, 42, tzinfo=UTC), "Réservation importée depuis WuBook (réf. 1793102243)"),
    (datetime(2026, 10, 26, 18, 42, tzinfo=UTC), "Chambre 308 attribuée (Double)"),
    (datetime(2026, 10, 26, 18, 43, tzinfo=UTC), "Heure d'arrivée prévue : 14:00"),
    (datetime(2026, 10, 27, 9, 15, tzinfo=UTC), "Montant payé en ligne : 61,20 (lien de paiement)"),
    (datetime(2026, 10, 27, 9, 16, tzinfo=UTC), "Taxe de séjour : 4,00"),
    (datetime(2026, 10, 27, 11, 2, tzinfo=UTC), "Téléphone mobile mis à jour"),
    (datetime(2026, 10, 27, 14, 5, tzinfo=UTC), "Note d'arrivée : arrivé ?"),
    (datetime(2026, 10, 27, 14, 8, tzinfo=UTC), "Règlement carte bancaire : 4,00"),
)


def alimenter(engine: Engine, forcer: bool = False) -> None:
    with Session(engine) as session:
        existe = session.exec(select(User)).first()
        if existe and not forcer:
            return
        if existe and forcer:
            raise RuntimeError("La base contient déjà des données. Relancez avec --reset.")

        session.add(
            User(
                identifiant=IDENTIFIANT_DEMO,
                nom="Réception",
                password_hash=hasher_mot_de_passe(MOT_DE_PASSE_DEMO),
            )
        )
        passage = Client(nom="CLIENT PASSAGE")
        bernard = Client(nom="Bernard Alain", telephone="06 12 34 56 78", email="bernard.alain@example.com")
        martin = Client(nom="Martin Sophie", telephone="06 98 76 54 32", email="sophie.martin@example.com")
        session.add(passage)
        session.add(bernard)
        session.add(martin)

        chambres = {
            "101": Chambre(numero="101", type_chambre="Simple", etat=EtatChambre.non_pret),
            "102": Chambre(numero="102", type_chambre="Double", etat=EtatChambre.pret),
            "201": Chambre(numero="201", type_chambre="Double", etat=EtatChambre.pret),
            "202": Chambre(numero="202", type_chambre="Twin", etat=EtatChambre.non_pret),
            "305": Chambre(numero="305", type_chambre="Suite", etat=EtatChambre.pret),
            "308": Chambre(numero="308", type_chambre="Double", etat=EtatChambre.pret),
        }
        for chambre in chambres.values():
            session.add(chambre)

        session.add(Produit(nom="Petit-déjeuner", prix_ttc=Decimal("12.00"), taux_tva=Decimal("10.00")))
        session.add(Produit(nom="Parking", prix_ttc=Decimal("8.00"), taux_tva=Decimal("20.00")))
        session.add(Produit(nom="Taxe de séjour", prix_ttc=Decimal("4.00"), taux_tva=Decimal("0.00")))
        session.flush()

        monnier = Sejour(
            nom="Monnier Christophe",
            client_id=passage.id,
            partenaire="WuBook",
            statut=StatutSejour.en_cours,
            telephone_mobile=MOBILE_MONNIER,
            email=EMAIL_MONNIER,
            ref_partenaire=REF_PARTENAIRE,
            ref_distributeur=REF_DISTRIBUTEUR,
            notes=NOTES_MONNIER,
            notes_internes=NOTES_INTERNES_MONNIER,
            facturation_client=FACTURATION_MONNIER,
        )
        session.add(monnier)
        session.flush()
        session.add(
            LigneReservation(
                sejour_id=monnier.id,
                chambre_id=chambres["308"].id,
                type_chambre="Double",
                nb_jours=1,
                date_debut=date(2026, 10, 27),
                date_fin=date(2026, 10, 28),
                prix_ttc=Decimal("61.20"),
                remise_pct=Decimal("0"),
                adultes=2,
                enfants=0,
                taxe_sejour=Decimal("4.00"),
            )
        )
        session.add(
            Reglement(
                sejour_id=monnier.id,
                date_reglement=date(2026, 10, 27),
                type_reglement="Lien de paiement",
                montant=Decimal("61.20"),
            )
        )
        session.add(
            Reglement(
                sejour_id=monnier.id,
                date_reglement=date(2026, 10, 27),
                type_reglement="Carte bancaire",
                montant=Decimal("4.00"),
            )
        )
        for quand, texte in JOURNAL_MONNIER:
            session.add(ModificationSejour(sejour_id=monnier.id, date_modif=quand, description=texte))

        autre = Sejour(
            nom="Bernard Alain",
            client_id=bernard.id,
            pays_nat="France",
            partenaire="Direct",
            statut=StatutSejour.en_cours,
            telephone_mobile="06 12 34 56 78",
            email="bernard.alain@example.com",
        )
        session.add(autre)
        session.flush()
        session.add(
            LigneReservation(
                sejour_id=autre.id,
                chambre_id=chambres["201"].id,
                type_chambre="Double",
                nb_jours=2,
                date_debut=date(2026, 10, 28),
                date_fin=date(2026, 10, 30),
                prix_ttc=Decimal("180.00"),
                remise_pct=Decimal("0"),
                adultes=1,
                enfants=0,
                taxe_sejour=Decimal("8.00"),
            )
        )

        parti = Sejour(
            nom="Martin Sophie",
            client_id=martin.id,
            pays_nat="France",
            partenaire="Booking",
            statut=StatutSejour.traite,
            telephone_mobile="06 98 76 54 32",
            email="sophie.martin@example.com",
        )
        session.add(parti)
        session.flush()
        session.add(
            LigneReservation(
                sejour_id=parti.id,
                chambre_id=chambres["102"].id,
                type_chambre="Double",
                nb_jours=2,
                date_debut=date(2026, 10, 25),
                date_fin=date(2026, 10, 27),
                prix_ttc=Decimal("140.00"),
                remise_pct=Decimal("0"),
                adultes=2,
                enfants=0,
                taxe_sejour=Decimal("8.00"),
            )
        )
        session.add(
            Reglement(
                sejour_id=parti.id,
                date_reglement=date(2026, 10, 25),
                type_reglement="Carte bancaire",
                montant=Decimal("148.00"),
            )
        )
        session.commit()


def main() -> None:
    import argparse
    import os

    from hotel_pms.db import DB_PATH, creer_engine, initialiser, preparer_url

    parser = argparse.ArgumentParser(description="Crée les tables et le séjour de démonstration.")
    parser.add_argument("--reset", action="store_true", help="Efface la base puis réinsère la démo.")
    args = parser.parse_args()
    url = preparer_url(os.environ.get("PMS_DATABASE_URL", f"sqlite:///{DB_PATH}"))
    initialiser(creer_engine(url), reset=args.reset)
    print(f"Base prête : {url}")


if __name__ == "__main__":
    main()
