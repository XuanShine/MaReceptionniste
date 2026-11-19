"""Le planning préfixe le nom de chaque séjour par le symbole de son statut."""

from datetime import date, timedelta

from nicegui.testing import User
from sqlmodel import select

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.db import get_session
from ma_receptionniste.models import StatutReservation
from ma_receptionniste.models import User as Compte
from ma_receptionniste.saisie import (
    ajouter_sejour,
    creer_chambre,
    creer_client,
    creer_reservation,
    enregistrer_fiche,
)

EMAIL = "planning-symbole@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-planning"


def _compte() -> int:
    with get_session() as session:
        try:
            register_user(session, EMAIL, "Réception", MOT_DE_PASSE)
        except EmailDejaUtilise:
            pass
        return session.exec(select(Compte).where(Compte.email == EMAIL)).one().id


def _sejour(nom: str, statut: StatutReservation, user_id: int, debut: date) -> None:
    reservation_id = creer_reservation(creer_client(nom))
    chambre_id = creer_chambre(f"{statut.value}-{reservation_id}", reservation_id)
    ajouter_sejour(reservation_id, chambre_id, debut, debut + timedelta(days=2))
    enregistrer_fiche(reservation_id, user_id, {"statut": statut.value})


async def test_le_planning_place_le_symbole_devant_le_nom(user: User) -> None:
    user_id = _compte()
    lundi = date.today() - timedelta(days=date.today().weekday())
    _sejour("Martin Option", StatutReservation.option_devis, user_id, lundi)
    _sejour("Durand Confirme", StatutReservation.confirmee, user_id, lundi)
    _sejour("Bernard Encours", StatutReservation.en_cours, user_id, lundi)
    _sejour("Leroy Parti", StatutReservation.parti, user_id, lundi)

    await user.open("/login")
    user.find("Email").type(EMAIL)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open("/")
    await user.should_see("📄 Martin Option")
    await user.should_see("📁 Durand Confirme")
    await user.should_see("▶️ Bernard Encours")
    await user.should_see("👋 Leroy Parti")
